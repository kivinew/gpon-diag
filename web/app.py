# -*- coding: utf-8 -*-
"""Flask web interface with orchestrator endpoints for AI agent task management."""

from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Flask app with database
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///../data/diagnoses.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Import models for test compatibility
from web.api.models import Diagnosis, PortSnapshot

from orchestrator.agent_registry import AgentRegistry, AgentStatus
from orchestrator.task_card import (
    TaskCard, TaskStatus, create_task_card, load_task_card, list_task_cards
)
from orchestrator.outer_loop import OuterLoopController, TaskSpec, ValidationLevel
from orchestrator.external_control import ExternalControlLoop

logger = logging.getLogger(__name__)

# Registry singleton
_registry = AgentRegistry()
_outer_loop = OuterLoopController(project_root=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_runner = ExternalControlLoop(
    project_root=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    registry=_registry
)

# ===================== Orchestrator Web UI =====================

@app.route("/orchestrator/")
def orchestrator_index():
    return render_template("orchestrator/index.html")


# ===================== Task Endpoints =====================

@app.route("/orchestrator/tasks")
def get_tasks():
    tasks = [card.to_dict() for card in list_task_cards()]
    return jsonify({"tasks": tasks})


@app.route("/orchestrator/create_task", methods=["POST"])
def create_task():
    data = request.get_json() or {}
    title = data.get("title", "Без названия")
    description = data.get("description", "")
    zone = data.get("zone", "parser")

    card = create_task_card(
        title=title,
        description=description,
        zone=zone,
        verification_criteria=["check_code"],
    )

    return jsonify({"task_id": card.task_id, "status": card.status.value})


@app.route("/orchestrator/set_status", methods=["POST"])
def set_status():
    data = request.get_json() or {}
    task_id = data.get("task_id")
    status = data.get("status")
    agent_id = data.get("agent_id", "")

    if not task_id:
        return jsonify({"error": "task_id required"}), 400

    card = load_task_card(task_id)
    if not card:
        return jsonify({"error": f"Task {task_id} not found"}), 404

    old_status = card.status
    if status == "in_progress":
        card.status = TaskStatus.IN_PROGRESS
        card.agent_id = agent_id
        card.revision_count += 1  # Increment attempt count
        card.updated_at = __import__("time").time()
        card.save()

        # Register agent in registry
        zone = card.zone
        try:
            _registry.register(
                agent_id=agent_id,
                zone=zone,
                files_intended=card.metadata.get("files_intended", []),
            )
            _registry.set_status(agent_id, AgentStatus.ACTIVE)
        except ValueError:
            pass  # Agent may already be registered

    elif status == "completed":
        card.status = TaskStatus.COMPLETED
        card.updated_at = __import__("time").time()
        card.save()
        if agent_id:
            _registry.set_status(agent_id, AgentStatus.COMPLETED)

    elif status == "verification_pending":
        card.status = TaskStatus.VERIFICATION_PENDING
        card.agent_id = agent_id
        card.updated_at = __import__("time").time()
        card.save()

    return jsonify({"task_id": task_id, "status": card.status.value, "revision_count": card.revision_count})


@app.route("/orchestrator/delete_task/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    card = load_task_card(task_id)
    if card:
        path = card._path()
        if os.path.exists(path):
            os.remove(path)
            dir_path = os.path.dirname(path)
            if os.path.exists(dir_path):
                try:
                    os.rmdir(dir_path)
                except OSError:
                    pass
    return jsonify({"status": "deleted"})


@app.route("/orchestrator/verify", methods=["POST"])
def verify_task():
    data = request.get_json() or {}
    task_id = data.get("task_id")

    if not task_id:
        return jsonify({"error": "task_id required"}), 400

    card = load_task_card(task_id)
    if not card:
        return jsonify({"error": f"Task {task_id} not found"}), 404

    result = _runner.verify_and_update(task_id)

    if result.success:
        card.status = TaskStatus.COMPLETED
    else:
        card.status = TaskStatus.REVISION_REQUIRED
        card.errors = result.errors
        card.revision_count += 1  # Increment on revision needed

    card.save()

    return jsonify({
        "task_id": task_id,
        "passed": result.success,
        "errors": result.errors,
        "warnings": result.warnings,
    })


@app.route("/orchestrator/agents")
def get_agents():
    from orchestrator import list_agents
    agents = list_agents()
    return jsonify({"agents": agents})


@app.route("/orchestrator/register_agent", methods=["POST"])
def register_agent():
    from orchestrator import _ensure_global_registry
    data = request.get_json() or {}
    agent_id = data.get("agent_id")
    zone = data.get("zone")

    if not agent_id or not zone:
        return jsonify({"error": "agent_id and zone required"}), 400

    registry = _ensure_global_registry()
    try:
        registry.register(agent_id=agent_id, zone=zone, files_intended=[], metadata={})
        registry.set_status(agent_id, AgentStatus.ACTIVE)
        return jsonify({"status": "registered", "agent_id": agent_id})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/orchestrator/heartbeat", methods=["POST"])
def heartbeat():
    data = request.get_json() or {}
    agent_id = data.get("agent_id")
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400
    _registry.heartbeat(agent_id)
    return jsonify({"status": "ok"})


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