#!/usr/bin/env python3
"""Quick telnet to OLT - test connectivity."""

import socket, time

HOST = '172.16.17.232'
USER = 'kudryavcev.iv'
PASS = 'hard5gznm'

def read_output(sock, timeout=2):
    buf = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            chunk = sock.recv(4096)
            if chunk:
                buf += chunk
        except socket.timeout:
            pass
    return buf

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((HOST, 23))
    print("Connected")

    # IAC negotiation
    time.sleep(0.5)
    s.sendall(bytes([255, 251, 1, 255, 251, 3]))
    time.sleep(0.5)
    buf = read_output(s, 2)
    print(f"Banner: {buf[:100]}")

    s.sendall(USER.encode() + b'\r')
    time.sleep(1)
    buf = read_output(s, 2)
    print(f"After user: {buf[:100]}")

    s.sendall(PASS.encode() + b'\r')
    time.sleep(2)
    buf = read_output(s, 2)
    print(f"After pass: {buf[:100]}")

    # Test command
    s.sendall(b'display ont info 0 1 3 9\r')
    time.sleep(3)
    buf = read_output(s, 3)
    text = buf.decode('utf-8', errors='ignore')
    print(f"ONT info (500 chars): {text[:500]}")

    s.close()

if __name__ == '__main__':
    main()
