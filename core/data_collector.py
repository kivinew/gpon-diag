"""ONT data collection commands for Huawei MA5600 series OLTs."""

import logging
import re
import time
from typing import Dict, Optional

from core.parser import parse_ont_info_summary

logger = logging.getLogger(__name__)


class OntDataCollector:
    """Collects ONT data from OLT using telnet session."""

    def __init__(self, session: 'TelnetSession'):
        self.session = session

    def collect_ont(self, frame: str, slot: str, port: str, ont_id: str, log=None) -> Dict:
        """
        Collect all ONT data with parameter validation.

        Args:
            frame, slot, port, ont_id: ONT address components (must be digits)
            log: Optional logging callback

        Returns:
            Dictionary with raw command outputs

        Raises:
            ValueError: If parameters are invalid
            OntNotFoundError: If ONT does not exist
        """
        _log = log or (lambda msg, end=" ", flush=True: print(msg, end=end, flush=flush))
        self.session._drain_socket()

        for param_name, param_value in [("frame", frame), ("slot", slot),
                                       ("port", port), ("ont_id", ont_id)]:
            if not re.fullmatch(r'\d+', param_value):
                raise ValueError(f"Invalid {param_name}: {param_value}")

        results = {}

        _log("  ont info...")
        results["ont_info"] = self.session.send_command(
            f"display ont info {frame} {slot} {port} {ont_id}", max_more=0
        )
        _log("OK")

        if "The required ONT does not exist" in results["ont_info"]:
            from core.olt import OntNotFoundError
            raise OntNotFoundError(f"ONT {frame}/{slot}/{port}/{ont_id} not found on OLT")

        status_match = re.search(r"Run state\s*: *(.+)", results["ont_info"])
        is_online = status_match and "online" in status_match.group(1).lower()
        if not is_online:
            _log("  ONT offline, skipping other commands")
            _log("  register-info...")
            results["register_info"] = self.session.send_command(
                f"display ont register-info {frame} {slot} {port} {ont_id}", max_more=-1
            )
            _log("OK")
            return results

        _log("  ont version...")
        results["ont_version"] = self.session.send_command(
            f"display ont version {frame} {slot} {port} {ont_id}", max_more=0
        )
        _log("OK")

        _log("  optical-info...")
        self.session._gpon_ctx(frame, slot)
        results["optical_info"] = self.session.send_command(
            f"display ont optical-info {port} {ont_id}", max_more=-1
        )
        self.session._quit_gpon()
        _log("OK")

        _log("  line-quality...")
        results["line_quality"] = self.session.send_command(
            f"display statistics ont-line-quality {frame} {slot} {port} {ont_id}", max_more=0
        )
        _log("OK")

        _log("  port state...")
        results["lan_ports"] = self.session.send_command(
            f"display ont port state {frame} {slot} {port} {ont_id} eth-port all", max_more=-1
        )
        _log("OK")

        for lan_id in range(1, 5):
            _log(f"  eth-errors {lan_id}...")
            results[f"eth_errors_raw_{lan_id}"] = self.session.send_command(
                f"display statistics ont-eth {frame} {slot} {port} {ont_id} ont-port {lan_id}", max_more=0
            )
            _log("OK")

        _log("  mac-address...")
        mac_raw = self.session.send_command(
            f"display mac-address ont {frame}/{slot}/{port} {ont_id}", max_more=-1
        )
        results["mac_addresses"] = mac_raw
        _log(f"OK ({mac_raw.count(chr(10))} lines)")

        _log("  wan-info...")
        results["wan_info"] = self.session.send_command(
            f"display ont wan-info {frame} {slot} {port} {ont_id}", max_more=-1
        )
        _log("OK")

        _log("  ipconfig...")
        results["ipconfig"] = self.session.send_command(
            f"display ont ipconfig {frame} {slot} {port} {ont_id}", max_more=0
        )
        _log("OK")

        _log("  register-info...")
        results["register_info"] = self.session.send_command(
            f"display ont register-info {frame} {slot} {port} {ont_id}", max_more=-1
        )
        _log("OK")

        return results

    def collect_port_summary(self, frame: str, slot: str, port: str, log=None) -> list:
        """
        Collect 'display ont info summary' for all ONTs on a GPON port.

        Returns list of OntSummary objects.
        """
        _log = log or (lambda msg, end=" ", flush=True: print(msg, end=end, flush=flush))

        for param_name, param_value in [("frame", frame), ("slot", slot), ("port", port)]:
            if not re.fullmatch(r'\d+', param_value):
                raise ValueError(f"Invalid {param_name}: {param_value}")

        self.session._drain_socket()

        _log("  port summary...")
        output = self.session.send_command(
            f"display ont info summary {frame} {slot} {port}", max_more=-1
        )
        _log("OK")

        summaries = parse_ont_info_summary(output)
        _log(f"  parsed {len(summaries)} ONTs")
        return summaries

    def clear_line_quality(self, frame: str, slot: str, port: str, ont_id: str):
        """Clear line quality statistics for an ONT."""
        self.session._gpon_ctx(frame, slot)
        self.session.send_command(f"clear statistics ont-line-quality {port} {ont_id}", max_more=0)
        self.session._quit_gpon()

    def reset_lan_port(self, frame: str, slot: str, port: str, ont_id: str, lan_id: int):
        """Reset a LAN port on an ONT."""
        self.session._gpon_ctx(frame, slot)
        self.session.send_command(f"ont port attribute {port} {ont_id} eth {lan_id} operational-state off", max_more=0)
        time.sleep(0.5)
        self.session.send_command(f"ont port attribute {port} {ont_id} eth {lan_id} operational-state on", max_more=0)
        self.session._quit_gpon()

    def clear_eth_errors(self, frame: str, slot: str, port: str, ont_id: str, lan_id: int):
        """Clear Ethernet error counters for a LAN port."""
        self.session._gpon_ctx(frame, slot)
        self.session.send_command(f"clear statistics ont-eth {port} {ont_id} ont-port {lan_id}", max_more=0)
        self.session._quit_gpon()

    def remote_ping(self, frame: str, slot: str, port: str, ont_id: str, ip: str = "1.1.1.1") -> str:
        """Perform remote ping from ONT."""
        self.session._gpon_ctx(frame, slot)
        self.session._write(f"ont remote-ping {port} {ont_id} ip-address {ip}\r")
        time.sleep(8)
        output = self.session._read_to_prompt(5)
        self.session._quit_gpon()
        return output

    def find_ont_by_sn(self, serial: str) -> Optional[Dict]:
        """Find ONT by serial number."""
        output = self.session.send_command(f"display ont info by-sn {serial}", max_more=-1)
        return self._parse_fsp(output)

    def find_ont_by_description(self, description: str) -> Optional[Dict]:
        """Find ONT by description."""
        value = description
        if description.isdigit() and 5 <= len(description) <= 16:
            value = f"fl_{description}"
        output = self.session.send_command(f"display ont info by-desc {value}", max_more=-1)
        result = self._parse_fsp(output)
        if not result:
            time.sleep(1)
            output = self.session.send_command(f"display ont info by-desc {value}", max_more=-1)
            result = self._parse_fsp(output)
        return result

    @staticmethod
    def _parse_fsp(output: str) -> Optional[Dict]:
        """Parse F/S/P/ONT from OLT output."""
        lines = output.strip().split('\n')
        fsp_val = oid_val = None
        for line in lines:
            if not line.strip():
                fsp_val = oid_val = None
                continue
            # Table format: "0/ 0/6 0 fl_102693"
            m = re.search(r'(\d+)\s*/\s*(\d+)\s*/\s*(\d+)\s+(\d+)', line)
            if m:
                return {"frame": m.group(1), "slot": m.group(2), "port": m.group(3), "ont_id": m.group(4)}
            # Key-value format across lines
            fsp_m = re.search(r"F/S/P\s*:\s*([\d/]+)", line)
            oid_m = re.search(r"ONT-ID\s*:\s*(\d+)", line)
            if fsp_m:
                fsp_val = fsp_m.group(1)
            if oid_m:
                oid_val = oid_m.group(1)
            if fsp_val and oid_val:
                parts = fsp_val.split("/")
                if len(parts) == 3:
                    return {"frame": parts[0], "slot": parts[1], "port": parts[2], "ont_id": oid_val}
        return None