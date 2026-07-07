# -*- coding: utf-8 -*-
"""Flask web interface for GPON diagnostics."""

from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Flask app with database
app = Flask(__name__)
CORS(app)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///../data/diagnoses.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# Model definitions
class Diagnosis(db.Model):
    """Diagnosis report (legacy)."""
    __tablename__ = "diagnoses"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.String, nullable=False)
    olt_host = db.Column(db.String, nullable=False)
    olt_name = db.Column(db.String, nullable=False, default="")
    ont_address = db.Column(db.String, nullable=False)
    input_type = db.Column(db.String, nullable=False)
    input_value = db.Column(db.String, nullable=False)
    report_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


class PortSnapshot(db.Model):
    """Snapshot of all ONTs on a GPON port."""
    __tablename__ = "port_snapshots"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.String, nullable=False)
    olt_name = db.Column(db.String, nullable=False)
    olt_host = db.Column(db.String, nullable=False)
    frame = db.Column(db.String, nullable=False)
    slot = db.Column(db.String, nullable=False)
    port = db.Column(db.String, nullable=False)
    ont_count = db.Column(db.Integer, default=0)
    data_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


logger = logging.getLogger(__name__)

# ===================== Main Routes =====================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/result")
def result():
    return render_template("result.html")


@app.route("/ping")
def ping():
    return jsonify({"status": "ok"})


# ===================== API Endpoints =====================

@app.route("/api/diagnose", methods=["POST"])
def api_diagnose():
    return jsonify({"error": "Use FastAPI endpoints instead"}), 501


# =====================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)