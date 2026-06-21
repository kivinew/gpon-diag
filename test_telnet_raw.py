#!/usr/bin/env python3
"""Quick telnet test to OLT - fixed IAC handling."""

import socket, time, sys

HOST = '172.16.17.232'
USER = 'kudryavcev.iv'
PASS = 'hard5gznm'

def strip_iac(data):
    result = b''
    i = 0
    while i < len(data):
        if data[i] == 255 and i + 2 < len(data):
            i += 3
        else:
            result += bytes([data[i]])
            i += 1
    return result

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect((HOST, 23))
        print('Connected', flush=True)

        time.sleep(0.5)
        buf = strip_iac(s.recv(4096))
        if b'User name' in buf:
            print('Got username prompt', flush=True)
        else:
            print(f'Unexpected: {buf[:100]}', flush=True)

        s.sendall(USER.encode() + b'\r')
        print('Sent username', flush=True)
        time.sleep(1)
        buf = strip_iac(s.recv(4096))
        print(f'After user: {buf[:100]}', flush=True)

        s.sendall(PASS.encode() + b'\r')
        print('Sent password', flush=True)
        time.sleep(2)
        buf = strip_iac(s.recv(4096))
        print(f'After pass: {buf[:150]}', flush=True)

        s.sendall(b'enable\r')
        print('Sent enable', flush=True)
        time.sleep(1)
        buf = strip_iac(s.recv(4096))
        print(f'After enable: {buf[:100]}', flush=True)

        s.sendall(b'config\r')
        print('Sent config', flush=True)
        time.sleep(1)
        buf = strip_iac(s.recv(4096))
        print(f'After config: {buf[:100]}', flush=True)

        s.sendall(b'scroll\r')
        print('Sent scroll', flush=True)
        time.sleep(0.5)
        buf = strip_iac(s.recv(4096))
        print(f'After scroll: {buf[:100]}', flush=True)

        s.sendall(b'display ont info 0 1 3 9\r')
        print('Sent command', flush=True)
        time.sleep(3)
        buf = b''
        while True:
            try:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += strip_iac(chunk)
            except socket.timeout:
                break
        text = buf.decode('utf-8', errors='ignore')
        print(f'ONT output: {text[:400]}', flush=True)

    finally:
        s.close()
        print('Closed', flush=True)

if __name__ == '__main__':
    main()