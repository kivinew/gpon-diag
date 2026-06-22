"""Flask web interface for GPON diagnostics.

Provides a simple HTML form where the user can input:
- serial number (SN),
- description (лицевой счёт), or
- ONT address in the form F/S/P/ONT (e.g. ``0/1/1/5``).

The backend reuses existing core functions (`load_config`, `find_available_olt`,
`parse_input`, `run_diagnosis`) to perform the diagnosis and stores the
resulting report JSON in an SQLite database.  The rendered result shows the
human‑readable text report with a **Копировать** button that copies the report
to the clipboard using the browser API.
"""

import os
import json
from datetime import datetime, timezone, timedelta

TZ_LOCAL = timezone(timedelta(hours=7))
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

# Ensure the project root is in PYTHONPATH for core imports
import sys
sys.path.append(os.path.abspath(os.path.dirname(__file__) + os.sep + ".."))

from diagnose import load_config, find_available_olt, parse_input, run_diagnosis
from core.thresholds import Thresholds

app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24)
# SQLite DB stored under data/diagnoses.db
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "diagnoses.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class Diagnosis(db.Model):
    __tablename__ = "diagnoses"
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.String, nullable=False)          # ISO timestamp from report
    olt_host = db.Column(db.String, nullable=False)
    olt_name = db.Column(db.String, nullable=False, default="")
    ont_address = db.Column(db.String, nullable=False)
    input_type = db.Column(db.String, nullable=False)        # "serial", "description", or "address"
    input_value = db.Column(db.String, nullable=False)       # raw value entered by user
    report_json = db.Column(db.Text, nullable=False)         # full JSON report
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(TZ_LOCAL))

# Create tables if they do not exist
with app.app_context():
    db.create_all()
    # Migration: add olt_name column if missing
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

@app.route("/", methods=["GET", "POST"])
def index():
    config = load_config()
    olts = config.get("olts", [])
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        olt_host = request.form.get("olt_host", "").strip()
        if not query:
            flash("Введите запрос.", "error")
            return redirect(url_for("index"))
        try:
            if olt_host:
                olt_config = find_olt_by_host(config, olt_host)
                if not olt_config:
                    flash(f"OLT {olt_host} не найден в конфигурации.", "error")
                    return redirect(url_for("index"))
            else:
                olt_config = find_available_olt(config)
                if not olt_config:
                    flash("Нет доступных OLT в конфигурации.", "error")
                    return redirect(url_for("index"))
            input_data = parse_input(query)
            thresholds = build_thresholds(config)
            report = run_diagnosis(input_data, olt_config, thresholds, allow_actions=False)
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
            history = Diagnosis.query.order_by(Diagnosis.created_at.desc()).limit(10).all()
            return render_template("result.html",
                                   report_text=report.to_text(),
                                   history=history,
                                   olt_name=olt_config.get("name", ""),
                                   olt_host=olt_config.get("host", ""))
        except Exception as exc:
            flash(f"Ошибка: {exc}", "error")
            return redirect(url_for("index"))
    return render_template("index.html", olts=olts)

if __name__ == "__main__":
    # For development use the built‑in server; production should use a WSGI server.
    app.run(host="0.0.0.0", port=5000, debug=True)
