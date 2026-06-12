"""Quick probe — connect to OLT and dump all diagnostic commands output."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from core.olt import OltConnection

# Use environment variables for credentials
# PowerShell example:
#   $env:GPON_OLT_40_111_USERNAME="user"; $env:GPON_OLT_40_111_PASSWORD="pass"
USERNAME = os.getenv("GPON_OLT_40_111_USERNAME", "")
PASSWORD = os.getenv("GPON_OLT_40_111_PASSWORD", "")

if not USERNAME or not PASSWORD:
    raise SystemExit(
        "Missing credentials. Set GPON_OLT_40_111_USERNAME/PASSWORD in environment.\n"
        "Example (PowerShell):\n"
        '  $env:GPON_OLT_40_111_USERNAME="user"; $env:GPON_OLT_40_111_PASSWORD="pass"'
    )


def main():
    olt = OltConnection("172.16.40.111", 23, USERNAME, PASSWORD)
    olt.connect()
    print("=== CONNECTED ===\n")

    # Use ONT 0/0/0/5 (online on OLT-40.111)
    frame, slot, port, ont = "0", "0", "0", "5"

    # 1. display ont info
    print("=" * 60)
    print("CMD: display ont info 0 0 0 5")
    print("=" * 60)
    out = olt.send_command(f"display ont info {frame} {slot} {port} {ont}", max_more=-1)
    print(out)

    # 2. display ont version
    print("=" * 60)
    print("CMD: display ont version 0 0 0 5")
    print("=" * 60)
    out = olt.send_command(f"display ont version {frame} {slot} {port} {ont}", max_more=-1)
    print(out)

    # Enter gpon context
    olt._gpon_ctx(frame, slot)

    # 3. display ont optical-info
    print("=" * 60)
    print("CMD: display ont optical-info 0 5")
    print("=" * 60)
    out = olt.send_command(f"interface gpon 0/0\ndisplay ont optical-info {port} {ont}", max_more=-1)
    print(out)

    # 4. display statistics ont-line-quality
    print("=" * 60)
    print("CMD: display statistics ont-line-quality 0 5")
    print("=" * 60)
    out = olt.send_command(f"display statistics ont-line-quality {port} {ont}", max_more=-1)
    print(out)

    # 5. display ont port state
    print("=" * 60)
    print("CMD: display ont port state 0 5 eth-port all")
    print("=" * 60)
    out = olt.send_command(f"display ont port state {port} {ont} eth-port all", max_more=-1)
    print(out)

    # 6. display mac-address ont
    print("=" * 60)
    print("CMD: display mac-address ont 0/0/0 5")
    print("=" * 60)
    out = olt.send_command(f"display mac-address ont {frame}/{slot}/{port} {ont}", max_more=-1)
    print(out)

    # 7. display ont wan-info
    print("=" * 60)
    print("CMD: display ont wan-info 0 5")
    print("=" * 60)
    out = olt.send_command(f"display ont wan-info {port} {ont}", max_more=-1)
    print(out)

    # 8. display ont ipconfig
    olt._quit_gpon()
    print("=" * 60)
    print("CMD: display ont ipconfig 0 5")
    print("=" * 60)
    out = olt.send_command(f"display ont ipconfig {port} {ont}", max_more=-1)
    print(out)

    # 9. display ont remote-ping
    print("=" * 60)
    print("CMD: display ont remote-ping 0 5 ip-address 1.1.1.1")
    print("=" * 60)
    out = olt.send_command(f"display ont remote-ping {port} {ont} ip-address 1.1.1.1", max_more=-1)
    print(out)

    # 10. display ont register-info
    olt._gpon_ctx(frame, slot)
    print("=" * 60)
    print("CMD: display ont register-info 0 5")
    print("=" * 60)
    out = olt.send_command(f"display ont register-info {port} {ont}", max_more=-1)
    print(out)
    olt._quit_gpon()

    # 11. display statistics ont-eth for each LAN port
    for lan_id in ["1", "2", "3", "4"]:
        print("=" * 60)
        print(f"CMD: display statistics ont-eth 0 5 ont-port {lan_id}")
        print("=" * 60)
        out = olt.send_command(f"display statistics ont-eth {port} {ont} ont-port {lan_id}", max_more=-1)
        print(out)

    olt.disconnect()
    print("\n=== DONE ===")

if __name__ == "__main__":
    main()
