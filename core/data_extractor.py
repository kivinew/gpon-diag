#!/usr/bin/env python3
"""Data Extraction Module — fetch ONT records with match/mismatch state.

Sources:
  - SQLite diagnoses.db (historical diagnosis results)
  - OLT telnet (real-time via 'display ont info summary')

Output: list of OntRecord with ONT ID, match state, config state, timestamp.
  - to_json() / to_csv() for file export.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sqlite3
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO

logger = logging.getLogger(__name__)

# Use centralized constants
from core.constants import TZ_LOCAL

# ──────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────

@dataclass
class OntRecord:
    """Structured ONT record with match state."""
    ont_id: str               # ONT ID (0-127)
    address: str              # F/S/P/ONT
    status: str               # online / offline
    match_state: str          # match / mismatch / initial / -
    config_state: str         # normal / initial / -
    distance_m: int = -1
    description: str = ""
    serial: str = ""
    rx_power: float = 999.0
    tx_power: float = 999.0
    olt_name: str = ""
    olt_host: str = ""
    collected_at: str = field(default_factory=lambda: datetime.now(TZ_LOCAL).isoformat())

    @property
    def is_match_ok(self) -> bool:
        """True if match state is 'match'."""
        return self.match_state.lower() == "match"

    @property
    def is_mismatch(self) -> bool:
        return self.match_state.lower() in ("mismatch", "mis-match")

    @property
    def is_online(self) -> bool:
        return self.status.lower() in ("online", "working")


# ──────────────────────────────────────────────
# DB extraction
# ──────────────────────────────────────────────

def _get_db_path() -> str:
    """Resolve the diagnoses.db path relative to this project."""
    # Walk up from core/ to project root
    here = Path(__file__).resolve().parent  # core/
    return str(here.parent / "data" / "diagnoses.db")


def extract_from_db(
    db_path: Optional[str] = None,
    olt_name: Optional[str] = None,
    olt_host: Optional[str] = None,
    ont_address: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 500,
) -> List[OntRecord]:
    """Extract ONT records from SQLite diagnoses.db.

    Args:
        db_path: Path to diagnoses.db (default: auto-detect).
        olt_name: Filter by OLT name (LIKE match).
        olt_host: Filter by OLT host (LIKE match).
        ont_address: Filter by ONT address (exact match via ONT).
        status_filter: 'online', 'offline', or None for all.
        limit: Max records to return.

    Returns:
        List of OntRecord extracted from the DB.
    """
    path = db_path or _get_db_path()
    if not os.path.exists(path):
        logger.warning(f"DB not found: {path}")
        return []

    records: List[OntRecord] = []
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    try:
        cur = conn.cursor()

        # Check tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}

        if "diagnoses" not in tables:
            logger.warning("No 'diagnoses' table in DB")
            return []

        # Build query
        query = "SELECT id, timestamp, olt_host, olt_name, ont_address, input_type, input_value, report_json FROM diagnoses WHERE 1=1"
        params: List[Any] = []

        if olt_name:
            query += " AND olt_name LIKE ?"
            params.append(f"%{olt_name}%")
        if olt_host:
            query += " AND olt_host LIKE ?"
            params.append(f"%{olt_host}%")
        if ont_address:
            query += " AND ont_address = ?"
            params.append(ont_address)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cur.execute(query, params)
        rows = cur.fetchall()

        for row in rows:
            try:
                report = json.loads(row["report_json"]) if row["report_json"] else {}
            except (json.JSONDecodeError, TypeError):
                logger.debug(f"Bad JSON in row {row['id']}, skipping")
                continue

            ont_addr = row["ont_address"] or report.get("ont", "")

            # Status filter on report data
            is_online = report.get("is_online", report.get("status", "") in ("online", "working"))
            if status_filter == "online" and not is_online:
                continue
            if status_filter == "offline" and is_online:
                continue

            match_state = report.get("match_state", "")
            config_state = report.get("config_state", "")
            status = report.get("status", "")
            serial = report.get("serial", "")
            description = report.get("description", "")

            # Extract rx/tx power from report
            rx = report.get("ont_rx_power", 999.0)
            tx = report.get("ont_tx_power", 999.0)
            distance = report.get("distance_m", -1)

            # ONT ID from address
            ont_id = ""
            addr_parts = ont_addr.split("/")
            if len(addr_parts) == 4:
                ont_id = addr_parts[3]

            rec = OntRecord(
                ont_id=ont_id,
                address=ont_addr,
                status=status,
                match_state=match_state,
                config_state=config_state,
                distance_m=distance if isinstance(distance, int) else -1,
                description=description,
                serial=serial,
                rx_power=float(rx) if isinstance(rx, (int, float)) else 999.0,
                tx_power=float(tx) if isinstance(tx, (int, float)) else 999.0,
                olt_name=row["olt_name"] or report.get("head_station", ""),
                olt_host=row["olt_host"],
                collected_at=row["timestamp"] or report.get("timestamp", ""),
            )
            records.append(rec)

    finally:
        conn.close()

    return records


# ──────────────────────────────────────────────
# Telnet extraction (real-time)
# ──────────────────────────────────────────────

def extract_from_olt_port(
    olt_config: dict,
    frame: str,
    slot: str,
    port: str,
    connect_timeout: int = 30,
) -> List[OntRecord]:
    """Extract all ONT records from one GPON port on an OLT via telnet.

    Uses 'display ont info summary <frame>/<slot>/<port>' which returns
    ONT-ID, Run state, Config state, Match state, ONT distance, Description.

    Args:
        olt_config: OLT config dict with host, port, credential_key.
        frame: Frame number (typically '0').
        slot: Slot number.
        port: GPON port number.
        connect_timeout: Telnet connection timeout.

    Returns:
        List of OntRecord parsed from the OLT.

    Raises:
        ConnectionError: If OLT is unreachable or authentication fails.
        ValueError: If OLT config is missing credentials.
    """
    from core.olt import OltConnection
    from core.parser import parse_ont_info_summary
    from core.utils import load_olt_credentials

    host = olt_config["host"]
    telnet_port = olt_config.get("port", 23)

    # Load credentials from env using shared utility
    username, password = load_olt_credentials(olt_config)
    if not username or not password:
        raise ValueError(
            f"Missing credentials for OLT '{olt_config.get('name', host)}'. "
            f"Set GPON_OLT_<KEY>_USERNAME/PASSWORD."
        )

    olt = OltConnection(host, telnet_port, username, password, connect_timeout)
    try:
        olt.connect()
        time.sleep(1)
        if not olt._connected:
            raise ConnectionError(f"Failed to establish connection to {host}")

        olt_name = olt_config.get("name", host)

        summaries = olt.collect_port_summary(frame, slot, port)

        records = []
        for s in summaries:
            address = f"{frame}/{slot}/{port}/{s.ont_id}"
            rec = OntRecord(
                ont_id=s.ont_id,
                address=address,
                status=s.status,
                match_state=s.match_state,
                config_state=s.config_state,
                distance_m=s.distance,
                description=s.description,
                olt_name=olt_name,
                olt_host=host,
                collected_at=s.collected_at,
            )
            records.append(rec)

        return records

    finally:
        try:
            olt.disconnect()
        except Exception:
            pass


def extract_all_ports_on_olt(
    olt_config: dict,
    max_slots: int = 17,
    max_ports: int = 16,
    skip_empty: bool = True,
) -> Dict[str, List[OntRecord]]:
    """Extract ONT records from all GPON ports on an OLT.

    Iterates frame=0, slot=0..max_slots-1, port=0..max_ports-1.
    Each port's records are keyed by 'F/S/P' in the result dict.
    Ports with zero ONTs are skipped when skip_empty=True.

    Args:
        olt_config: OLT config dict.
        max_slots: Max slots to scan (default 17 for MA5608T).
        max_ports: Max ports per slot (default 16).
        skip_empty: If True, skip ports returning 0 ONTs.

    Returns:
        Dict mapping 'frame/slot/port' -> list of OntRecord.
    """
    results: Dict[str, List[OntRecord]] = {}
    total = 0
    errors = 0

    for slot in range(max_slots):
        for port in range(max_ports):
            try:
                recs = extract_from_olt_port(
                    olt_config, "0", str(slot), str(port)
                )
                if skip_empty and not recs:
                    continue
                key = f"0/{slot}/{port}"
                results[key] = recs
                total += len(recs)
                logger.info(f"  {key}: {len(recs)} ONTs")
            except (ConnectionError, OSError, ValueError) as e:
                logger.warning(f"  ERROR 0/{slot}/{port}: {e}")
                errors += 1
                # If connection is lost, stop scanning
                if "blocked" in str(e) or "not reachable" in str(e):
                    logger.error("Connection lost, stopping scan")
                    break
            except Exception as e:
                logger.warning(f"  ERROR 0/{slot}/{port}: {e}")
                errors += 1

    logger.info(f"Total ONTs collected: {total}, errors: {errors}")
    return results


# ──────────────────────────────────────────────
# Export helpers
# ──────────────────────────────────────────────

def records_to_json(records: List[OntRecord], **kw) -> str:
    """Serialize a list of OntRecord to JSON string."""
    return json.dumps(
        [asdict(r) for r in records],
        ensure_ascii=False,
        indent=2,
        **kw,
    )


def write_json(records: List[OntRecord], path: str) -> str:
    """Write records to a JSON file. Returns the path."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(records_to_json(records))
    logger.info(f"Wrote {len(records)} records to {path}")
    return os.path.abspath(path)


def write_csv(
    records: List[OntRecord],
    path: str,
    delimiter: str = ",",
) -> str:
    """Write records to a CSV file. Returns the path."""
    if not records:
        logger.warning("No records to write")
        return ""

    fieldnames = [
        "ont_id", "address", "status", "match_state", "config_state",
        "distance_m", "description", "serial", "rx_power", "tx_power",
        "olt_name", "olt_host", "collected_at",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        for r in records:
            row = asdict(r)
            # Ensure only declared fields
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    logger.info(f"Wrote {len(records)} records to {path}")
    return os.path.abspath(path)


def summary_stats(records: List[OntRecord]) -> dict:
    """Compute summary statistics from records."""
    total = len(records)
    online = sum(1 for r in records if r.is_online)
    offline = total - online
    matched = sum(1 for r in records if r.is_match_ok)
    mismatched = sum(1 for r in records if r.is_mismatch)
    initial = sum(1 for r in records if r.match_state.lower() == "initial")
    unknown_state = sum(
        1 for r in records
        if r.match_state.lower() not in ("match", "mismatch", "mis-match", "initial", "")
    )
    return {
        "total": total,
        "online": online,
        "offline": offline,
        "match_state_match": matched,
        "match_state_mismatch": mismatched,
        "match_state_initial": initial,
        "match_state_unknown": unknown_state,
    }


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main_cli(args: Optional[List[str]] = None) -> int:
    """CLI entry point for data extraction."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract ONT records with match state from DB or OLT",
    )
    parser.add_argument("--from-db", action="store_true",
                        help="Extract from SQLite diagnoses.db")
    parser.add_argument("--from-olt", metavar="OLT_NAME",
                        help="Extract from OLT by name or host")
    parser.add_argument("--olt-config", default="config.yaml",
                        help="Path to config.yaml with OLT list")
    parser.add_argument("--port", metavar="F/S/P",
                        help="GPON port address (e.g. 0/0/4) for OLT extraction")
    parser.add_argument("--all-ports", action="store_true",
                        help="Scan all GPON ports on the OLT (may be slow)")
    parser.add_argument("--olt-name", help="Filter DB results by OLT name")
    parser.add_argument("--olt-host", help="Filter DB results by OLT host")
    parser.add_argument("--address", help="Filter DB results by ONT address")
    parser.add_argument("--status", choices=["online", "offline"],
                        help="Filter by ONT status (DB only)")
    parser.add_argument("--limit", type=int, default=500,
                        help="Max records (default 500)")
    parser.add_argument("--output", "-o", default="",
                        help="Output file path (auto-format by extension)")
    parser.add_argument("--format", choices=["json", "csv"], default="json",
                        help="Output format (default: json)")
    parser.add_argument("--stats", action="store_true",
                        help="Print summary statistics only")
    parser.add_argument("--db-path",
                        help="Explicit path to diagnoses.db")

    opts = parser.parse_args(args)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    records: List[OntRecord] = []

    if opts.from_db:
        records = extract_from_db(
            db_path=opts.db_path,
            olt_name=opts.olt_name,
            olt_host=opts.olt_host,
            ont_address=opts.address,
            status_filter=opts.status,
            limit=opts.limit,
        )
        print(f"Извлечено {len(records)} записей из БД diagnoses.db")

    elif opts.from_olt:
        import yaml
        config_path = opts.olt_config
        if not os.path.exists(config_path):
            print(f"Ошибка: конфиг не найден: {config_path}", file=sys.stderr)
            return 1
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Find OLT config by name or host
        olt_cfg = None
        for olt in config.get("olts", []):
            if olt.get("name") == opts.from_olt or olt.get("host") == opts.from_olt:
                olt_cfg = olt
                break
        if not olt_cfg:
            print(f"Ошибка: OLT '{opts.from_olt}' не найден в конфиге",
                  file=sys.stderr)
            return 1

        if opts.all_ports:
            print(f"Сканирование всех портов на {olt_cfg.get('name', olt_cfg['host'])}..."
                  " Это может занять время.")
            port_results = extract_all_ports_on_olt(olt_cfg)
            for port_key, recs in port_results.items():
                records.extend(recs)
            print(f"Всего ONT: {len(records)}")
        elif opts.port:
            parts = opts.port.split("/")
            if len(parts) != 3 or not all(p.isdigit() for p in parts):
                print("Ошибка: формат порта — F/S/P (например, 0/0/4)",
                      file=sys.stderr)
                return 1
            frame, slot, port = parts
            print(f"Извлечение ONT с порта {frame}/{slot}/{port}...")
            records = extract_from_olt_port(olt_cfg, frame, slot, port)
            print(f"Получено {len(records)} ONT")
        else:
            print("Ошибка: укажите --port F/S/P или --all-ports",
                  file=sys.stderr)
            return 1

    else:
        parser.print_help()
        return 0

    if opts.stats:
        stats = summary_stats(records)
        print()
        print("=== Сводка ===")
        print(f"  Всего ONT:            {stats['total']}")
        print(f"  Online:               {stats['online']}")
        print(f"  Offline:              {stats['offline']}")
        print(f"  Match state 'match':   {stats['match_state_match']}")
        print(f"  Match state 'mismatch': {stats['match_state_mismatch']}")
        print(f"  Match state 'initial':  {stats['match_state_initial']}")
        print(f"  Unknown state:         {stats['match_state_unknown']}")

    if opts.output:
        ext = Path(opts.output).suffix.lower()
        if ext == ".json" or (not ext and opts.format == "json"):
            write_json(records, opts.output)
        elif ext == ".csv" or (not ext and opts.format == "csv"):
            write_csv(records, opts.output)
        else:
            print(f"Неизвестный формат: {ext}", file=sys.stderr)
            return 1
    elif not opts.stats and records:
        # Print to stdout
        if opts.format == "json":
            print(records_to_json(records))
        elif opts.format == "csv":
            import io
            buf = io.StringIO()
            fieldnames = [
                "ont_id", "address", "status", "match_state", "config_state",
                "distance_m", "description", "serial", "rx_power", "tx_power",
                "olt_name", "olt_host", "collected_at",
            ]
            writer = csv.DictWriter(buf, fieldnames=fieldnames)
            writer.writeheader()
            for r in records:
                row = asdict(r)
                writer.writerow({k: row.get(k, "") for k in fieldnames})
            print(buf.getvalue())

    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
