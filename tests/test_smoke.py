"""Smoke tests — run diagnosis on sample data without OLT connection."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.models import OntMetrics
from core.parser import (
    parse_ont_info, parse_ont_version, parse_optical_info,
    parse_line_quality, parse_lan_ports,
)
from core.engine import create_default_engine
from core.thresholds import Thresholds
from core.report import DiagnosisReport
from datetime import datetime


def make_thresholds():
    return Thresholds(bad_versions=["V1R003C00S108", "V1R006C00S130", "V1R006C00S205", "V1R006C00S201", "V1R006C01S201"])


def test_offline_dying_gasp():
    raw = """
  F/S/P                   : 0/1/3
  ONT-ID                  : 9
  Run state               : offline
  Last down cause         : dying-gasp
  Last up time            : 2026-06-11 08:47:33+07:00
  Last down time          : 2026-06-11 10:09:33+07:00
  ONT distance(m)         : 2765
  SN                      : 4857544312E0E379 (HWTC-12E0E379)
"""
    m = OntMetrics(address="0/1/3/9", frame="0", slot="1", port="3", ont_id="9")
    parse_ont_info(raw, m)
    engine = create_default_engine(make_thresholds())
    problems = engine.diagnose(m)
    report = DiagnosisReport(datetime.now().isoformat(), "TEST", m, problems, True)

    print("=== TEST 1: Offline (dying-gasp) ===")
    print(report.to_text())
    print()
    assert not m.is_online
    assert any(p.category == "power" for p in problems)
    print("PASSED\n")


def test_online_healthy():
    raw = """
  F/S/P                   : 0/1/3
  ONT-ID                  : 15
  Run state               : online
  Last up time            : 2026-06-10 14:00:00+07:00
  ONT distance(m)         : 1200
  SN                      : 4857544312E0E400
  Description             : TEST_USER
  Memory occupation       : 45
  CPU occupation           : 30
  Temperature             : 55
"""
    raw_v = "ONT Type: HG8245H\nMain Software Version: V1R006C00S220"
    raw_opt = "Rx optical power(dBm): -18.5\nOLT Rx ONT optical power(dBm): -22.3"
    raw_q = "Upstream frame BIP error count: 0\nDownstream frame BIP error count: 0"
    raw_lan = "1  1  GE  1000  full  up"

    m = OntMetrics(address="0/1/3/15", frame="0", slot="1", port="3", ont_id="15")
    parse_ont_info(raw, m)
    parse_ont_version(raw_v, m)
    parse_optical_info(raw_opt, m)
    parse_line_quality(raw_q, m)
    parse_lan_ports(raw_lan, m)

    engine = create_default_engine(make_thresholds())
    problems = engine.diagnose(m)

    print("=== TEST 2: Online healthy ===")
    print(DiagnosisReport(datetime.now().isoformat(), "TEST", m, problems).to_text())
    print()
    assert m.is_online
    assert len(problems) == 0
    print("PASSED\n")


def test_low_rx():
    raw = """
  F/S/P                   : 0/1/3
  ONT-ID                  : 22
  Run state               : online
  Last up time            : 2026-06-09 09:00:00+07:00
  ONT distance(m)         : 4500
  SN                      : 4857544312E0E500
"""
    raw_v = "ONT Type: HG8245H\nMain Software Version: V1R006C00S220"
    raw_opt = "Rx optical power(dBm): -28.3\nOLT Rx ONT optical power(dBm): -33.1"
    raw_q = "Upstream frame BIP error count: 15000\nDownstream frame BIP error count: 8000"
    raw_lan = "1  1  GE  100  full  up"

    m = OntMetrics(address="0/1/3/22", frame="0", slot="1", port="3", ont_id="22")
    parse_ont_info(raw, m)
    parse_ont_version(raw_v, m)
    parse_optical_info(raw_opt, m)
    parse_line_quality(raw_q, m)
    parse_lan_ports(raw_lan, m)

    engine = create_default_engine(make_thresholds())
    problems = engine.diagnose(m)

    print("=== TEST 3: Low Rx + BIP errors ===")
    print(DiagnosisReport(datetime.now().isoformat(), "TEST", m, problems).to_text())
    print()
    assert any(p.category == "optic" for p in problems)
    print(f"PASSED ({len(problems)} problems)\n")


def test_parse_fsp_fl_prefix():
    """Test that _parse_fsp correctly handles fl_ prefix for numeric descriptions."""
    from core.olt import OltConnection

    output1 = """
F/S/P   Description
0/ 0/6  0  fl_102693
"""
    result = OltConnection._parse_fsp(output1)
    assert result == {"frame": "0", "slot": "0", "port": "6", "ont_id": "0"}

    output2 = """
F/S/P                   : 0/1/3
ONT-ID                  : 9
Description             : fl_102693
"""
    result = OltConnection._parse_fsp(output2)
    assert result == {"frame": "0", "slot": "1", "port": "3", "ont_id": "9"}


def test_parse_input_types():
    """Test parse_input for serial, address and description recognition."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.utils import parse_input

    result = parse_input("4857544312E0E379")
    assert result["type"] == "serial"
    assert result["value"] == "4857544312E0E379"

    result = parse_input("0/1/3/9")
    assert result["type"] == "address"
    assert result["frame"] == "0"
    assert result["slot"] == "1"
    assert result["port"] == "3"
    assert result["ont_id"] == "9"

    result = parse_input("102693")
    assert result["type"] == "description"
    assert result["value"] == "fl_102693"

    result = parse_input("fl_102693")
    assert result["type"] == "description"
    assert result["value"] == "fl_102693"

    result = parse_input("TEST_USER")
    assert result["type"] == "description"
    assert result["value"] == "TEST_USER"

    print("PASSED: parse_input types\n")


def test_parse_ont_info_summary():
    """Test parsing of 'display ont info summary' output."""
    from core.parser import parse_ont_info_summary
    from core.models import OntSummary

    raw = """
  --------------------------------------------------------------------------------
  F/S/P                 : 0/1/3
  ONT-ID  Run state   Config state  Match state  ONT distance  Description
  --------------------------------------------------------------------------------
  0       online      normal        match        1234          ONT_001
  1       online      normal        match        1500          ONT_002
  2       offline     normal        -            -             ONT_003
  3       online      normal        match        800           office_004
  --------------------------------------------------------------------------------
"""
    summaries = parse_ont_info_summary(raw)

    print("=== TEST 5: parse_ont_info_summary ===")
    assert len(summaries) == 4, f"Expected 4 summaries, got {len(summaries)}"

    s0 = summaries[0]
    assert s0.ont_id == "0"
    assert s0.status == "online"
    assert s0.distance == 1234
    assert s0.description == "ONT_001"
    assert s0.is_online is True

    s2 = summaries[2]
    assert s2.status == "offline"
    assert s2.distance == -1
    assert s2.is_online is False

    print(f"  Parsed {len(summaries)} summaries: {[s.ont_id for s in summaries]}")
    print("PASSED\n")


if __name__ == "__main__":
    test_offline_dying_gasp()
    test_online_healthy()
    test_low_rx()
    test_parse_fsp_fl_prefix()
    test_parse_input_types()
    test_parse_ont_info_summary()
    print("=" * 40)
    print("ALL TESTS PASSED")