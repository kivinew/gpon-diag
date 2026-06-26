"""Flask web interface for GPON diagnostics."""

import os
import json
import sys
import queue
import threading
from datetime import datetime, timezone, timedelta

TZ_LOCAL = timezone(timedelta(hours=7))

from flask import Flask, render_template, request, redirect, url_for, flash, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from diagnose import load_config, find_available_olt, parse_input, run_diagnosis
from core.olt import OntNotFoundError
from core.thresholds import Thresholds

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
                input_data = parse_input(query)
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
            except Exception as exc:
                log_q.put({"type": "error", "message": str(exc)})
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

# Simple health‑check endpoint for diagnostics
@app.route("/ping", methods=["GET"])
def ping():
    return {"status": "ok"}

if __name__ == "__main__":
    # Production server is started via scripts/run_server.py
    pass
