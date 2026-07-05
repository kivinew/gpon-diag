"""Flask web interface for GPON diagnostics."""

import os
import json
import sys
import queue
import threading
import time
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

from flask import Flask, render_template, request, redirect, url_for, flash, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

# Orchestrator imports
from orchestrator.task_card import TaskCard, TaskStatus, load_task_card, list_task_cards
from orchestrator.agent_registry import AgentRegistry, AgentStatus

# Orchestrator outer loop imports
from orchestrator.outer_loop import ValidationResult

# Core utils and constants
from core.utils import parse_input, sanitize_ont_param, load_olt_credentials
from core.constants import TZ_LOCAL
from core.olt import OntNotFoundError, get_olt_connection, close_all
from core.thresholds import Thresholds
from core.parser import parse_ont_info, parse_optical_info, parse_line_quality
from core.models import OntMetrics
from core.config_parser import _build_thresholds, load_config
from core.diagnose_logic import run_diagnosis
from core.connection_diagnosis import find_available_olt

app = Flask(__name__)
app.debug = False
app.config["SECRET_KEY"] = os.urandom(24)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "diagnoses.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class Diagnosis(db.Model):
    __tablename__ = "diagnoses"
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.String, nullable=False)
    olt_host = db.Column(db.String, nullable=False)
    olt_name = db.Column(db.String, nullable=False, default="")
    ont_address = db.Column(db.String, nullable=False)
    input_type = db.Column(db.String, nullable=False)
    input_value = db.Column(db.String, nullable=False)
    report_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(TZ_LOCAL))


class PortSnapshot(db.Model):
    """Snapshot of all ONTs on a GPON port collected via 'display ont info summary'."""
    __tablename__ = "port_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.String, nullable=False)
    olt_name = db.Column(db.String, nullable=False)
    olt_host = db.Column(db.String, nullable=False)
    frame = db.Column(db.String, nullable=False)
    slot = db.Column(db.String, nullable=False)
    port = db.Column(db.String, nullable=False)
    ont_count = db.Column(db.Integer, nullable=False, default=0)
    data_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(TZ_LOCAL))

with app.app_context():
    db.create_all()
    # olt_name column added; Alembic migrations planned for future schema changes

def build_thresholds(config):
    return _build_thresholds(config)


def find_olt_by_host(config, host):
    for olt in config.get("olts", []):
        if olt.get("host") == host:
            return olt
    return None

@app.route("/api/diagnose", methods=["POST"])
def api_diagnose():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    olt_host = data.get("olt_host", "").strip()

    if not query:
        return {"error": "Введите запрос."}, 400

    config = load_config()

    if olt_host:
        olt_config = find_olt_by_host(config, olt_host)
        if not olt_config:
            return {"error": f"OLT {olt_host} не найден."}, 400
    else:
        olt_config = find_available_olt(config)
        if not olt_config:
            return {"error": "Нет доступных OLT."}, 400

    log_q = queue.Queue()

    def log_fn(msg, end=" ", flush=True):
        text = str(msg)
        print(text, flush=flush)
        log_q.put(text)

    def worker():
        with app.app_context():
            try:
                # First, search for historical results (in try block to avoid breaking diagnosis)
                input_data = parse_input(query)
                ont_address = None
                search_terms = []

                if input_data["type"] == "address":
                    ont_address = f"{input_data['frame']}/{input_data['slot']}/{input_data['port']}/{input_data['ont_id']}"
                    search_terms.append(ont_address)
                elif input_data["type"] == "serial":
                    search_terms.append(input_data["value"])
                elif input_data["type"] == "description":
                    search_terms.append(input_data["value"])

                # Query history before running diagnosis
                if search_terms:
                    try:
                        conditions = []
                        for term in search_terms:
                            conditions.append(Diagnosis.ont_address.contains(term))
                            conditions.append(Diagnosis.input_value.contains(term))
                        if conditions:
                            history_records = Diagnosis.query.filter(
                                db.or_(*conditions)
                            ).order_by(Diagnosis.created_at.desc()).limit(10).all()
                        else:
                            history_records = []

                        history_results = []
                        for record in history_records:
                            try:
                                report_data = json.loads(record.report_json) if record.report_json else {}
                            except (json.JSONDecodeError, TypeError):
                                report_data = {}
                            history_results.append({
                                "id": record.id,
                                "created_at": record.created_at.strftime("%d.%m.%Y %H:%M"),
                                "olt_name": record.olt_name,
                                "ont_address": record.ont_address,
                                "report": report_data,
                            })

                        if history_results:
                            log_q.put({"type": "history", "history": history_results})
                    except Exception as hist_err:
                        logger.warning(f"History search failed: {hist_err}")

                thresholds = build_thresholds(config)

                def on_olt_info(info):
                    log_q.put({"type": "olt_info", "model": info["model"],
                               "uptime": info["uptime"], "version": info["version"]})

                report = run_diagnosis(input_data, olt_config, thresholds,
                                       allow_actions=False, log=log_fn,
                                       ping_target=config.get("ping_target", "1.1.1.1"),
                                       on_olt_info=on_olt_info)

                diag = Diagnosis(
                    timestamp=report.timestamp,
                    olt_host=olt_config.get("host", ""),
                    olt_name=olt_config.get("name", ""),
                    ont_address=report.metrics.address,
                    input_type=input_data["type"],
                    input_value=(input_data.get("value")
                                 if input_data["type"] != "address"
                                 else f"{input_data['frame']}/{input_data['slot']}/{input_data['port']}/{input_data['ont_id']}"),
                    report_json=json.dumps(report.to_dict(), ensure_ascii=False),
                )
                db.session.add(diag)
                db.session.commit()

                log_q.put({"type": "result", "report": report.to_text()})

            except OntNotFoundError:
                olt_label = olt_config.get("name", olt_config.get("host", ""))
                olt_ip = olt_config.get("host", "")
                msg = f"На головной станции {olt_label} ({olt_ip}) терминал {query} не обнаружен."
                log_q.put({"type": "error", "message": msg})
            except (TimeoutError, OSError) as exc:
                olt_label = olt_config.get("name", olt_config.get("host", ""))
                olt_ip = olt_config.get("host", "")
                msg = f"Не удалось подключиться к головной станции {olt_label} ({olt_ip}). Проверьте доступность: {exc}"
                log_q.put({"type": "error", "message": msg})
            except Exception as exc:
                import traceback
                logger.exception(f"Diagnosis error for {query}: {exc}")
                log_q.put({"type": "error", "message": f"{exc}\n{traceback.format_exc()}"})
            finally:
                log_q.put(None)

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    def generate():
        while True:
            try:
                item = log_q.get(timeout=120)
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Таймаут подключения к головной станции.'})}\n\n"
                return
            if item is None:
                return
            if isinstance(item, dict):
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'log', 'line': str(item)}, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/", methods=["GET"])
def index():
    config = load_config()
    olts = config.get("olts", [])
    history = Diagnosis.query.order_by(Diagnosis.created_at.desc()).limit(20).all()
    return render_template("index.html", olts=olts, history=history)

@app.route("/dashboard", methods=["GET"])
def dashboard():
    config = load_config()
    olts = config.get("olts", [])
    history_raw = Diagnosis.query.order_by(Diagnosis.created_at.desc()).limit(20).all()
    # Pre-parse report_json for template compatibility
    history = []
    for h in history_raw:
        try:
            import json
            report = json.loads(h.report_json) if h.report_json else {}
        except (json.JSONDecodeError, TypeError):
            report = {}
        history.append({
            'id': h.id,
            'created_at': h.created_at,
            'olt_name': h.olt_name,
            'olt_host': h.olt_host,
            'ont_address': h.ont_address,
            'input_value': h.input_value,
            'report': report
        })
    return render_template("dashboard.html", olts=olts, history=history)

# Simple health-check endpoint for diagnostics
@app.route("/ping", methods=["GET"])
def ping():
    return {"status": "ok"}

@app.route("/api/search", methods=["POST"])
def api_search():
    """Search for ONTs by serial, address, or description across OLT(s)."""
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    olt_host = data.get("olt_host", "").strip()

    if not query:
        return {"error": "Введите запрос для поиска."}, 400

    config = load_config()
    olts_to_search = []

    if olt_host:
        olt_config = find_olt_by_host(config, olt_host)
        if not olt_config:
            return {"error": f"OLT {olt_host} не найден."}, 400
        olts_to_search = [olt_config]
    else:
        olts_to_search = config.get("olts", [])

    # Search across all OLTs
    all_results = []
    for olt_config in olts_to_search:
        host = olt_config["host"]
        port = olt_config.get("port", 23)
        username, password = _load_olt_credentials(olt_config)
        if not username or not password:
            continue

        try:
            olt = get_olt_connection(host, port, username, password, 15)
            if olt._skip_disconnect or olt._sock is None:
                logger.warning(f"Skipping unavailable OLT {host} in search")
                continue  # Try next OLT
            try:
                olt.connect()
            except Exception as conn_err:
                logger.warning(f"Connect failed to {host}: {conn_err}")
                continue  # Try next OLT
            # Wait for connection to stabilize after login
            time.sleep(1)

            # Parse query type
            input_data = parse_input(query)

            if input_data["type"] == "serial":
                loc = olt.find_ont_by_sn(input_data["value"])
                if loc:
                    input_data.update(loc)
            elif input_data["type"] == "address":
                # Already have frame/slot/port/ont_id
                pass
            elif input_data["type"] == "description":
                loc = olt.find_ont_by_description(input_data["value"])
                if loc:
                    input_data.update(loc)

            # If we have address, collect basic info
            if "frame" in input_data and "slot" in input_data and "port" in input_data and "ont_id" in input_data:
                # Quick collect basic info
                raw_data = olt.collect_ont(
                    sanitize_ont_param(input_data["frame"]),
                    sanitize_ont_param(input_data["slot"]),
                    sanitize_ont_param(input_data["port"]),
                    sanitize_ont_param(input_data["ont_id"]),
                    log=lambda *a, **k: None
                )

                metrics = OntMetrics()
                metrics.address = f"{input_data['frame']}/{input_data['slot']}/{input_data['port']}/{input_data['ont_id']}"
                metrics.frame = input_data["frame"]
                metrics.slot = input_data["slot"]
                metrics.port = input_data["port"]
                metrics.ont_id = input_data["ont_id"]

                if "ont_info" in raw_data:
                    parse_ont_info(raw_data["ont_info"], metrics)
                if "optical_info" in raw_data:
                    parse_optical_info(raw_data["optical_info"], metrics)

                all_results.append({
                    "ont_address": metrics.address,
                    "olt_host": host,
                    "olt_name": olt_config.get("name", host),
                    "serial": metrics.serial,
                    "description": metrics.description,
                    "is_online": metrics.is_online,
                    "model": metrics.model,
                    "ont_rx_power": metrics.ont_rx_power,
                    "olt_rx_power": metrics.olt_rx_power,
                    "distance_m": metrics.distance_m
                })

        except Exception as e:
            logger.warning(f"Search failed on {host}: {e}")
            continue

    return {"results": all_results}

@app.route("/api/optics", methods=["GET"])
def api_optics():
    """Get real-time optics data for a specific ONT."""
    address = request.args.get("address", "").strip()
    olt_host = request.args.get("olt_host", "").strip()

    if not address or not olt_host:
        return {"error": "Укажите адрес ONT и OLT."}, 400

    config = load_config()
    olt_config = find_olt_by_host(config, olt_host)
    if not olt_config:
        return {"error": f"OLT {olt_host} не найден."}, 400

    host = olt_config["host"]
    port = olt_config.get("port", 23)
    username, password = _load_olt_credentials(olt_config)
    if not username or not password:
        return {"error": "Нет учетных данных для OLT."}, 400

    # Parse address F/S/P/ONT
    parts = address.split("/")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        return {"error": "Неверный формат адреса. Ожидается F/S/P/ONT."}, 400

    frame, slot, port_, ont_id = parts

    try:
        olt = get_olt_connection(host, port, username, password, 15)
        try:
            olt.connect()
        except Exception as conn_err:
            return {"error": f"OLT {olt_host} временно недоступен: {conn_err}. Выберите другой OLT."}, 503

        raw_data = olt.collect_ont(
            sanitize_ont_param(frame),
            sanitize_ont_param(slot),
            sanitize_ont_param(port_),
            sanitize_ont_param(ont_id),
            log=lambda *a, **k: None
        )

        metrics = OntMetrics()
        metrics.address = address
        metrics.frame = frame
        metrics.slot = slot
        metrics.port = port_
        metrics.ont_id = ont_id

        if "optical_info" in raw_data:
            parse_optical_info(raw_data["optical_info"], metrics)
        if "ont_info" in raw_data:
            parse_ont_info(raw_data["ont_info"], metrics)
        if "line_quality" in raw_data:
            parse_line_quality(raw_data["line_quality"], metrics)

        return {
            "ont_rx_power": metrics.ont_rx_power,
            "olt_rx_power": metrics.olt_rx_power,
            "ont_tx_power": metrics.ont_tx_power,
            "laser_bias_current": metrics.laser_bias_current,
            "ont_temperature": metrics.ont_temperature,
            "supply_voltage": metrics.supply_voltage,
            "distance_m": metrics.distance_m,
            "upstream_errors": metrics.upstream_errors,
            "downstream_errors": metrics.downstream_errors,
            "total_bip_errors": metrics.total_bip_errors,
            "is_online": metrics.is_online,
            "model": metrics.model,
            "serial": metrics.serial,
            "description": metrics.description
        }

    except Exception as e:
        logger.exception(f"Optics fetch error: {e}")
        return {"error": str(e)}, 500

@app.route("/api/reset-connections", methods=["POST"])
def api_reset_connections():
    """Reset all OLT connections in the pool (useful when switching OLT or on connection errors)."""
    close_all()
    return {"status": "connections reset"}

@app.route("/api/history/<int:diag_id>", methods=["GET"])
def api_history_detail(diag_id):
    """Return a single diagnosis record by ID."""
    record = Diagnosis.query.get(diag_id)
    if not record:
        return {"error": "Запись не найдена."}, 404
    try:
        report_data = json.loads(record.report_json) if record.report_json else {}
    except (json.JSONDecodeError, TypeError):
        report_data = {}
    return {
        "id": record.id,
        "timestamp": record.timestamp,
        "created_at": record.created_at.strftime("%d.%m.%Y %H:%M"),
        "olt_name": record.olt_name,
        "olt_host": record.olt_host,
        "ont_address": record.ont_address,
        "input_type": record.input_type,
        "input_value": record.input_value,
        "report": report_data,
        "is_online": report_data.get("is_online", True),
    }


@app.route("/api/history", methods=["GET"])
def api_history():
    """Search historical diagnosis results by ONT address, serial, or description.
    If no query provided, returns all history (limited)."""
    query = request.args.get("q", "").strip()
    limit = request.args.get("limit", 20, type=int)

    q = Diagnosis.query
    if query:
        q = q.filter(
            db.or_(
                Diagnosis.ont_address.contains(query),
                Diagnosis.input_value.contains(query),
            )
        )

    history_records = q.order_by(Diagnosis.created_at.desc()).limit(limit).all()

    results = []
    for record in history_records:
        try:
            report_data = json.loads(record.report_json) if record.report_json else {}
        except (json.JSONDecodeError, TypeError):
            report_data = {}
        results.append({
            "id": record.id,
            "timestamp": record.timestamp,
            "created_at": record.created_at.strftime("%d.%m.%Y %H:%M"),
            "olt_name": record.olt_name,
            "olt_host": record.olt_host,
            "ont_address": record.ont_address,
            "input_type": record.input_type,
            "input_value": record.input_value,
            "report": report_data,
            "is_online": report_data.get("is_online", True),
        })

    return {"history": results}


@app.route("/orchestrator", methods=["GET"])
def orchestrator_index():
    from orchestrator.agent_registry import AgentRegistry
    from orchestrator.task_card import TaskStatus
    registry = AgentRegistry()
    agents = registry.list_all()
    return render_template("orchestrator/index.html", agents=agents)


@app.route("/orchestrator/tasks", methods=["GET"])
def orchestrator_tasks():
    from orchestrator.task_card import list_task_cards, TaskStatus
    cards = list_task_cards()
    tasks = []
    for c in cards:
        tasks.append({
            "task_id": c.task_id,
            "title": c.title,
            "agent_id": c.agent_id,
            "status": c.status.value,
            "zone": c.zone,
            "revision_count": c.revision_count,
            "errors": c.errors,
        })
    return {"tasks": tasks}


@app.route("/orchestrator/agents", methods=["GET"])
def orchestrator_agents():
    from orchestrator.agent_registry import AgentRegistry, AgentStatus
    registry = AgentRegistry()
    agents = registry.list_all()
    agent_data = []
    for aid, info in agents.items():
        agent_data.append({
            "agent_id": info.agent_id,
            "zone": info.zone,
            "status": info.status.value,
            "files_intended": info.files_intended,
            "error_message": info.error_message,
        })
    return {"agents": agent_data}


@app.route("/orchestrator/verify", methods=["POST"])
def orchestrator_verify():
    from orchestrator.external_control import ExternalControlLoop
    from orchestrator.agent_registry import AgentRegistry
    task_id = request.json.get("task_id")
    loop = ExternalControlLoop(os.path.dirname(os.path.dirname(__file__)), AgentRegistry())
    result = loop.verify_and_update(task_id)
    return {"success": result.success, "errors": result.errors, "warnings": result.warnings}


@app.route("/orchestrator/create_task", methods=["POST"])
def orchestrator_create_task():
    from orchestrator.task_card import create_task_card
    data = request.json or {}
    card = create_task_card(
        title=data.get("title", ""),
        description=data.get("description", ""),
        zone=data.get("zone", "model"),
        verification_criteria=data.get("criteria", []),
        metadata=data.get("metadata"),
    )
    return {"task_id": card.task_id, "status": card.status.value}


@app.route("/orchestrator/set_status", methods=["POST"])
def orchestrator_set_status():
    from orchestrator.task_card import load_task_card, TaskStatus
    task_id = request.json.get("task_id")
    status_val = request.json.get("status")
    card = load_task_card(task_id)
    if not card:
        return {"error": "Task not found"}, 404
    card.status = TaskStatus(status_val)
    card.agent_id = request.json.get("agent_id", "")
    card.save()
    return {"task_id": task_id, "status": card.status.value}


@app.route("/api/port-monitor", methods=["POST"])
def api_port_monitor():
    """SSE endpoint for port monitoring - collects 'display ont info summary' for all ONTs on a GPON port.
    Runs in background thread parallel to main diagnosis.
    """
    data = request.get_json(silent=True) or {}
    address = data.get("address", "").strip()
    olt_host = data.get("olt_host", "").strip()

    if not address or not olt_host:
        return {"error": "Укажите адрес ONT (F/S/P/ONT) и OLT."}, 400

    config = load_config()
    olt_config = find_olt_by_host(config, olt_host)
    if not olt_config:
        return {"error": f"OLT {olt_host} не найден."}, 400

    parts = address.split("/")
    if len(parts) != 4:
        return {"error": "Неверный формат адреса. Ожидается F/S/P/ONT."}, 400
    frame, slot, port, ont_id = parts

    host = olt_config["host"]
    port_num = olt_config.get("port", 23)
    username, password = _load_olt_credentials(olt_config)
    if not username or not password:
        return {"error": "Нет учетных данных для OLT."}, 400

    log_q = queue.Queue()

    def log_fn(msg, end=" ", flush=True):
        text = str(msg)
        print(text, flush=flush)
        log_q.put(text)

    def worker():
        with app.app_context():
            try:
                # Get SECOND connection from pool (index 1) - parallel to main diagnosis
                monitor_conn = get_olt_connection(
                    host, port_num, username, password, 30, pool_index=1
                )
                if not monitor_conn._connected and not monitor_conn._skip_disconnect:
                    try:
                        monitor_conn.connect()
                    except Exception as conn_err:
                        logger.warning(f"Port monitor conn failed, using fallback OLT: {conn_err}")
                        # Fallback: try another OLT from config
                        for alt_olt in config.get("olts", []):
                            if alt_olt.get("host") == olt_config.get("host"):
                                continue
                            try:
                                monitor_conn = get_olt_connection(
                                    alt_olt["host"], alt_olt.get("port", 23),
                                    _load_olt_credentials(alt_olt)[0],
                                    password, 30, pool_index=1
                                )
                                break
                            except Exception:
                                continue

                log_fn("  port summary...")
                summaries = monitor_conn.collect_port_summary(
                    sanitize_ont_param(frame),
                    sanitize_ont_param(slot),
                    sanitize_ont_param(port),
                    log=log_fn
                )
                log_fn("OK")

                from core.models import OntSummary
                snapshot_data = []
                for s in summaries:
                    snapshot_data.append({
                        "ont_id": s.ont_id,
                        "status": s.status,
                        "rx_power": s.rx_power,
                        "tx_power": s.tx_power,
                        "distance": s.distance,
                        "last_down_cause": s.last_down_cause,
                        "description": s.description,
                        "collected_at": s.collected_at or datetime.now().isoformat(),
                        "is_online": s.is_online,
                        "rx_power_status": s.rx_power_status
                    })

                log_q.put({"type": "result", "summaries": snapshot_data, "count": len(snapshot_data)})

                snapshot = PortSnapshot(
                    timestamp=datetime.now(TZ_LOCAL).strftime("%Y-%m-%d %H:%M:%S"),
                    olt_name=olt_config.get("name", host),
                    olt_host=host,
                    frame=frame,
                    slot=slot,
                    port=port,
                    ont_count=len(snapshot_data),
                    data_json=json.dumps(snapshot_data, ensure_ascii=False)
                )
                db.session.add(snapshot)
                db.session.commit()
                log_fn("  snapshot saved")

                monitor_conn.disconnect()

            except Exception as exc:
                import traceback
                logger.exception(f"Port monitor error: {exc}")
                log_q.put({"type": "error", "message": f"{exc}\n{traceback.format_exc()}"})
            finally:
                log_q.put(None)

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    def generate():
        while True:
            try:
                item = log_q.get(timeout=60)
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Таймаут сбора данных порта.'})}\n\n"
                return
            if item is None:
                return
            if isinstance(item, dict):
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'log', 'line': str(item)}, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ===== Orchestrator Agent API =====

@app.route("/orchestrator/api/agent/tasks", methods=["POST"])
def orchestrator_agent_tasks():
    """Return pending tasks assigned to a specific agent or zone."""
    data = request.get_json(silent=True) or {}
    agent_id = data.get("agent_id", "").strip()
    zone = data.get("zone", "").strip()

    if not agent_id and not zone:
        return {"error": "Укажите agent_id или zone."}, 400

    tasks = list_task_cards()
    matching = []
    for tc in tasks:
        if tc.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
            if tc.agent_id == agent_id or (zone and tc.zone == zone):
                matching.append({
                    "task_id": tc.task_id,
                    "title": tc.title,
                    "description": tc.description,
                    "zone": tc.zone,
                    "files_intended": tc.metadata.get("files_intended", []),
                    "validation_criteria": tc.verification_criteria,
                    "metadata": tc.metadata,
                    "status": tc.status.value,
                })

    return {"tasks": matching}


@app.route("/orchestrator/api/agent/complete", methods=["POST"])
def orchestrator_agent_complete():
    """Mark a task as completed by an agent."""
    data = request.get_json(silent=True) or {}
    task_id = data.get("task_id", "").strip()
    agent_id = data.get("agent_id", "").strip()
    result = data.get("result", {})

    if not task_id:
        return {"error": "task_id обязателен."}, 400

    task_card = load_task_card(task_id)
    if not task_card:
        return {"error": f"Задача {task_id} не найдена."}, 404

    task_card.status = TaskStatus.IN_PROGRESS
    task_card.agent_id = agent_id
    task_card.result = result
    task_card.save()

    registry = AgentRegistry()
    registry.heartbeat(agent_id, AgentStatus.IDLE)

    return {"status": "accepted", "task_id": task_id}


@app.route("/orchestrator/api/agent/heartbeat", methods=["POST"])
def orchestrator_agent_heartbeat():
    """Receive heartbeat from an agent."""
    data = request.get_json(silent=True) or {}
    agent_id = data.get("agent_id", "").strip()
    status = data.get("status", "idle")

    if not agent_id:
        return {"error": "agent_id обязателен."}, 400

    try:
        status_enum = AgentStatus(status)
    except ValueError:
        return {"error": f"Неизвестный статус: {status}"}, 400

    registry = AgentRegistry()
    registry.heartbeat(agent_id, status_enum)

    return {"status": "ok"}


@app.route("/orchestrator/api/agent/result", methods=["POST"])
def orchestrator_agent_result():
    """Submit final result of a task execution."""
    data = request.get_json(silent=True) or {}
    task_id = data.get("task_id", "").strip()
    agent_id = data.get("agent_id", "").strip()
    success = data.get("success", False)
    output = data.get("output", "")
    errors = data.get("errors", [])

    if not task_id:
        return {"error": "task_id обязателен."}, 400

    task_card = load_task_card(task_id)
    if not task_card:
        return {"error": f"Задача {task_id} не найдена."}, 404

    task_card.status = TaskStatus.VERIFICATION_PENDING
    task_card.result = {"output": output, "success": success, "errors": errors}
    task_card.save()

    registry = AgentRegistry()
    if success:
        registry.set_status(agent_id, AgentStatus.COMPLETED)
    else:
        registry.set_status(agent_id, AgentStatus.ERROR, "; ".join(errors))

    return {"status": "result_received"}


if __name__ == "__main__":
    # Production server is started via scripts/check_and_start_server.py
    pass
