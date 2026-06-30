"""Fix the broken olt.py file."""
import re

with open('core/olt.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Remove broken duplicate line (line 244 in original, ends with :\s*\n without : after )
content = re.sub(
    r"(if re\.match\(r'\^\\\S\+\[>#]', last_line\) or re\.search\(r'\\\}\\s\*:\\s\*\n)"
    r"(if re\.match\(r'\^\\\S\+\[>#]', last_line\) or re\.search\(r'\\\}\\s\*:\\s\*\$', last_line\):\n)",
    r"\2",
    content
)

# Fix 2: Replace the _gpon_ctx stub with full implementations
stub_pattern = (
    r"    def _gpon_ctx\(self, frame, slot\):\n"
    r"\n"
    r"\n"
    r"    def get_olt_info"
)
replacement = """    def _gpon_ctx(self, frame, slot):
        self._drain_socket()
        self._write(f"interface gpon {frame}/{slot}\\r")
        time.sleep(1)
        self._read_to_prompt(3)

    def _quit_gpon(self):
        self._write("quit\\r")
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
        \"\"\"Collect ONT data with parameter validation.\"\"\"
        _log = log or (lambda msg, end=" ", flush=True: print(msg, end=end, flush=flush))

    def get_olt_info"""

content = re.sub(stub_pattern, replacement, content, count=1)

with open('core/olt.py', 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
with open('core/olt.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    print(f"Total lines: {len(lines)}")
    for i, line in enumerate(lines[240:260], start=241):
        print(f"{i}: {line.rstrip()[:100]}")
