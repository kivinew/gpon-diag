"""Smoke tests for loop_runner — verify task queue and runner logic without OLT connection."""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.loop_runner import LoopTask, TaskQueue, create_diagnose_tasks


def test_task_creation():
    """Test that tasks are created correctly."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        queue_path = f.name

    try:
        onts = ["0/1/3/9", "0/1/3/15", "4857544312E0E379"]
        tasks = create_diagnose_tasks(onts, olt="TEST-OLT", no_actions=True)

        queue = TaskQueue(queue_path)
        queue.add_batch(tasks)

        assert len(queue.tasks) == 3
        assert queue.tasks[0].type == "diagnose"
        assert queue.tasks[0].payload["ont_id"] == "0/1/3/9"
        assert queue.tasks[0].payload["olt"] == "TEST-OLT"
        print("✓ Task creation: PASSED")
    finally:
        os.unlink(queue_path)


def test_task_queue_persistence():
    """Test that task queue persists correctly."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        queue_path = f.name

    try:
        queue1 = TaskQueue(queue_path)
        queue1.add(LoopTask(id="test_1", type="diagnose", payload={"x": 1}))

        # Reload
        queue2 = TaskQueue(queue_path)
        assert len(queue2.tasks) == 1
        assert queue2.tasks[0].id == "test_1"
        print("✓ Queue persistence: PASSED")
    finally:
        os.unlink(queue_path)


def test_task_status_transitions():
    """Test task status transitions."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        queue_path = f.name

    try:
        queue = TaskQueue(queue_path)
        queue.add(LoopTask(id="test_status", type="diagnose", payload={}))

        assert queue.tasks[0].status == "pending"

        queue.mark_running("test_status")
        assert queue.tasks[0].status == "running"

        queue.mark_done("test_status", {"result": "ok"})
        assert queue.tasks[0].status == "done"

        # Test failed task handling
        queue2 = TaskQueue(queue_path)
        queue2.add(LoopTask(id="test_retry", type="diagnose", payload={}, max_attempts=1))
        queue2.mark_failed("test_retry", "test error")
        
        queue3 = TaskQueue(queue_path)
        assert queue3.tasks[1].status == "failed"
        print("✓ Status transitions: PASSED")
    finally:
        os.unlink(queue_path)


def test_stats():
    """Test queue statistics."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        queue_path = f.name

    try:
        queue = TaskQueue(queue_path)
        queue.add(LoopTask(id="a", type="diagnose", payload={}))
        queue.add(LoopTask(id="b", type="diagnose", payload={}))
        queue.mark_running("a")

        stats = queue.stats()
        assert stats["total"] == 2
        assert stats["pending"] == 1
        assert stats["running"] == 1
        print("✓ Stats: PASSED")
    finally:
        os.unlink(queue_path)


if __name__ == "__main__":
    test_task_creation()
    test_task_queue_persistence()
    test_task_status_transitions()
    test_stats()
    print("\n" + "=" * 40)
    print("ALL LOOP RUNNER TESTS PASSED")