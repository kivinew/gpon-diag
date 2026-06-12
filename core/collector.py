"""Collector — connects to OLT via telnetlib3, runs commands, returns raw output."""

import asyncio
import re
from typing import Optional


MORE_PROMPT = "---- More ( Press 'Q' to break ) ----"


class TelnetCollector:
    """Collects ONT data from Huawei OLT via telnetlib3."""

    def __init__(self, host: str, port: int = 23,
                 username: str = "", password: str = "",
                 timeout: int = 15):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self._reader = None
        self._writer = None
        self._loop = asyncio.new_event_loop()

    def connect(self):
        self._loop.run_until_complete(self._connect())

    def disconnect(self):
        if self._writer:
            try:
                self._writer.close()
            except Exception:
                pass

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    async def _connect(self):
        import telnetlib3
        self._reader, self._writer = await telnetlib3.open_connection(
            self.host, self.port, encoding="utf-8"
        )
        # Auth
        await self._readuntil("name:")
        self._write(self.username + "\n")
        await self._readuntil("password:")
        self._write(self.password + "\n")
        await self._readuntil(">")
        # Enable + config + scroll
        await self._cmd("enable")
        await self._cmd("config")
        await self._cmd("scroll 256")

    def _write(self, text):
        self._writer.write(text)

    async def _readuntil(self, marker, timeout=None):
        if timeout is None:
            timeout = self.timeout
        try:
            result = await asyncio.wait_for(
                self._reader.readuntil(marker.encode("utf-8")),
                timeout=timeout
            )
            return result.decode("utf-8", errors="ignore") if isinstance(result, bytes) else result
        except asyncio.TimeoutError:
            return ""

    async def _drain(self, seconds=1):
        """Drain all pending input."""
        deadline = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < deadline:
            try:
                await asyncio.wait_for(self._reader.read(4096), timeout=0.3)
            except (asyncio.TimeoutError, Exception):
                pass

    async def _cmd(self, command, max_more=0):
        """Send single command, read output until prompt."""
        self._write(command + "\n")
        # Drain echo and output until we see prompt
        await asyncio.sleep(0.3)
        await self._drain(1)

    async def _send_cmd(self, command, max_more=0):
        """Send command and read output with pagination support."""
        self._write(command + "\n")
        output = ""
        more_count = 0

        while True:
            try:
                chunk = await asyncio.wait_for(
                    self._reader.read(8192),
                    timeout=self.timeout
                )
                if isinstance(chunk, bytes):
                    chunk = chunk.decode("utf-8", errors="ignore")
                output += chunk
            except asyncio.TimeoutError:
                break

            if MORE_PROMPT in output:
                if max_more == -1 or more_count < max_more:
                    self._write(" ")
                    more_count += 1
                    continue
                else:
                    self._write("q")
                    break

            # Check for CLI prompt
            lines = output.strip().split("\n")
            last_line = lines[-1].strip() if lines else ""
            if last_line.endswith("#") or (last_line.endswith(">") and "(" in last_line):
                break

        return output

    def send_command(self, command, max_more=0):
        return self._loop.run_until_complete(self._send_cmd(command, max_more))

    def collect_ont(self, frame, slot, port, ont_id):
        results = {}

        results["ont_info"] = self.send_command(
            f"display ont info {frame} {slot} {port} {ont_id}", max_more=0
        )

        status_match = re.search(r"Run state\s*:\s*(.+)", results["ont_info"])
        is_online = status_match and "online" in status_match.group(1).lower()
        if not is_online:
            return results

        results["ont_version"] = self.send_command(
            f"display ont version {frame} {slot} {port} {ont_id}", max_more=0
        )
        self.send_command(f"interface gpon {frame}/{slot}", max_more=0)
        results["optical_info"] = self.send_command(
            f"display ont optical-info {port} {ont_id}", max_more=-1
        )
        results["line_quality"] = self.send_command(
            f"display statistics ont-line-quality {port} {ont_id}", max_more=0
        )
        results["lan_ports"] = self.send_command(
            f"display ont port state {port} {ont_id} eth-port all", max_more=-1
        )
        results["mac_addresses"] = self.send_command(
            f"display mac-address ont {frame}/{slot}/{port} {ont_id}", max_more=-1
        )
        results["ipconfig"] = self.send_command(
            f"display ont ipconfig {port} {ont_id}", max_more=0
        )
        self.send_command("quit", max_more=0)
        return results

    def find_ont_by_sn(self, serial):
        output = self.send_command(f"display ont info by-sn {serial}", max_more=0)
        return self._parse_fsp(output)

    def find_ont_by_description(self, description):
        output = self.send_command(f"display ont info by-desc {description}", max_more=0)
        return self._parse_fsp(output)

    @staticmethod
    def _parse_fsp(output):
        fsp = re.search(r"F/S/P\s*:\s*([\d/]+)", output)
        oid = re.search(r"ONT-ID\s*:\s*(\d+)", output)
        if fsp and oid:
            parts = fsp.group(1).split("/")
            if len(parts) == 3:
                return {"frame": parts[0], "slot": parts[1], "port": parts[2], "ont_id": oid.group(1)}
        return None
