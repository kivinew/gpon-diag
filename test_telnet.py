#!/usr/bin/env python3
import asyncio
import telnetlib3
import sys

async def test():
    try:
        reader, writer = await telnetlib3.open_connection('172.16.40.111', 23, encoding='utf-8')
        print("Connected")
        # read until we get a prompt or login
        data = await reader.readuntil(b'name:')
        print("Received:", data.decode('utf-8', errors='ignore'))
        writer.write('kudryavcev.iv\n')
        await writer.drain()
        data = await reader.readuntil(b'password:')
        print("Received:", data.decode('utf-8', errors='ignore'))
        writer.write('hard5gznm\n')
        await writer.drain()
        data = await reader.readuntil(b'>')
        print("Received:", data.decode('utf-8', errors='ignore'))
        writer.write('enable\n')
        await writer.drain()
        data = await reader.readuntil(b'#')
        print("Received:", data.decode('utf-8', errors='ignore'))
        writer.write('display version\n')
        await writer.drain()
        data = await reader.readuntil(b'#')
        print("Version output:", data.decode('utf-8', errors='ignore'))
        writer.write('exit\n')
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    except Exception as e:
        print("Error:", e)
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test())