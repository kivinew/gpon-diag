"""MCP server for GPON Huawei diagnostics via telnet.

Provides tools for ONT management: connect, diagnose, clear errors, reset ports.
Uses synchronous socket-based OLT connection from core/olt.py.
"""

import json
import os
import sys
import logging
from typing import Any

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.types as types

# Import GPON core modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.olt import get_olt_connection, close_all, OntNotFoundError, OltConnection
from core.parser import (
    parse_ont_info, parse_ont_version, parse_optical_info,
    parse_line_quality, parse_lan_ports, parse_mac_addresses, parse_ipconfig,
    parse_wan_info, parse_eth_errors, parse_register_info, parse_ping_result,
)
from core.engine import create_extended_engine
from core.thresholds import Thresholds
from core.report import DiagnosisReport, DiagnosisProblem
from core.models import OntMetrics
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)
TZ_LOCAL = timezone(timedelta(hours=7))

# Connection state - track active connections
_connection_state: dict[str, OltConnection] = {}

# Server instance
server = Server("gpon-huawei")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available GPON tools."""
    return [
        types.Tool(
            name="gpon_connect",
            description="Connect to Huawei OLT via telnet and get OLT info",
            inputSchema={
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "OLT IP address or hostname"},
                    "port": {"type": "integer", "default": 23, "description": "Telnet port"},
                    "username": {"type": "string", "description": "Login username"},
                    "password": {"type": "string", "description": "Login password"},
                    "timeout": {"type": "integer", "default": 30, "description": "Connection timeout in seconds"},
                    "session_name": {"type": "string", "default": "default", "description": "Connection session identifier"}
                },
                "required": ["host", "username", "password"]
            }
        ),
        types.Tool(
            name="gpon_diagnose",
            description="Run full diagnosis on ONT by address, serial or description",
            inputSchema={
                "type": "object",
                "properties": {
                    "ont": {"type": "string", "description": "ONT address (F/S/P/ONT), serial, or description"},
                    "session_name": {"type": "string", "default": "default", "description": "Connection session identifier"},
                    "allow_actions": {"type": "boolean", "default": True, "description": "Allow port resets and counter clears"},
                    "ping_target": {"type": "string", "default": "1.1.1.1", "description": "Target for remote ping"}
                },
                "required": ["ont", "session_name"]
            }
        ),
        types.Tool(
            name="gpon_clear_errors",
            description="Clear BIP and Ethernet errors counters on ONT",
            inputSchema={
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "ONT address (F/S/P/ONT)"},
                    "session_name": {"type": "string", "default": "default", "description": "Connection session identifier"}
                },
                "required": ["address", "session_name"]
            }
        ),
        types.Tool(
            name="gpon_reset_lan_port",
            description="Reset (disable/enable) a specific LAN port on ONT",
            inputSchema={
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "ONT address (F/S/P/ONT)"},
                    "lan_id": {"type": "integer", "description": "LAN port number (1-4)"},
                    "session_name": {"type": "string", "default": "default", "description": "Connection session identifier"}
                },
                "required": ["address", "lan_id", "session_name"]
            }
        ),
        types.Tool(
            name="gpon_get_optics",
            description="Get real-time optical power readings from ONT",
            inputSchema={
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "ONT address (F/S/P/ONT)"},
                    "session_name": {"type": "string", "default": "default", "description": "Connection session identifier"}
                },
                "required": ["address", "session_name"]
            }
        ),
    ]


def _parse_address(ont: str) -> dict:
    """Parse ONT identifier into type and value."""
    import re
    ont = ont.strip()
    if re.fullmatch(r"(?i)(48575443|hwtc)[\da-f]{8}", ont):
        return {"type": "serial", "value": ont.upper()}
    tokens = ont.replace("/", " ").split()
    if len(tokens) == 4 and all(t.isdigit() for t in tokens):
        return {"type": "address", "frame": tokens[0], "slot": tokens[1], "port": tokens[2], "ont_id": tokens[3]}
    if re.fullmatch(r"^(fl_|kes)?\d{5,16}$", ont) or (ont.isdigit() and 5 <= len(ont) <= 16):
        value = ont
        if ont.isdigit():
            value = f"fl_{ont}"
        return {"type": "description", "value": value}
    return {"type": "description", "value": ont}


def _build_thresholds() -> Thresholds:
    """Build thresholds with defaults."""
    return Thresholds(
        ont_rx_power_warn=-26.5,
        ont_rx_power_crit=-30.0,
        olt_rx_power_warn=-33.0,
        olt_rx_power_crit=-35.0,
        bip_error_warn=10000,
        bip_error_crit=100000,
        cpu_temp_warn=75,
        cpu_temp_crit=90,
        cpu_usage_warn=90,
        ont_temperature_warn=65,
        ont_temperature_crit=75,
        memory_usage_warn=85,
        distance_warn=19000,
        distance_crit=20000
    )


def _collect_diagnosis_data(olt: OltConnection, frame: str, slot: str, port: str, ont_id: str) -> dict:
    """Collect all ONT data for diagnosis."""
    results = {}
    results["ont_info"] = olt.send_command(f"display ont info {frame} {slot} {port} {ont_id}", max_more=0)
    
    status_match = olt.send_command(f"display ont info {frame} {slot} {port} {ont_id}", max_more=0)
    if "The required ONT does not exist" in results["ont_info"]:
        raise OntNotFoundError(f"ONT {frame}/{slot}/{port}/{ont_id} not found")
    
    if "online" not in status_match.lower():
        results["register_info"] = olt.send_command(f"display ont register-info {frame} {slot} {port} {ont_id}", max_more=-1)
        return results
    
    results["ont_version"] = olt.send_command(f"display ont version {frame} {slot} {port} {ont_id}", max_more=0)
    
    olt._gpon_ctx(frame, slot)
    results["optical_info"] = olt.send_command(f"display ont optical-info {port} {ont_id}", max_more=-1)
    olt._quit_gpon()
    
    results["line_quality"] = olt.send_command(f"display statistics ont-line-quality {frame} {slot} {port} {ont_id}", max_more=0)
    results["lan_ports"] = olt.send_command(f"display ont port state {frame} {slot} {port} {ont_id} eth-port all", max_more=-1)
    
    for lan_id in ["1", "2", "3", "4"]:
        key = f"eth_errors_raw_{lan_id}"
        results[key] = olt.send_command(f"display statistics ont-eth {frame} {slot} {port} {ont_id} ont-port {lan_id}", max_more=0)
    
    results["mac_addresses"] = olt.send_command(f"display mac-address ont {frame}/{slot}/{port} {ont_id}", max_more=-1)
    results["wan_info"] = olt.send_command(f"display ont wan-info {frame} {slot} {port} {ont_id}", max_more=-1)
    results["ipconfig"] = olt.send_command(f"display ont ipconfig {frame} {slot} {port} {ont_id}", max_more=0)
    results["register_info"] = olt.send_command(f"display ont register-info {frame} {slot} {port} {ont_id}", max_more=-1)
    
    return results


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    """Handle GPON tool calls."""
    if arguments is None:
        arguments = {}
    
    if name == "gpon_connect":
        return await _tool_connect(arguments)
    elif name == "gpon_diagnose":
        return await _tool_diagnose(arguments)
    elif name == "gpon_clear_errors":
        return await _tool_clear_errors(arguments)
    elif name == "gpon_reset_lan_port":
        return await _tool_reset_lan_port(arguments)
    elif name == "gpon_get_optics":
        return await _tool_get_optics(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


async def _tool_connect(params: dict) -> list[types.TextContent]:
    """Connect to OLT and return basic info."""
    host = params["host"]
    port = params.get("port", 23)
    username = params["username"]
    password = params["password"]
    timeout = params.get("timeout", 30)
    session_name = params.get("session_name", "default")
    
    try:
        olt = get_olt_connection(host, port, username, password, timeout)
        olt.connect()
        info = olt.get_olt_info()
        _connection_state[session_name] = olt
        
        return [types.TextContent(type="text", text=json.dumps({
            "status": "connected",
            "session": session_name,
            "host": host,
            "olt_info": info
        }, ensure_ascii=False))]
    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "failed",
            "error": str(e)
        }, ensure_ascii=False))]


async def _tool_diagnose(params: dict) -> list[types.TextContent]:
    """Run full diagnosis on ONT."""
    session_name = params.get("session_name", "default")
    ont = params["ont"]
    
    olt = _connection_state.get(session_name)
    if not olt:
        return [types.TextContent(type="text", text=json.dumps({
            "error": "Not connected. Use gpon_connect first."
        }, ensure_ascii=False))]
    
    input_data = _parse_address(ont)
    allow_actions = params.get("allow_actions", True)
    ping_target = params.get("ping_target", "1.1.1.1")
    
    host = olt.host
    
    # Find ONT if needed
    if input_data["type"] == "serial":
        loc = olt.find_ont_by_sn(input_data["value"])
        if loc:
            input_data.update(loc)
    elif input_data["type"] == "description":
        loc = olt.find_ont_by_description(input_data["value"])
        if loc:
            input_data.update(loc)
    
    if "frame" not in input_data:
        return [types.TextContent(type="text", text=json.dumps({
            "error": f"ONT {ont} not found on OLT"
        }, ensure_ascii=False))]
    
    # Collect data
    try:
        raw_data = _collect_diagnosis_data(
            olt, input_data["frame"], input_data["slot"],
            input_data["port"], input_data["ont_id"]
        )
    except OntNotFoundError as e:
        return [types.TextContent(type="text", text=json.dumps({
            "error": str(e)
        }, ensure_ascii=False))]
    
    # Parse
    metrics = OntMetrics()
    metrics.address = f"{input_data['frame']}/{input_data['slot']}/{input_data['port']}/{input_data['ont_id']}"
    metrics.frame = input_data["frame"]
    metrics.slot = input_data["slot"]
    metrics.port = input_data["port"]
    metrics.ont_id = input_data["ont_id"]
    
    if "ont_info" in raw_data:
        parse_ont_info(raw_data["ont_info"], metrics)
    if "ont_version" in raw_data:
        parse_ont_version(raw_data["ont_version"], metrics)
    if "optical_info" in raw_data:
        parse_optical_info(raw_data["optical_info"], metrics)
    if "line_quality" in raw_data:
        parse_line_quality(raw_data["line_quality"], metrics)
    if "lan_ports" in raw_data:
        parse_lan_ports(raw_data["lan_ports"], metrics)
    if "mac_addresses" in raw_data:
        parse_mac_addresses(raw_data["mac_addresses"], metrics)
    if "ipconfig" in raw_data:
        parse_ipconfig(raw_data["ipconfig"], metrics)
    if "wan_info" in raw_data:
        parse_wan_info(raw_data["wan_info"], metrics)
    
    for lan_id in ["1", "2", "3", "4"]:
        key = f"eth_errors_raw_{lan_id}"
        if key in raw_data:
            parse_eth_errors(raw_data[key], metrics, lan_id)
    
    if "register_info" in raw_data:
        parse_register_info(raw_data["register_info"], metrics)
    
    metrics.fetch_timestamp = datetime.now(TZ_LOCAL).isoformat()
    
    # Diagnose
    thresholds = _build_thresholds()
    engine = create_extended_engine(thresholds)
    problems = engine.diagnose(metrics)
    
    report = DiagnosisReport(
        datetime.now(TZ_LOCAL).isoformat(), host,
        metrics, problems, not metrics.is_online
    )
    
    return [types.TextContent(type="text", text=json.dumps({
        "status": "success",
        "session": session_name,
        "report_text": report.to_text(),
        "report_dict": report.to_dict()
    }, ensure_ascii=False))]


async def _tool_clear_errors(params: dict) -> list[types.TextContent]:
    """Clear BIP and Ethernet errors counters on ONT."""
    session_name = params.get("session_name", "default")
    address = params["address"]
    
    olt = _connection_state.get(session_name)
    if not olt:
        return [types.TextContent(type="text", text=json.dumps({
            "error": "Not connected. Use gpon_connect first."
        }, ensure_ascii=False))]
    
    parts = address.split("/")
    if len(parts) != 4:
        return [types.TextContent(type="text", text=json.dumps({
            "error": f"Invalid address format: {address}"
        }, ensure_ascii=False))]
    
    frame, slot, port, ont_id = parts
    
    try:
        olt.clear_line_quality(frame, slot, port, ont_id)
        for lan_id in ["1", "2", "3", "4"]:
            olt.clear_eth_errors(frame, slot, port, ont_id, int(lan_id))
        return [types.TextContent(type="text", text=json.dumps({
            "status": "success",
            "message": f"Errors cleared for {address}"
        }, ensure_ascii=False))]
    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({
            "error": str(e)
        }, ensure_ascii=False))]


async def _tool_reset_lan_port(params: dict) -> list[types.TextContent]:
    """Reset (disable/enable) a specific LAN port on ONT."""
    session_name = params.get("session_name", "default")
    address = params["address"]
    lan_id = params["lan_id"]
    
    olt = _connection_state.get(session_name)
    if not olt:
        return [types.TextContent(type="text", text=json.dumps({
            "error": "Not connected. Use gpon_connect first."
        }, ensure_ascii=False))]
    
    parts = address.split("/")
    if len(parts) != 4:
        return [types.TextContent(type="text", text=json.dumps({
            "error": f"Invalid address format: {address}"
        }, ensure_ascii=False))]
    
    frame, slot, port, ont_id = parts
    
    try:
        olt.reset_lan_port(frame, slot, port, ont_id, lan_id)
        return [types.TextContent(type="text", text=json.dumps({
            "status": "success",
            "message": f"LAN{lan_id} reset on {address}"
        }, ensure_ascii=False))]
    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({
            "error": str(e)
        }, ensure_ascii=False))]


async def _tool_get_optics(params: dict) -> list[types.TextContent]:
    """Get real-time optical power readings from ONT."""
    session_name = params.get("session_name", "default")
    address = params["address"]

    olt = _connection_state.get(session_name)
    if not olt:
        return [types.TextContent(type="text", text=json.dumps({
            "error": "Not connected. Use gpon_connect first."
        }, ensure_ascii=False))]

    parts = address.split("/")
    if len(parts) != 4:
        return [types.TextContent(type="text", text=json.dumps({
            "error": f"Invalid address format: {address}"
        }, ensure_ascii=False))]

    frame, slot, port, ont_id = parts

    try:
        olt._gpon_ctx(frame, slot)
        optical_output = olt.send_command(f"display ont optical-info {port} {ont_id}", max_more=0)
        olt._quit_gpon()

        metrics = OntMetrics()
        parse_optical_info(optical_output, metrics)

        # Calculate power status based on thresholds
        ont_rx_status = "ok"
        if metrics.ont_rx_power < -30.0:
            ont_rx_status = "critical"
        elif metrics.ont_rx_power < -26.5:
            ont_rx_status = "warning"

        return [types.TextContent(type="text", text=json.dumps({
            "ont_rx_power": metrics.ont_rx_power,
            "ont_rx_status": ont_rx_status,
            "olt_rx_power": metrics.olt_rx_power,
            "ont_tx_power": metrics.ont_tx_power,
            "supply_voltage": metrics.supply_voltage,
            "ont_temperature": metrics.ont_temperature,
            "module_subtype": metrics.module_subtype
        }, ensure_ascii=False))]
    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({
            "error": str(e)
        }, ensure_ascii=False))]


def run():
    """Run the MCP server via stdio."""
    import mcp.server.stdio
    import asyncio
    
    asyncio.run(_run_async())


async def _run_async():
    """Async entry point."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="gpon-huawei",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )


if __name__ == "__main__":
    run()