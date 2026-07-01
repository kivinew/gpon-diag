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

# New test that loads a report from data/reports directory
def test_load_report_from_data():
    import json, os
    reports_dir = os.path.join(os.path.dirname(__file__), "..", "data", "reports")
    # Find a JSON report file
    for fname in os.listdir(reports_dir):
        if fname.lower().endswith('.json'):
            report_path = os.path.join(reports_dir, fname)
            with open(report_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Basic sanity check: ensure report has required keys
            assert 'timestamp' in data
            assert 'metrics' in data
            assert 'problems' in data
            break
    else:
        # No report files found – this test will be skipped
        raise AssertionError('No JSON report files found in data/reports')

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
    
    # Test table format with numeric description (fl_* on ONT)
    output1 = """
F/S/P   Description
0/ 0/6  0  fl_102693
"""
    result = OltConnection._parse_fsp(output1)
    assert result == {"frame": "0", "slot": "0", "port": "6", "ont_id": "0"}
    
    # Test key-value format
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

    # Serial format
    result = parse_input("4857544312E0E379")
    assert result["type"] == "serial"
    assert result["value"] == "4857544312E0E379"

    # Address format
    result = parse_input("0/1/3/9")
    assert result["type"] == "address"
    assert result["frame"] == "0"
    assert result["slot"] == "1"
    assert result["port"] == "3"
    assert result["ont_id"] == "9"

    # Description: numeric (5-16 digits) gets fl_ prefix
    result = parse_input("102693")
    assert result["type"] == "description"
    assert result["value"] == "fl_102693"

    # Description: already has prefix
    result = parse_input("fl_102693")
    assert result["type"] == "description"
    assert result["value"] == "fl_102693"

    # Description: custom string
    result = parse_input("TEST_USER")
    assert result["type"] == "description"
    assert result["value"] == "TEST_USER"

    print("PASSED: parse_input types\n")


def test_web_routes():
    """Test web application routes without OLT connection."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from web.app import app, Diagnosis, db

    with app.app_context():
        # Test ping endpoint
        with app.test_client() as client:
            resp = client.get("/ping")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "ok"

        # Test dashboard renders
        with app.test_client() as client:
            resp = client.get("/")
            assert resp.status_code == 200

        print("PASSED: web routes\n")


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

    # Check first summary
    s0 = summaries[0]
    assert s0.ont_id == "0"
    assert s0.status == "online"
    assert s0.distance == 1234
    assert s0.description == "ONT_001"
    assert s0.is_online is True

    # Check offline summary
    s2 = summaries[2]
    assert s2.status == "offline"
    assert s2.distance == -1
    assert s2.is_online is False

    print(f"  Parsed {len(summaries)} summaries: {[s.ont_id for s in summaries]}")
    print("PASSED\n")


def test_port_snapshot_model():
    """Test PortSnapshot database model exists and works."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from web.app import app, PortSnapshot, db

    with app.app_context():
        # Create a test snapshot
        snapshot = PortSnapshot(
            timestamp="2026-06-30 12:00:00",
            olt_name="OLT-TEST",
            olt_host="192.168.1.1",
            frame="0",
            slot="1",
            port="3",
            ont_count=5,
            data_json='[{"ont_id": "0", "status": "online"}]'
        )
        db.session.add(snapshot)
        db.session.commit()

        # Query it back
        retrieved = PortSnapshot.query.filter_by(olt_name="OLT-TEST").first()
        assert retrieved is not None
        assert retrieved.ont_count == 5
        assert "ont_id" in retrieved.data_json

        # Cleanup
        db.session.delete(retrieved)
        db.session.commit()

        print("PASSED: PortSnapshot model\n")


if __name__ == "__main__":
    test_offline_dying_gasp()
    test_online_healthy()
    test_low_rx()
    test_parse_fsp_fl_prefix()
    test_parse_input_types()
    test_web_routes()
    test_parse_ont_info_summary()
    test_port_snapshot_model()
    print("=" * 40)
    print("ALL TESTS PASSED")
