"""OLT connection manager — synchronous socket-based for Huawei MA5608T."""

import logging
import re
import select
import socket
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

MORE_PROMPT = "---- More ( Press 'Q' to break ) ----"

_olt_registry: Dict[str, 'OltConnection'] = {}


class OntNotFoundError(Exception):
    pass


def get_olt_connection(host: str, port: int = 23,
                       username: str = "", password: str = "",
                       timeout: int = 15) -> 'OltConnection':
    """Get or create singleton OLT connection."""
    key = f"{host}:{port}"
    if key not in _olt_registry:
        _olt_registry[key] = OltConnection(host, port, username, password, timeout)
    return _olt_registry[key]


def close_all():
    """Close all OLT connections."""
    for conn in _olt_registry.values():
        conn.disconnect()
    _olt_registry.clear()


def _strip_iac(data):
    """Remove telnet IAC sequences from data."""
    result = b""
    i = 0
    while i < len(data):
        if data[i] == 255 and i + 2 < len(data):
            i += 3
        else:
            result += bytes([data[i]])
            i += 1
    return result


class OltConnection:
    """Manages a single telnet connection to one OLT using synchronous sockets."""

    _banner_cache = ""  # Class-level cache for model info

    def __init__(self, host: str = "", port: int = 23,
                 username: str = "", password: str = "",
                 timeout: int = 15):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._connected = False

    def connect(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(self.timeout)
            self._sock.connect((self.host, self.port))
            # Accept telnet negotiations
            self._sock.sendall(b"\xff\xfb\x01\xff\xfb\x03")
            # Read banner and login prompts, cache banner for model detection
            banner = self._read_to_prompt(2)
            OltConnection._banner_cache = banner
            self._write(self.username + "\r")
            time.sleep(1)
            self._read_to_prompt(2)
            self._write(self.password + "\r")
            time.sleep(2)
            # Enter enable mode and config mode
            self._write("enable\r")
            self._read_to_prompt(2)
            self._write("config\r")
            self._read_to_prompt(2)
            self._drain_socket()
            self._connected = True
        except Exception as e:
            logger.error(f"Failed to connect to {self.host}:{self.port}: {e}")
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
            raise

    def get_olt_info(self) -> dict:
        """Get OLT model, uptime, and software version.
        The method extracts the model from the cached banner and, if possible,
        queries the OLT for version and uptime using the appropriate CLI commands.
        """
        model = uptime = version = ""
        # --------- Model extraction from banner ---------
        try:
            banner = OltConnection._banner_cache
            # Typical banner contains: "Huawei Integrated Access Software (MA5608T)"
            model_match = re.search(r"\bMA(\d{4})T?\b", banner, re.I)
            if model_match:
                model = f"MA{model_match.group(1)}"
        except Exception:
            logger.debug("Failed to parse model from banner", exc_info=True)
        # --------- Version extraction ---------
        try:
            version_output = self.send_command("display version", max_more=0)
            # Look for a line like: "Software Version : V200R019C00"
            version_match = re.search(r"Version\s*[:]?\s*([\w\.]+)", version_output, re.I)
            if version_match:
                version = version_match.group(1).strip()
        except Exception:
            logger.debug("Failed to retrieve OLT version", exc_info=True)
        # --------- Uptime extraction ---------
        try:
            uptime_output = self.send_command("display uptime", max_more=0)
            # Typical format: "Uptime is 5 days, 3 hours, 12 minutes"
            uptime_match = re.search(r"Uptime\s*[:]?\s*([\w ,]+)", uptime_output, re.I)
            if uptime_match:
                uptime = uptime_match.group(1).strip()
        except Exception:
            logger.debug("Failed to retrieve OLT uptime", exc_info=True)
        return {"model": model, "uptime": uptime, "version": version}

    def disconnect(self):
        if self._sock:
            try:
                self._sock.sendall(b"quit\r")
                time.sleep(0.3)
            except Exception:
                pass
            self._sock.close()
            self._sock = None
        self._connected = False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def _write(self, text):
        try:
            self._sock.sendall(text.encode("utf-8"))
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            logger.warning(f"Write failed ({e}), reconnecting...")
            self._connected = False
            self._sock = None
            self.connect()
            self._sock.sendall(text.encode("utf-8"))

    def _read_to_prompt(self, seconds=2):
        buf = b""
        deadline = time.time() + seconds
        while time.time() < deadline:
            ready = select.select([self._sock], [], [], 0.5)
            if ready[0]:
                try:
                    chunk = self._sock.recv(8192)
                    if chunk:
                        buf += _strip_iac(chunk)
                except (socket.timeout, ConnectionResetError, BrokenPipeError, OSError):
                    break
            text = buf.decode("utf-8", errors="ignore")
            lines = text.rstrip().split("\n")
            if lines:
                last = lines[-1].strip()
                if re.match(r'^\S+(?:\([^\n]+\))?[>#:]\s*$', last) or re.search(r'\}\s*:\s*$', last):
                    break
        return buf.decode("utf-8", errors="ignore")

    def send_command(self, command, max_more=0):
        try:
            self._write(command + "\r")
            output = self._read_to_prompt(5)
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            logger.warning(f"Command '{command}' failed ({e}), reconnecting...")
            self._connected = False
            self._sock = None
            self.connect()
            self._write(command + "\r")
            output = self._read_to_prompt(5)

        if MORE_PROMPT in output:
            if max_more == -1:
                while True:
                    self._write(" \r")
                    time.sleep(0.3)
                    chunk = self._read_to_prompt(2)
                    output += chunk
                    if MORE_PROMPT not in chunk:
                        break
            else:
                self._write("q\r")
                time.sleep(0.3)
                output += self._read_to_prompt(2)

        if re.search(r'\}\s*:\s*$', output.rstrip()):
            self._write("\r")
            time.sleep(0.5)
            output += self._read_to_prompt(5)

        return output

    def _gpon_ctx(self, frame, slot):
        self._drain_socket()
        self._write(f"interface gpon {frame}/{slot}\r")
        time.sleep(1)
        self._read_to_prompt(3)

    def _quit_gpon(self):
        self._write("quit\r")
        time.sleep(1)
        self._read_to_prompt(2)

    def _drain_socket(self):
        try:
            while True:
                ready = select.select([self._sock], [], [], 0.3)
                if ready[0]:
                    self._sock.recv(8192)
                else:
                    break
        except Exception:
            pass

    def collect_ont(self, frame, slot, port, ont_id, log=None):
        """Collect ONT data with parameter validation."""
        _log = log or (lambda msg, end=" ", flush=True: print(msg, end=end, flush=flush))
        self._drain_socket()

        for param_name, param_value in [("frame", frame), ("slot", slot),
                                       ("port", port), ("ont_id", ont_id)]:
            if not re.fullmatch(r'\d+', param_value):
                raise ValueError(f"Invalid {param_name}: {param_value}")

        results = {}

        _log("  ont info...")
        results["ont_info"] = self.send_command(
            f"display ont info {frame} {slot} {port} {ont_id}", max_more=0
        )
        _log("OK")

        if "The required ONT does not exist" in results["ont_info"]:
            raise OntNotFoundError(f"ONT {frame}/{slot}/{port}/{ont_id} not found on OLT")

        status_match = re.search(r"Run state\s*: *(.+)", results["ont_info"])
        is_online = status_match and "online" in status_match.group(1).lower()
        if not is_online:
            _log("  ONT offline, пропуск остальных команд")
            _log("  register-info...")
            results["register_info"] = self.send_command(
                f"display ont register-info {frame} {slot} {port} {ont_id}", max_more=-1
            )
            _log("OK")
            return results

        _log("  ont version...")
        results["ont_version"] = self.send_command(
            f"display ont version {frame} {slot} {port} {ont_id}", max_more=0
        )
        _log("OK")

        _log("  optical-info...")
        self._gpon_ctx(frame, slot)
        results["optical_info"] = self.send_command(
            f"display ont optical-info {port} {ont_id}", max_more=-1
        )
        self._quit_gpon()
        _log("OK")

        _log("  line-quality...")
        results["line_quality"] = self.send_command(
            f"display statistics ont-line-quality {frame} {slot} {port} {ont_id}", max_more=0
        )
        _log("OK")

        _log("  port state...")
        results["lan_ports"] = self.send_command(
            f"display ont port state {frame} {slot} {port} {ont_id} eth-port all", max_more=-1
        )
        _log("OK")

        for lan_id in range(1, 5):
            _log(f"  eth-errors {lan_id}...")
            results[f"eth_errors_raw_{lan_id}"] = self.send_command(
                f"display statistics ont-eth {frame} {slot} {port} {ont_id} ont-port {lan_id}", max_more=0
            )
            _log("OK")

        _log("  mac-address...")
        mac_raw = self.send_command(
            f"display mac-address ont {frame}/{slot}/{port} {ont_id}", max_more=-1
        )
        results["mac_addresses"] = mac_raw
        _log(f"OK ({mac_raw.count(chr(10))} строк)")

        _log("  wan-info...")
        results["wan_info"] = self.send_command(
            f"display ont wan-info {frame} {slot} {port} {ont_id}", max_more=-1
        )
        _log("OK")

        _log("  ipconfig...")
        results["ipconfig"] = self.send_command(
            f"display ont ipconfig {frame} {slot} {port} {ont_id}", max_more=0
        )
        _log("OK")

        _log("  register-info...")
        results["register_info"] = self.send_command(
            f"display ont register-info {frame} {slot} {port} {ont_id}", max_more=-1
        )
        _log("OK")

        return results

    def clear_line_quality(self, frame, slot, port, ont_id):
        self._gpon_ctx(frame, slot)
        self.send_command(f"clear statistics ont-line-quality {port} {ont_id}", max_more=0)
        self._quit_gpon()

    def reset_lan_port(self, frame, slot, port, ont_id, lan_id):
        self._gpon_ctx(frame, slot)
        self.send_command(f"ont port attribute {port} {ont_id} eth {lan_id} operational-state off", max_more=0)
        time.sleep(0.5)
        self.send_command(f"ont port attribute {port} {ont_id} eth {lan_id} operational-state on", max_more=0)
        self._quit_gpon()

    def clear_eth_errors(self, frame, slot, port, ont_id, lan_id):
        self._gpon_ctx(frame, slot)
        self.send_command(f"clear statistics ont-eth {port} {ont_id} ont-port {lan_id}", max_more=0)
        self._quit_gpon()

    def remote_ping(self, frame, slot, port, ont_id, ip="1.1.1.1"):
        self._gpon_ctx(frame, slot)
        self._write(f"ont remote-ping {port} {ont_id} ip-address {ip}\r")
        time.sleep(8)
        output = self._read_to_prompt(5)
        self._quit_gpon()
        return output

    def find_ont_by_sn(self, serial):
        output = self.send_command(f"display ont info by-sn {serial}", max_more=0)
        return self._parse_fsp(output)

    def find_ont_by_description(self, description):
        # Попробовать найти с оригинальным значением
        output = self.send_command(f"display ont info by-desc {description}", max_more=0)
        result = self._parse_fsp(output)
        if result:
            return result
        # Fallback: попробовать с префиксом fl_ если description - это цифры
        if description.isdigit() and 5 <= len(description) <= 16:
            output = self.send_command(f"display ont info by-desc fl_{description}", max_more=0)
            return self._parse_fsp(output)
        return None

    @staticmethod
    def _parse_fsp(output):
        # Huawei MA5600 format:
        #   F/S/P   ONT-ID   Description
        #   0/ 0/6       0   fl_102693
        # Also supports format with colons from other variants
        #   F/S/P                   : 0/1/3
        #   ONT-ID                  : 9
        lines = output.strip().split('\n')
        for line in lines:
            # Try format: "0/ 0/6 0 fl_102693" (table format with spaces inside F/S/P)
            match = re.match(r'\s*(\d+)\s*/\s*\d+\s*/\s*\d+\s+(\d+)', line)
            if match:
                # Extract full F/S/P from line and parse
                fsp_match = re.match(r'\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)', line)
                if fsp_match:
                    return {"frame": fsp_match.group(1), "slot": fsp_match.group(2), "port": fsp_match.group(3), "ont_id": match.group(1)}
            # Try format with colons: "F/S/P : 0/1/3" and "ONT-ID : 9"
            fsp = re.search(r"F/S/P\s*:\s*([\d/]+)", line)
            oid = re.search(r"ONT-ID\s*:\s*(\d+)", line)
            if fsp and oid:
                parts = fsp.group(1).split("/")
                if len(parts) == 3:
                    return {"frame": parts[0], "slot": parts[1], "port": parts[2], "ont_id": oid.group(1)}
        return None