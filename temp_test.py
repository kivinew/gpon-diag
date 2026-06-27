from web.app import app
with app.test_client() as c:
    resp = c.get('/orchestrator/tasks')
    print('status', resp.status_code)
    print('json', resp.json)
