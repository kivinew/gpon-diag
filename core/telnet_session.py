"""Telnet session handling — raw socket communication with Huawei OLT."""

import logging
import re
import select
import socket
import time
from typing import Optional

logger = logging.getLogger(__name__)

MORE_PROMPT = "---- More ( Press 'Q' to break ) ----"


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


class TelnetSession:
    """Manages a single telnet session using synchronous sockets."""

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
            if self._sock:
                try: self._sock.close()
                except: pass
                self._sock = None
            self._connected = False

    def connect(self):
        if self._connect_attempts > 0:  # Already had failed attempts
            wait_time = min(30, self._connect_attempts * 3)  # Max 30 seconds
            logger.info(f"Waiting {wait_time}s before retry to {self.host}...")
            time.sleep(wait_time)

        self._connect_attempts += 1
        # Reset socket state before attempting new connection
        if self._sock:
            try: self._sock.close()
            except: pass
        self._sock = None

        # Quick telnet port check before full handshake
        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(2)
            result = test_sock.connect_ex((self.host, self.port))
            test_sock.close()
            if result != 0:
                # Port not reachable - set circuit breaker immediately
                self._skip_disconnect = True
                raise ConnectionError(f"Telnet port not reachable (error {result})")
        except (socket.error, socket.timeout) as check_err:
            logger.warning(f"Telnet check failed for {self.host}:{self.port}: {check_err}")
            self._skip_disconnect = True
            raise OSError(f"Cannot create socket: {check_err}")

        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.settimeout(self.timeout)
            self._sock.connect((self.host, self.port))
            # Accept telnet negotiations
            self._sock.sendall(b"\xff\xfb\x01\xff\xfb\x03")
            # Read banner and login prompts, cache banner for model detection
            banner = self._read_to_prompt(2)
            self._banner = banner

            # Send username and wait for password prompt
            self._write(self.username + "\r")
            time.sleep(1.5)
            resp = self._read_to_prompt(3)

            # Send password
            self._write(self.password + "\r")
            time.sleep(2)
            resp = self._read_to_prompt(4)

            # Wait for command prompt (>)
            time.sleep(1)
            self._read_to_prompt(3)

            # Enter enable mode
            self._write("enable\r")
            time.sleep(1.5)
            self._read_to_prompt(3)

            # Enter config mode
            self._write("config\r")
            time.sleep(1.5)
            self._read_to_prompt(3)

            self._drain_socket()
            time.sleep(0.5)
            self._connected = True
            self._skip_disconnect = False
            self._connect_attempts = 0
            self._last_used = time.time()
        except Exception as e:
            logger.error(f"Failed to connect to {self.host}:{self.port}: {e}")
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
            self._sock = None
            self._connected = False
            raise

    def disconnect(self):
        if self._sock:
            try:
                self._sock.sendall(b"quit\r")
                time.sleep(0.1)
            except Exception:
                pass
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._connected = False
        self._connect_attempts = 0  # Reset for next time

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def _write(self, text):
        if self._skip_disconnect:
            raise ConnectionError(f"Connection to {self.host} is blocked")
        try:
            if self._sock is None:
                raise OSError("Socket not initialized")
            self._sock.sendall(text.encode("utf-8"))
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            logger.warning(f"Write failed ({e})")
            self._connected = False
            self._skip_disconnect = True
            raise

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
        """Send command and get output."""
        if self._skip_disconnect:
            raise ConnectionError(f"Connection blocked")

        self._check_idle_timeout()
        self._last_used = time.time()

        if self._sock is None or not self._connected:
            self._connected = False
            raise OSError("Socket not initialized")

        try:
            self._write(command + "\r")
            output = self._read_to_prompt(5)
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            logger.warning(f"Command '{command}' failed ({e})")
            raise

        # Handle empty output - connection may be stale (skip reconnect to avoid loop)
        if not output.strip():
            logger.warning(f"Empty output for '{command}'")
            raise ConnectionError(f"Empty response from OLT for command: {command}")

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

    def _gpon_ctx(self, frame, slot):
        self._drain_socket()
        self._write(f"interface gpon {frame}/{slot}\r")
        time.sleep(1)
        self._read_to_prompt(3)

    def _quit_gpon(self):
        self._write("quit\r")
        time.sleep(1)
        self._read_to_prompt(2)