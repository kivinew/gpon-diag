"""OLT connection manager — synchronous socket-based for Huawei MA5608T."""

import logging
import re
import select
import socket
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

MORE_PROMPT = "---- More ( Press 'Q' to break ) ----"

_olt_registry: Dict[str, list] = {}  # List of connections per OLT (pool of 2)
_MAX_CONNECTIONS_PER_OLT = 2


class OntNotFoundError(Exception):
    pass


def get_olt_connection(host: str, port: int = 23,
                       username: str = "", password: str = "",
                       timeout: int = 15,
                       pool_index: Optional[int] = None) -> 'OltConnection':
    """Get or create connection from pool (max 2 per OLT).

    If pool_index is specified, returns that specific connection.
    Otherwise, returns the first available (or creates one).
    """
    key = f"{host}:{port}"

    # Skip blocked connections (circuit breaker open)
    if key in _olt_registry and pool_index is None:
        pool = _olt_registry[key]
        # Check if all connections in pool are blocked
        all_blocked = all(conn._skip_disconnect for conn in pool) if pool else False
        if all_blocked:
            # Clear pool and start fresh
            for conn in pool:
                try: conn.disconnect()
                except: pass
            _olt_registry[key] = []
            pool = []

    if key not in _olt_registry:
        _olt_registry[key] = []

    pool = _olt_registry[key]

    if pool_index is not None:
        while len(pool) <= pool_index:
            pool.append(OltConnection(host, port, username, password, timeout))
        conn = pool[pool_index]
        if not conn._connected and not conn._skip_disconnect:
            try: conn.connect()
            except Exception: pass
        return conn

    for conn in pool:
        if conn._connected and not conn._skip_disconnect:
            return conn

    if len(pool) < _MAX_CONNECTIONS_PER_OLT:
        conn = OltConnection(host, port, username, password, timeout)
        pool.append(conn)
        return conn

    return pool[0]


def close_all():
    """Close all OLT connections in the pool."""
    for pool in _olt_registry.values():
        for conn in pool:
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
        self._last_used: float = 0.0
        self._max_idle_seconds: int = 120
        self._skip_disconnect: bool = False  # If True, don't reconnect to preserve sessions
        self._connect_attempts: int = 0  # Track failed connection attempts

    def _check_idle_timeout(self):
        """Auto-disconnect if idle too long (prevents session exhaustion)."""
        now = time.time()
        if self._connected and (now - self._last_used) > self._max_idle_seconds:
            logger.info(f"Auto-disconnecting idle connection to {self.host}")
            self.disconnect()

    def connect(self):
        self._connect_attempts += 1
        # Reset socket state before attempting new connection
        if self._sock:
            try: self._sock.close()
            except: pass
        self._sock = None
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
            # Stabilize connection - OLT may need time after config mode
            time.sleep(0.5)
            self._connected = True
            self._connect_attempts = 0  # Reset on success
        except Exception as e:
            logger.error(f"Failed to connect to {self.host}:{self.port}: {e}")
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
            self._sock = None
            self._connected = False
            # Only set circuit breaker after 2 failed attempts to allow retries
            if self._connect_attempts >= 2:
                self._skip_disconnect = True
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
            version_match = re.search(r"VERSION\s*[:]\s*([^\s]+)", version_output, re.I)
            if version_match:
                version = version_match.group(1).strip()
        except Exception:
            logger.debug("Failed to retrieve OLT version", exc_info=True)
        # --------- Uptime extraction ---------
        try:
            uptime_output = self.send_command("display uptime", max_more=0)
            # Typical format: "Uptime is 5 days, 3 hours, 12 minutes"
            uptime_match = re.search(r"Uptime\s+is\s+([\w ,()]+)", uptime_output, re.I)
            if uptime_match:
                raw_uptime = uptime_match.group(1).strip()
                # Extract only the days component (e.g., "1957 day(s)")
                days_match = re.search(r"(\d+)\s*day", raw_uptime, re.I)
                uptime = f"{days_match.group(1)} day(s)" if days_match else raw_uptime
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
        if self._skip_disconnect:
            raise ConnectionError(f"Connection to {self.host} is blocked (circuit breaker open)")
        try:
            if self._sock is None:
                raise OSError("Socket not initialized")
            self._sock.sendall(text.encode("utf-8"))
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            logger.warning(f"Write failed ({e}), reconnecting...")
            self._connected = False
            self._sock = None
            try:
                self.connect()
                if self._sock is None:
                    raise OSError("Reconnect failed - socket still None")
                self._sock.sendall(text.encode("utf-8"))
            except Exception as reconnect_err:
                self._skip_disconnect = True  # Open circuit breaker
                raise reconnect_err

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
        # Check if connection is blocked before anything else
        if self._skip_disconnect:
            raise ConnectionError(f"Connection to {self.host} is blocked (circuit breaker open)")

        # Check idle timeout before using connection
        self._check_idle_timeout()
        self._last_used = time.time()

        # Check if socket is valid
        if self._sock is None or not self._connected:
            self._connected = False

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

        # Handle empty output - connection may be stale
        if not output.strip():
            logger.warning(f"Empty output for '{command}', reconnecting...")
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
            _log("  ONT offline, skipping other commands")
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
        _log(f"OK ({mac_raw.count(chr(10))} lines)")

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

    def collect_port_summary(self, frame, slot, port, log=None):
        """Collect 'display ont info summary' for all ONTs on a GPON port.
        Returns list of OntSummary objects.
        """
        from core.parser import parse_ont_info_summary

        _log = log or (lambda msg, end=" ", flush=True: print(msg, end=end, flush=flush))

        for param_name, param_value in [("frame", frame), ("slot", slot), ("port", port)]:
            if not re.fullmatch(r'\d+', param_value):
                raise ValueError(f"Invalid {param_name}: {param_value}")

        self._drain_socket()

        _log("  port summary...")
        output = self.send_command(
            f"display ont info summary {frame} {slot} {port}", max_more=-1
        )
        _log("OK")

        summaries = parse_ont_info_summary(output)
        _log(f"  parsed {len(summaries)} ONTs")
        return summaries

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
        output = self.send_command(f"display ont info by-sn {serial}", max_more=-1)
        return self._parse_fsp(output)

    def find_ont_by_description(self, description):
        value = description
        if description.isdigit() and 5 <= len(description) <= 16:
            value = f"fl_{description}"
        output = self.send_command(f"display ont info by-desc {value}", max_more=-1)
        result = self._parse_fsp(output)
        if not result:
            time.sleep(1)
            output = self.send_command(f"display ont info by-desc {value}", max_more=-1)
            result = self._parse_fsp(output)
        return result

    @staticmethod
    def _parse_fsp(output):
        # Huawei MA5600 table format:
        #   F/S/P   ONT-ID   Description
        #   0/ 0/6       0   fl_102693
        # Key-value format (across multiple lines):
        #   F/S/P                   : 0/1/3
        #   ONT-ID                  : 9
        #   Description             : fl_102693
        lines = output.strip().split('\n')
        fsp_val = oid_val = None
        for line in lines:
            # Reset on empty line separator between ONT records
            if not line.strip():
                fsp_val = oid_val = None
                continue
            # Table format: "0/ 0/6 0 fl_102693" — single-line F/S/P + ONT-ID
            m = re.search(r'(\d+)\s*/\s*(\d+)\s*/\s*(\d+)\s+(\d+)', line)
            if m:
                return {"frame": m.group(1), "slot": m.group(2), "port": m.group(3), "ont_id": m.group(4)}
            # Collect key-value pairs across lines
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
