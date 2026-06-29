"""Flask web interface for GPON diagnostics."""

import os
import json
import sys
import queue
import threading
import time
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

TZ_LOCAL = timezone(timedelta(hours=7))

from flask import Flask, render_template, request, redirect, url_for, flash, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from diagnose import load_config, find_available_olt, parse_input, run_diagnosis, _load_olt_credentials, sanitize_ont_param
from core.olt import OntNotFoundError, get_olt_connection, close_all
from core.thresholds import Thresholds
from core.parser import parse_ont_info, parse_optical_info, parse_line_quality
from core.models import OntMetrics

app = Flask(__name__)
app.debug = False
app.config["SECRET_KEY"] = os.urandom(24)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "diagnoses.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class Diagnosis(db.Model):
    __tablename__ = "diagnoses"
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.String, nullable=False)
    olt_host = db.Column(db.String, nullable=False)
    olt_name = db.Column(db.String, nullable=False, default="")
    ont_address = db.Column(db.String, nullable=False)
    input_type = db.Column(db.String, nullable=False)
    input_value = db.Column(db.String, nullable=False)
    report_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(TZ_LOCAL))

with app.app_context():
    db.create_all()
    try:
        db.session.execute(text("SELECT olt_name FROM diagnoses LIMIT 1"))
    except Exception:
        db.session.execute(text("ALTER TABLE diagnoses ADD COLUMN olt_name TEXT NOT NULL DEFAULT ''"))
        db.session.commit()

def build_thresholds(config):
    t = config.get("thresholds", {})
    return Thresholds(
        ont_rx_power_warn=t.get("ont_rx_power_warn_dbm", -26.0),
        ont_rx_power_crit=t.get("ont_rx_power_crit_dbm", -30.0),
        olt_rx_power_warn=t.get("olt_rx_power_warn_dbm", -32.0),
        olt_rx_power_crit=t.get("olt_rx_power_crit_dbm", -35.0),
        bip_error_warn=t.get("bip_error_warn", 10000),
        bip_error_crit=t.get("bip_error_crit", 100000),
        cpu_temp_warn=t.get("cpu_temp_warn_c", 75),
        cpu_temp_crit=t.get("cpu_temp_crit_c", 85),
        cpu_usage_warn=t.get("cpu_usage_warn_pct", 80),
        memory_usage_warn=t.get("memory_usage_warn_pct", 85),
        distance_warn=t.get("distance_warn_m", 15000),
        distance_crit=t.get("distance_crit_m", 20000),
        bad_versions=t.get("bad_versions", []),
        no_ping_models=t.get("no_ping_models", []),
    )

def find_olt_by_host(config, host):
    for olt in config.get("olts", []):
        if olt.get("host") == host:
            return olt
    return None

@app.route("/api/diagnose", methods=["POST"])
def api_diagnose():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    olt_host = data.get("olt_host", "").strip()

    if not query:
        return {"error": "Введите запрос."}, 400

    config = load_config()

    if olt_host:
        olt_config = find_olt_by_host(config, olt_host)
        if not olt_config:
            return {"error": f"OLT {olt_host} не найден."}, 400
    else:
        olt_config = find_available_olt(config)
        if not olt_config:
            return {"error": "Нет доступных OLT."}, 400

    log_q = queue.Queue()

    def log_fn(msg, end=" ", flush=True):
        text = str(msg)
        print(text, flush=flush)
        log_q.put(text)

    def worker():
        with app.app_context():
            try:
                # First, search for historical results (in try block to avoid breaking diagnosis)
                input_data = parse_input(query)
                ont_address = None
                search_terms = []

                if input_data["type"] == "address":
                    ont_address = f"{input_data['frame']}/{input_data['slot']}/{input_data['port']}/{input_data['ont_id']}"
                    search_terms.append(ont_address)
                elif input_data["type"] == "serial":
                    search_terms.append(input_data["value"])
                elif input_data["type"] == "description":
                    search_terms.append(input_data["value"])

                # Query history before running diagnosis
                if search_terms:
                    try:
                        conditions = []
                        for term in search_terms:
                            conditions.append(Diagnosis.ont_address.contains(term))
                            conditions.append(Diagnosis.input_value.contains(term))
                        if conditions:
                            history_records = Diagnosis.query.filter(
                                db.or_(*conditions)
                            ).order_by(Diagnosis.created_at.desc()).limit(10).all()
                        else:
                            history_records = []

                        history_results = []
                        for record in history_records:
                            try:
                                report_data = json.loads(record.report_json) if record.report_json else {}
                            except (json.JSONDecodeError, TypeError):
                                report_data = {}
                            history_results.append({
                                "id": record.id,
                                "created_at": record.created_at.strftime("%d.%m.%Y %H:%M"),
                                "olt_name": record.olt_name,
                                "ont_address": record.ont_address,
                                "report": report_data,
                            })

                        if history_results:
                            log_q.put({"type": "history", "history": history_results})
                    except Exception as hist_err:
                        logger.warning(f"History search failed: {hist_err}")

                thresholds = build_thresholds(config)

                def on_olt_info(info):
                    log_q.put({"type": "olt_info", "model": info["model"],
                               "uptime": info["uptime"], "version": info["version"]})

                report = run_diagnosis(input_data, olt_config, thresholds,
                                       allow_actions=False, log=log_fn,
                                       ping_target=config.get("ping_target", "1.1.1.1"),
                                       on_olt_info=on_olt_info)

                diag = Diagnosis(
                    timestamp=report.timestamp,
                    olt_host=olt_config.get("host", ""),
                    olt_name=olt_config.get("name", ""),
                    ont_address=report.metrics.address,
                    input_type=input_data["type"],
                    input_value=(input_data.get("value")
                                 if input_data["type"] != "address"
                                 else f"{input_data['frame']}/{input_data['slot']}/{input_data['port']}/{input_data['ont_id']}"),
                    report_json=json.dumps(report.to_dict(), ensure_ascii=False),
                )
                db.session.add(diag)
                db.session.commit()

                log_q.put({"type": "result", "report": report.to_text()})

            except OntNotFoundError:
                olt_label = olt_config.get("name", olt_config.get("host", ""))
                olt_ip = olt_config.get("host", "")
                msg = f"На головной станции {olt_label} ({olt_ip}) терминал {query} не обнаружен."
                log_q.put({"type": "error", "message": msg})
            except (TimeoutError, OSError) as exc:
                olt_label = olt_config.get("name", olt_config.get("host", ""))
                olt_ip = olt_config.get("host", "")
                msg = f"Не удалось подключиться к головной станции {olt_label} ({olt_ip}). Проверьте доступность: {exc}"
                log_q.put({"type": "error", "message": msg})
            except Exception as exc:
                import traceback
                logger.exception(f"Diagnosis error for {query}: {exc}")
                log_q.put({"type": "error", "message": f"{exc}\n{traceback.format_exc()}"})
            finally:
                log_q.put(None)

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    def generate():
        while True:
            try:
                item = log_q.get(timeout=120)
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Таймаут подключения к головной станции.'})}\n\n"
                return
            if item is None:
                return
            if isinstance(item, dict):
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'log', 'line': str(item)}, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/", methods=["GET"])
def index():
    config = load_config()
    olts = config.get("olts", [])
    history = Diagnosis.query.order_by(Diagnosis.created_at.desc()).limit(20).all()
    return render_template("index.html", olts=olts, history=history)

@app.route("/dashboard", methods=["GET"])
def dashboard():
    config = load_config()
    olts = config.get("olts", [])
    history = Diagnosis.query.order_by(Diagnosis.created_at.desc()).limit(20).all()
    return render_template("dashboard.html", olts=olts, history=history)

# Simple health-check endpoint for diagnostics
@app.route("/ping", methods=["GET"])
def ping():
    return {"status": "ok"}

@app.route("/api/search", methods=["POST"])
def api_search():
    """Search for ONTs by serial, address, or description across OLT(s)."""
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    olt_host = data.get("olt_host", "").strip()

    if not query:
        return {"error": "Введите запрос для поиска."}, 400

    config = load_config()
    olts_to_search = []

    if olt_host:
        olt_config = find_olt_by_host(config, olt_host)
        if not olt_config:
            return {"error": f"OLT {olt_host} не найден."}, 400
        olts_to_search = [olt_config]
    else:
        olts_to_search = config.get("olts", [])

    # Search across all OLTs
    all_results = []
    for olt_config in olts_to_search:
        host = olt_config["host"]
        port = olt_config.get("port", 23)
        username, password = _load_olt_credentials(olt_config)
        if not username or not password:
            continue

        try:
            olt = get_olt_connection(host, port, username, password, 15)
            olt.connect()
            # Wait for connection to stabilize after login
            time.sleep(1)

            # Parse query type
            input_data = parse_input(query)

            if input_data["type"] == "serial":
                loc = olt.find_ont_by_sn(input_data["value"])
                if loc:
                    input_data.update(loc)
            elif input_data["type"] == "address":
                # Already have frame/slot/port/ont_id
                pass
            elif input_data["type"] == "description":
                loc = olt.find_ont_by_description(input_data["value"])
                if loc:
                    input_data.update(loc)

            # If we have address, collect basic info
            if "frame" in input_data and "slot" in input_data and "port" in input_data and "ont_id" in input_data:
                # Quick collect basic info
                raw_data = olt.collect_ont(
                    sanitize_ont_param(input_data["frame"]),
                    sanitize_ont_param(input_data["slot"]),
                    sanitize_ont_param(input_data["port"]),
                    sanitize_ont_param(input_data["ont_id"]),
                    log=lambda *a, **k: None
                )

                metrics = OntMetrics()
                metrics.address = f"{input_data['frame']}/{input_data['slot']}/{input_data['port']}/{input_data['ont_id']}"
                metrics.frame = input_data["frame"]
                metrics.slot = input_data["slot"]
                metrics.port = input_data["port"]
                metrics.ont_id = input_data["ont_id"]

                if "ont_info" in raw_data:
                    parse_ont_info(raw_data["ont_info"], metrics)
                if "optical_info" in raw_data:
                    parse_optical_info(raw_data["optical_info"], metrics)

                all_results.append({
                    "ont_address": metrics.address,
                    "olt_host": host,
                    "olt_name": olt_config.get("name", host),
                    "serial": metrics.serial,
                    "description": metrics.description,
                    "is_online": metrics.is_online,
                    "model": metrics.model,
                    "ont_rx_power": metrics.ont_rx_power,
                    "olt_rx_power": metrics.olt_rx_power,
                    "distance_m": metrics.distance_m
                })

            close_all()

        except Exception as e:
            logger.warning(f"Search failed on {host}: {e}")
            continue

    return {"results": all_results}

@app.route("/api/optics", methods=["GET"])
def api_optics():
    """Get real-time optics data for a specific ONT."""
    address = request.args.get("address", "").strip()
    olt_host = request.args.get("olt_host", "").strip()

    if not address or not olt_host:
        return {"error": "Укажите адрес ONT и OLT."}, 400

    config = load_config()
    olt_config = find_olt_by_host(config, olt_host)
    if not olt_config:
        return {"error": f"OLT {olt_host} не найден."}, 400

    host = olt_config["host"]
    port = olt_config.get("port", 23)
    username, password = _load_olt_credentials(olt_config)
    if not username or not password:
        return {"error": "Нет учетных данных для OLT."}, 400

    # Parse address F/S/P/ONT
    parts = address.split("/")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        return {"error": "Неверный формат адреса. Ожидается F/S/P/ONT."}, 400

    frame, slot, port_, ont_id = parts

    try:
        olt = get_olt_connection(host, port, username, password, 15)
        olt.connect()

        raw_data = olt.collect_ont(
            sanitize_ont_param(frame),
            sanitize_ont_param(slot),
            sanitize_ont_param(port_),
            sanitize_ont_param(ont_id),
            log=lambda *a, **k: None
        )

        metrics = OntMetrics()
        metrics.address = address
        metrics.frame = frame
        metrics.slot = slot
        metrics.port = port_
        metrics.ont_id = ont_id

        if "optical_info" in raw_data:
            parse_optical_info(raw_data["optical_info"], metrics)
        if "ont_info" in raw_data:
            parse_ont_info(raw_data["ont_info"], metrics)
        if "line_quality" in raw_data:
            parse_line_quality(raw_data["line_quality"], metrics)

        close_all()

        return {
            "ont_rx_power": metrics.ont_rx_power,
            "olt_rx_power": metrics.olt_rx_power,
            "ont_tx_power": metrics.ont_tx_power,
            "laser_bias_current": metrics.laser_bias_current,
            "ont_temperature": metrics.ont_temperature,
            "supply_voltage": metrics.supply_voltage,
            "distance_m": metrics.distance_m,
            "upstream_errors": metrics.upstream_errors,
            "downstream_errors": metrics.downstream_errors,
            "total_bip_errors": metrics.total_bip_errors,
            "is_online": metrics.is_online,
            "model": metrics.model,
            "serial": metrics.serial,
            "description": metrics.description
        }

    except Exception as e:
        logger.exception(f"Optics fetch error: {e}")
        return {"error": str(e)}, 500

@app.route("/api/history/<int:diag_id>", methods=["GET"])
def api_history_detail(diag_id):
    """Return a single diagnosis record by ID."""
    record = Diagnosis.query.get(diag_id)
    if not record:
        return {"error": "Запись не найдена."}, 404
    try:
        report_data = json.loads(record.report_json) if record.report_json else {}
    except (json.JSONDecodeError, TypeError):
        report_data = {}
    return {
        "id": record.id,
        "timestamp": record.timestamp,
        "created_at": record.created_at.strftime("%d.%m.%Y %H:%M"),
        "olt_name": record.olt_name,
        "olt_host": record.olt_host,
        "ont_address": record.ont_address,
        "input_type": record.input_type,
        "input_value": record.input_value,
        "report": report_data,
        "is_online": report_data.get("is_online", True),
    }


@app.route("/api/history", methods=["GET"])
def api_history():
    """Search historical diagnosis results by ONT address, serial, or description.
    If no query provided, returns all history (limited)."""
    query = request.args.get("q", "").strip()
    limit = request.args.get("limit", 20, type=int)

    q = Diagnosis.query
    if query:
        q = q.filter(
            db.or_(
                Diagnosis.ont_address.contains(query),
                Diagnosis.input_value.contains(query),
            )
        )

    history_records = q.order_by(Diagnosis.created_at.desc()).limit(limit).all()

    results = []
    for record in history_records:
        try:
            report_data = json.loads(record.report_json) if record.report_json else {}
        except (json.JSONDecodeError, TypeError):
            report_data = {}
        results.append({
            "id": record.id,
            "timestamp": record.timestamp,
            "created_at": record.created_at.strftime("%d.%m.%Y %H:%M"),
            "olt_name": record.olt_name,
            "olt_host": record.olt_host,
            "ont_address": record.ont_address,
            "input_type": record.input_type,
            "input_value": record.input_value,
            "report": report_data,
            "is_online": report_data.get("is_online", True),
        })

    return {"history": results}


@app.route("/orchestrator", methods=["GET"])
def orchestrator_index():
    from orchestrator.agent_registry import AgentRegistry
    from orchestrator.task_card import TaskStatus
    registry = AgentRegistry()
    agents = registry.list_all()
    return render_template("orchestrator/index.html", agents=agents)


@app.route("/orchestrator/tasks", methods=["GET"])
def orchestrator_tasks():
    from orchestrator.task_card import list_task_cards, TaskStatus
    cards = list_task_cards()
    tasks = []
    for c in cards:
        tasks.append({
            "task_id": c.task_id,
            "title": c.title,
            "agent_id": c.agent_id,
            "status": c.status.value,
            "zone": c.zone,
            "revision_count": c.revision_count,
            "errors": c.errors,
        })
    return {"tasks": tasks}


@app.route("/orchestrator/agents", methods=["GET"])
def orchestrator_agents():
    from orchestrator.agent_registry import AgentRegistry, AgentStatus
    registry = AgentRegistry()
    agents = registry.list_all()
    agent_data = []
    for aid, info in agents.items():
        agent_data.append({
            "agent_id": info.agent_id,
            "zone": info.zone,
            "status": info.status.value,
            "files_intended": info.files_intended,
            "error_message": info.error_message,
        })
    return {"agents": agent_data}


@app.route("/orchestrator/verify", methods=["POST"])
def orchestrator_verify():
    from orchestrator.external_control import ExternalControlLoop
    from orchestrator.agent_registry import AgentRegistry
    task_id = request.json.get("task_id")
    loop = ExternalControlLoop(os.path.dirname(os.path.dirname(__file__)), AgentRegistry())
    result = loop.verify_and_update(task_id)
    return {"success": result.success, "errors": result.errors, "warnings": result.warnings}


@app.route("/orchestrator/create_task", methods=["POST"])
def orchestrator_create_task():
    from orchestrator.task_card import create_task_card
    data = request.json or {}
    card = create_task_card(
        title=data.get("title", ""),
        description=data.get("description", ""),
        zone=data.get("zone", "model"),
        verification_criteria=data.get("criteria", []),
        metadata=data.get("metadata"),
    )
    return {"task_id": card.task_id, "status": card.status.value}


@app.route("/orchestrator/set_status", methods=["POST"])
def orchestrator_set_status():
    from orchestrator.task_card import load_task_card, TaskStatus
    task_id = request.json.get("task_id")
    status_val = request.json.get("status")
    card = load_task_card(task_id)
    if not card:
        return {"error": "Task not found"}, 404
    card.status = TaskStatus(status_val)
    card.agent_id = request.json.get("agent_id", "")
    card.save()
    return {"task_id": task_id, "status": card.status.value}

if __name__ == "__main__":
    # Production server is started via scripts/check_and_start_server.py
    pass
