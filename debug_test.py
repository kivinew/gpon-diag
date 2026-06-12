"""Debug: test telnet to Huawei OLT with enable/config."""

import socket
import time

HOST = '172.16.17.232'
PORT = 23
USER = 'kudryavcev.iv'
PASS = 'hard5gznm'

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(15)
s.connect((HOST, PORT))
print('Connected')

# Read everything for 3 seconds
deadline = time.time() + 3
buf = b''
while time.time() < deadline:
    try:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
    except socket.timeout:
        pass
print(f'Initial ({len(buf)} bytes): {buf[:200]}')

# Send WILL ECHO, WILL SGA
s.sendall(bytes([255, 251, 1, 255, 251, 3]))
time.sleep(0.5)

# Read response
buf = b''
deadline = time.time() + 2
while time.time() < deadline:
    try:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
    except socket.timeout:
        pass
print(f'After WILL ({len(buf)} bytes): {buf[:100]}')

# Send username
s.sendall(USER.encode() + b'\r')
time.sleep(2)

# Read
buf = b''
deadline = time.time() + 3
while time.time() < deadline:
    try:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
    except socket.timeout:
        pass
print(f'After user ({len(buf)} bytes): {buf[:100]}')

# Respond to any IAC
iac_resp = b''
i = 0
while i < len(buf) - 2:
    if buf[i] == 255 and buf[i+1] == 254:  # DONT
        iac_resp += bytes([255, 252, buf[i+2]])  # WONT
    i += 1
if iac_resp:
    s.sendall(iac_resp)
    time.sleep(0.3)

# Send password
s.sendall(PASS.encode() + b'\r')
time.sleep(3)

# Read
buf = b''
deadline = time.time() + 4
while time.time() < deadline:
    try:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
    except socket.timeout:
        pass
print(f'After pass ({len(buf)} bytes): {buf[:100]}')

# Enable
s.sendall(b'enable\r')
time.sleep(2)
buf = b''
deadline = time.time() + 3
while time.time() < deadline:
    try:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
    except socket.timeout:
        pass
print(f'After enable ({len(buf)} bytes): {buf[:80]}')

# Config
s.sendall(b'config\r')
time.sleep(2)
buf = b''
deadline = time.time() + 3
while time.time() < deadline:
    try:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
    except socket.timeout:
        pass
print(f'After config ({len(buf)} bytes): {buf[:80]}')

# Now the key test: display ont info
s.sendall(b'display ont info 0 1 3 9\r')
time.sleep(4)
buf = b''
deadline = time.time() + 5
while time.time() < deadline:
    try:
        chunk = s.recv(8192)
        if not chunk:
            break
        buf += chunk
    except socket.timeout:
        pass
text = buf.decode('ascii', errors='ignore')
print(f'\n=== ONT INFO ({len(buf)} bytes) ===')
print(text[:600])

s.close()
