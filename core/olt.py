"""OLT connection manager — synchronous socket-based for Huawei MA5608T.

Supports both telnet and SSH connections. SSH is preferred for better security.
"""

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
                       pool_index: Optional[int] = None,
                       use_ssh: bool = False) -> 'OltConnection':
    """Get or create connection from pool (max 2 per OLT).

    If pool_index is specified, returns that specific connection.
    Otherwise, returns the first available (or creates one).
    
    Args:
        host: OLT host IP or hostname
        port: Telnet port (default 23) or SSH port (default 22)
        username: Login username
        password: Login password
        timeout: Connection timeout in seconds
        pool_index: Specific connection index in pool
        use_ssh: Use SSH instead of telnet (port defaults to 22 if not specified)
    """
    if use_ssh and port == 23:
        port = 22  # Default SSH port
    
    key = f"{host}:{port}:{use_ssh}"

    # Skip broken connections - create fresh when socket is None or blocked
    if key in _olt_registry and pool_index is None:
        pool = _olt_registry[key]
        all_broken = all((conn._sock is None or conn._skip_disconnect) for conn in pool) if pool else False
        if all_broken:
            for conn in pool:
                try: conn.disconnect()
                except: pass
            _olt_registry[key] = []
            conn = OltConnection(host, port, username, password, timeout, use_ssh=use_ssh)
            _olt_registry[key].append(conn)
            return conn

    if key not in _olt_registry:
        _olt_registry[key] = []

    pool = _olt_registry[key]

    if pool_index is not None:
        while len(pool) <= pool_index:
            pool.append(OltConnection(host, port, username, password, timeout, use_ssh=use_ssh))
        conn = pool[pool_index]
        if conn._sock is None or conn._skip_disconnect:
            conn._connect_attempts = max(0, conn._connect_attempts - 1)
            try:
                conn.connect()
            except Exception:
                pass
        return conn

    for conn in pool:
        if conn._connected and not conn._skip_disconnect:
            return conn

    if len(pool) < _MAX_CONNECTIONS_PER_OLT:
        conn = OltConnection(host, port, username, password, timeout, use_ssh=use_ssh)
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
    """Manages a single telnet or SSH connection to one OLT."""

    _banner_cache = ""

    def __init__(self, host: str = "", port: int = 23,
                 username: str = "", password: str = "",
                 timeout: int = 15, use_ssh: bool = False):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.use_ssh = use_ssh
        self._sock: Optional[socket.socket] = None
        self._ssh_conn: Optional[object] = None
        self._connected = False
        self._last_used: float = time.time()
        self._max_idle_seconds: int = 120
        self._skip_disconnect: bool = False
        self._connect_attempts: int = 0

    def _check_idle_timeout(self):
        """Auto-disconnect if idle too long."""
        now = time.time()
        if self._connected and (now - self._last_used) > self._max_idle_seconds:
            logger.info(f"Auto-disconnecting idle connection to {self.host}")
            self.disconnect()

    def connect(self):
        """Connect to OLT using telnet."""
        self._connect_telnet()

    def _connect_telnet(self):
        """Telnet connection method."""
        # Wait before retry to avoid blocking OLT
        if self._connect_attempts > 0:
            wait_time = min(120, self._connect_attempts * 10)  # 10-120 seconds wait
            logger.info(f"Waiting {wait_time}s before retry...")
            time.sleep(wait_time)
            self._connect_attempts = 0

        self._connect_attempts += 1
        if self._sock:
            try: self._sock.close()
            except: pass
        self._sock = None

        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(2)
            result = test_sock.connect_ex((self.host, self.port))
            test_sock.close()
            if result != 0:
                self._skip_disconnect = True
                raise ConnectionError(f"Telnet port not reachable (error {result})")
        except (socket.error, socket.timeout) as check_err:
            self._skip_disconnect = True
            raise OSError(f"Cannot create socket: {check_err}")

        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.settimeout(self.timeout)
            self._sock.connect((self.host, self.port))
            
            self._sock.setblocking(False)
            banner_data = b""
            deadline = time.time() + 3
            while time.time() < deadline:
                try:
                    chunk = self._sock.recv(4096)
                    if chunk:
                        banner_data += chunk
                except BlockingIOError:
                    break
            self._sock.setblocking(True)
            
            banner_data = _strip_iac(banner_data)
            banner = banner_data.decode("utf-8", errors="ignore")
            logger.debug(f"Banner: {banner[:200] if banner else 'empty'}")
            OltConnection._banner_cache = banner
            
            # Send username
            self._sock.sendall((self.username + "\r").encode("utf-8"))
            time.sleep(1.5)
            resp1 = self._read_response(3)
            logger.debug(f"After username: {resp1[:200]}")
            
            # Send password
            self._sock.sendall((self.password + "\r").encode("utf-8"))
            time.sleep(2.5)
            resp2 = self._read_response(4)
            logger.debug(f"After password: {resp2[:200]}")
            
            # Check if we need enable mode
            combined = (resp1 + resp2).lower()
            if "config" not in combined and not resp2.strip().endswith(")"):
                self._sock.sendall(b"enable\r")
                time.sleep(1)
                self._read_response(2)
            
            # Enter config mode
            self._sock.sendall(b"config\r")
            time.sleep(1)
            self._read_response(3)
            
            self._drain_socket()
            time.sleep(0.5)
            self._connected = True
            self._connect_attempts = 0
        except Exception as e:
            logger.error(f"Failed to connect to {self.host}:{self.port}: {e}")
            if self._sock:
                try: self._sock.close()
                except: pass
            self._sock = None
            self._connected = False
            if "connection refused by remote host" in str(e).lower():
                logger.error(f"IP blocked by OLT {self.host}. Use different IP or wait.")
            if self._connect_attempts >= 2:
                self._skip_disconnect = True
            raise

    def _connect_ssh(self):
        """SSH connection method."""
        try:
            import asyncssh
        except ImportError:
            raise ImportError("asyncssh required for SSH. pip install asyncssh")
        
        import asyncio
        
        async def _do_connect():
            return await asyncssh.connect(
                self.host, username=self.username, password=self.password,
                known_hosts=None, client_host_keys=None
            )
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._ssh_conn = loop.run_until_complete(_do_connect())
            self._connected = True
            self._connect_attempts = 0
            logger.info(f"SSH connected to {self.host}")
        except Exception as e:
            logger.error(f"SSH failed to {self.host}: {e}")
            self._connected = False
            raise

    def _read_response(self, seconds=2):
        """Read response data from socket."""
        buf = b""
        deadline = time.time() + seconds
        while time.time() < deadline:
            ready = select.select([self._sock], [], [], 0.5)
            if ready[0]:
                try:
                    chunk = self._sock.recv(8192)
                    if chunk:
                        buf += chunk
                except (socket.timeout, ConnectionResetError, BrokenPipeError, OSError):
                    break
        return buf.decode("utf-8", errors="ignore")

    def disconnect(self):
        """Disconnect from OLT."""
        if self.use_ssh and self._ssh_conn:
            try: self._ssh_conn.close()
            except: pass
            self._ssh_conn = None
        elif self._sock:
            try:
                self._sock.sendall(b"quit\r")
                time.sleep(0.1)
            except: pass
            try: self._sock.close()
            except: pass
            self._sock = None
        self._connected = False
        self._connect_attempts = 0

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def _write(self, text):
        if self._skip_disconnect:
            raise ConnectionError(f"Connection blocked to {self.host}")
        if self._sock is None:
            raise OSError("Socket not initialized")
        self._sock.sendall(text.encode("utf-8"))

    def _read_to_prompt(self, seconds=2):
        """Read data until prompt."""
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
        return buf.decode("utf-8", errors="ignore")

    def get_olt_info(self) -> dict:
        """Get OLT model, uptime, and software version."""
        model = uptime = version = ""
        try:
            banner = OltConnection._banner_cache
            model_match = re.search(r"\bMA(\d{4})T?\b", banner, re.I)
            if model_match:
                model = f"MA{model_match.group(1)}"
        except Exception:
            pass
        try:
            version_output = self.send_command("display version", max_more=0)
            version_match = re.search(r"VERSION\s*[:]\s*([^\s]+)", version_output, re.I)
            if version_match:
                version = version_match.group(1).strip()
        except Exception:
            pass
        try:
            uptime_output = self.send_command("display uptime", max_more=0)
            uptime_match = re.search(r"Uptime\s+is\s+([\w ,()]+)", uptime_output, re.I)
            if uptime_match:
                raw_uptime = uptime_match.group(1).strip()
                days_match = re.search(r"(\d+)\s*day", raw_uptime, re.I)
                uptime = f"{days_match.group(1)} day(s)" if days_match else raw_uptime
        except Exception:
            pass
        return {"model": model, "uptime": uptime, "version": version}

    def send_command(self, command, max_more=0):
        """Send command and get output."""
        if self._skip_disconnect:
            raise ConnectionError(f"Connection blocked to {self.host}")
        self._check_idle_timeout()
        self._last_used = time.time()
        if self._sock is None:
            raise OSError("Socket not initialized")

        try:
            self._write(command + "\r")
            output = self._read_to_prompt(5)
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            self._connected = False
            raise

        if not output.strip():
            raise ConnectionError(f"Empty response for: {command}")

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
            while select.select([self._sock], [], [], 0.3)[0]:
                self._sock.recv(8192)
        except Exception:
            pass

    def collect_ont(self, frame, slot, port, ont_id, log=None):
        """Collect ONT data."""
        _log = log or (lambda msg, end=" ", flush=True: print(msg, end=end, flush=flush))
        self._drain_socket()

        for param_name, param_value in [("frame", frame), ("slot", slot),
                                       ("port", port), ("ont_id", ont_id)]:
            if not re.fullmatch(r'\d+', param_value):
                raise ValueError(f"Invalid {param_name}: {param_value}")

        results = {}
        _log("  ont info...")
        results["ont_info"] = self.send_command(f"display ont info {frame} {slot} {port} {ont_id}", max_more=0)
        _log("OK")

        if "The required ONT does not exist" in results["ont_info"]:
            raise OntNotFoundError(f"ONT {frame}/{slot}/{port}/{ont_id} not found")

        status_match = re.search(r"Run state\s*: *(.+)", results["ont_info"])
        is_online = status_match and "online" in status_match.group(1).lower()
        if not is_online:
            _log("  ONT offline, register-info...")
            try:
                results["register_info"] = self.send_command(f"display ont register-info {frame} {slot} {port} {ont_id}", max_more=-1)
                _log("OK")
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                logger.warning(f"Connection lost for offline ONT: {e}")
                _log("connection lost, returning partial data")
            return results

        _log("  ont version...")
        results["ont_version"] = self.send_command(f"display ont version {frame} {slot} {port} {ont_id}", max_more=0)
        _log("OK")

        _log("  optical-info...")
        self._gpon_ctx(frame, slot)
        results["optical_info"] = self.send_command(f"display ont optical-info {port} {ont_id}", max_more=-1)
        self._quit_gpon()
        _log("OK")

        _log("  line-quality...")
        results["line_quality"] = self.send_command(f"display statistics ont-line-quality {frame} {slot} {port} {ont_id}", max_more=0)
        _log("OK")

        _log("  port state...")
        results["lan_ports"] = self.send_command(f"display ont port state {frame} {slot} {port} {ont_id} eth-port all", max_more=-1)
        _log("OK")

        for lan_id in range(1, 5):
            _log(f"  eth-errors {lan_id}...")
            results[f"eth_errors_raw_{lan_id}"] = self.send_command(f"display statistics ont-eth {frame} {slot} {port} {ont_id} ont-port {lan_id}", max_more=0)
            _log("OK")

        _log("  mac-address...")
        results["mac_addresses"] = self.send_command(f"display mac-address ont {frame}/{slot}/{port} {ont_id}", max_more=-1)
        _log(f"OK ({results['mac_addresses'].count(chr(10))} lines)")

        _log("  wan-info...")
        results["wan_info"] = self.send_command(f"display ont wan-info {frame} {slot} {port} {ont_id}", max_more=-1)
        _log("OK")

        _log("  ipconfig...")
        results["ipconfig"] = self.send_command(f"display ont ipconfig {frame} {slot} {port} {ont_id}", max_more=0)
        _log("OK")

        _log("  register-info...")
        results["register_info"] = self.send_command(f"display ont register-info {frame} {slot} {port} {ont_id}", max_more=-1)
        _log("OK")

        return results

    def collect_port_summary(self, frame, slot, port, log=None):
        """Collect 'display ont info summary' for all ONTs on a GPON port."""
        from core.parser import parse_ont_info_summary
        _log = log or (lambda msg, end=" ", flush=True: print(msg, end=end, flush=flush))

        for param_name, param_value in [("frame", frame), ("slot", slot), ("port", port)]:
            if not re.fullmatch(r'\d+', param_value):
                raise ValueError(f"Invalid {param_name}: {param_value}")

        self._drain_socket()
        _log("  port summary...")
        output = self.send_command(f"display ont info summary {frame} {slot} {port}", max_more=-1)
        _log(f"  parsed {len(parse_ont_info_summary(output))} ONTs")
        return parse_ont_info_summary(output)

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
        return self._parse_fsp(self.send_command(f"display ont info by-sn {serial}", max_more=-1))

    def find_ont_by_description(self, description):
        value = description
        if description.isdigit() and 5 <= len(description) <= 16:
            value = f"fl_{description}"
        output = self.send_command(f"display ont info by-desc {value}", max_more=-1)
        result = self._parse_fsp(output)
        if not result:
            time.sleep(1)
            result = self._parse_fsp(self.send_command(f"display ont info by-desc {value}", max_more=-1))
        return result

    @staticmethod
    def _parse_fsp(output):
        """Parse F/S/P and ONT-ID from output."""
        lines = output.strip().split('\n')
        fsp_val = oid_val = None
        for line in lines:
            if not line.strip():
                fsp_val = oid_val = None
                continue
            m = re.search(r'(\d+)\s*/\s*(\d+)\s*/\s*(\d+)\s+(\d+)', line)
            if m:
                return {"frame": m.group(1), "slot": m.group(2), "port": m.group(3), "ont_id": m.group(4)}
            fsp_m = re.search(r"F/S/P\s*:\s*([\d/]+)", line)
            oid_m = re.search(r"ONT-ID\s*:\s*(\d+)", line)
            if fsp_m: fsp_val = fsp_m.group(1)
            if oid_m: oid_val = oid_m.group(1)
            if fsp_val and oid_val:
                parts = fsp_val.split("/")
                if len(parts) == 3:
                    return {"frame": parts[0], "slot": parts[1], "port": parts[2], "ont_id": oid_val}
        return None