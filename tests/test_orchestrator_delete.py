import os
import pytest
from web.app import app
from orchestrator import OuterLoopController, delete_task_from_queue
from orchestrator.outer_loop import TaskSpec, ZONE_PARSER

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def _create_task(controller, task_id: str):
    # TaskSpec requires files_intended – give empty list for test
    spec = TaskSpec(task_id=task_id, zone=ZONE_PARSER, description='test task', files_intended=[])
    controller.register_task(spec)
    return spec

def test_delete_task_success(client):
    ctrl = OuterLoopController(project_root=os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    task_id = 'test-delete-1'
    _create_task(ctrl, task_id)
    # Ensure task exists via controller
    assert ctrl.get_task_status(task_id) is not None
    # Call delete endpoint
    resp = client.post('/orchestrator/delete_task', json={'task_id': task_id})
    assert resp.status_code == 200
    assert resp.get_json().get('status') == 'deleted'
    # After deletion task should no longer be in controller
    with pytest.raises(KeyError):
        ctrl.get_task_status(task_id)

def test_delete_task_nonexistent(client):
    resp = client.post('/orchestrator/delete_task', json={'task_id': 'does-not-exist'})
    assert resp.status_code == 400
    assert 'error' in resp.get_json()
