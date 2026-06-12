"""CRT stub — emulates SecureCRT object using raw socket telnet."""

import socket
import time
import re


MORE_PROMPT = "---- More ( Press 'Q' to break ) ----"


class FakeScreen:
    def __init__(self, sock):
        self._sock = sock
        self._buf = b""
        self.CurrentRow = 1

    def Send(self, text):
        self._sock.sendall(text.encode("ascii"))

    def WaitForString(self, text, timeout=10):
        """Wait for single string. Returns 1 if found, 0 if timeout."""
        deadline = time.time() + timeout
        target = text.encode("ascii") if isinstance(text, str) else text
        while time.time() < deadline:
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    return 0
                self._buf += chunk
                # Strip IAC sequences
                self._buf = self._strip_iac(self._buf)
                if target in self._buf:
                    return 1
            except socket.timeout:
                pass
            time.sleep(0.05)
        return 0

    def WaitForStrings(self, texts, timeout=10):
        """Wait for multiple strings. Returns index+1 of first match, 0 if timeout."""
        deadline = time.time() + timeout
        targets = [t.encode("ascii") if isinstance(t, str) else t for t in texts]
        while time.time() < deadline:
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    return 0
                self._buf += chunk
                self._buf = self._strip_iac(self._buf)
                for idx, target in enumerate(targets):
                    if target in self._buf:
                        return idx + 1
            except socket.timeout:
                pass
            time.sleep(0.05)
        return 0

    def ReadString(self, marker, timeout=5):
        """Read until marker found."""
        deadline = time.time() + timeout
        target = marker.encode("ascii") if isinstance(marker, str) else marker
        while time.time() < deadline:
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                self._buf += chunk
                self._buf = self._strip_iac(self._buf)
                if target in self._buf:
                    idx = self._buf.find(target)
                    result = self._buf[:idx + len(target)].decode("ascii", errors="ignore")
                    self._buf = self._buf[idx + len(target):]
                    return result
            except socket.timeout:
                pass
            time.sleep(0.05)
        result = self._buf.decode("ascii", errors="ignore")
        self._buf = b""
        return result

    def Get(self, row, col_start, row_end, col_end):
        return ""

    def _strip_iac(self, data):
        """Remove telnet IAC sequences from data."""
        result = b""
        i = 0
        while i < len(data):
            if data[i] == 255 and i + 2 < len(data):
                cmd = data[i + 1]
                opt = data[i + 2]
                if cmd == 253:  # DO
                    self._sock.sendall(bytes([255, 251 if opt in (1, 3) else 252, opt]))
                elif cmd == 251:  # WILL
                    self._sock.sendall(bytes([255, 253 if opt == 3 else 254, opt]))
                elif cmd == 254:
                    self._sock.sendall(bytes([255, 252, opt]))
                elif cmd == 252:
                    self._sock.sendall(bytes([255, 254, opt]))
                i += 3
            else:
                result += bytes([data[i]])
                i += 1
        return result


class FakeCRT:
    def __init__(self, host, port=23, username="", password="", timeout=10):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._timeout = timeout
        self._sock = None
        self.Screen = None
        self.Arguments = FakeArguments()

    def connect(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(self._timeout)
        self._sock.connect((self._host, self._port))
        time.sleep(1)

        # Read banner + negotiate
        buf = b""
        deadline = time.time() + 3
        while time.time() < deadline:
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
            except socket.timeout:
                break
        buf = self._negotiate(buf)

        # Username
        self._sock.sendall(self._username.encode("ascii") + b"\r")
        time.sleep(2)
        buf = self._read_all(3)
        buf = self._respond_iac(buf)

        # Password
        self._sock.sendall(self._password.encode("ascii") + b"\r")
        time.sleep(3)
        self._read_all(4)

        # Enable -> Config
        self._sock.sendall(b"enable\r")
        time.sleep(1)
        self._read_all(2)
        self._sock.sendall(b"config\r")
        time.sleep(1)
        self._read_all(2)

        self.Screen = FakeScreen(self._sock)

    def _negotiate(self, buf):
        result = b""
        i = 0
        while i < len(buf):
            if buf[i] == 255 and i + 2 < len(buf):
                opt = buf[i + 2]
                if buf[i + 1] == 253:  # DO
                    self._sock.sendall(bytes([255, 251 if opt in (1, 3) else 252, opt]))
                elif buf[i + 1] == 251:  # WILL
                    self._sock.sendall(bytes([255, 253 if opt == 3 else 254, opt]))
                i += 3
            else:
                result += bytes([buf[i]])
                i += 1
        return result

    def _respond_iac(self, buf):
        result = b""
        i = 0
        while i < len(buf):
            if buf[i] == 255 and i + 2 < len(buf):
                opt = buf[i + 2]
                if buf[i + 1] == 254:  # DONT
                    self._sock.sendall(bytes([255, 252, opt]))
                i += 3
            else:
                result += bytes([buf[i]])
                i += 1
        return result

    def _read_all(self, seconds):
        buf = b""
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
            except socket.timeout:
                pass
        return buf

    def disconnect(self):
        if self._sock:
            try:
                self._sock.sendall(b"quit\r")
            except Exception:
                pass
            self._sock.close()
            self._sock = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()


class FakeArguments:
    Count = 0

    def __getitem__(self, idx):
        return ""
