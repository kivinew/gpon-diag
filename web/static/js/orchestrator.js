document.addEventListener('DOMContentLoaded', () => {
    loadTasks();
    loadAgents();
    
    document.getElementById('create-task-form').addEventListener('submit', (e) => {
        e.preventDefault();
        createTask();
    });
});

async function loadTasks() {
    const container = document.getElementById('tasks-container');
    try {
        const response = await fetch('/orchestrator/tasks');
        const data = await response.json();
        container.innerHTML = data.tasks.map(renderTask).join('') || '<p>Нет задач</p>';
    } catch (err) {
        container.innerHTML = '<p class="error">Ошибка загрузки задач</p>';
    }
}

async function loadAgents() {
    const container = document.getElementById('agents-container');
    try {
        const response = await fetch('/orchestrator/agents');
        const data = await response.json();
        container.innerHTML = data.agents.map(renderAgent).join('') || '<p>Нет агентов</p>';
    } catch (err) {
        container.innerHTML = '<p class="error">Ошибка загрузки агентов</p>';
    }
}

function renderTask(task) {
    const errors = task.errors.length ? `<div class="error-list">Ошибки: ${task.errors.join(', ')}</div>` : '';
    const assignBtn = task.status === 'pending' ? `<button class="btn btn-small" onclick="assignAgentPrompt('${task.task_id}')">Назначить агента</button>` : '';
    return `<div class="task-item status-${task.status}">
        <strong>${task.task_id}</strong>: ${task.title}
        <div>Зона: <span class="agent-zone">${task.zone}</span> | Статус: ${task.status} | Попытки: ${task.revision_count}</div>
        ${errors}
        <button class="btn" onclick="deleteTask('${task.task_id}')">Удалить</button>
        ${assignBtn}
    </div>`;
}

function renderAgent(agent) {
    return `<div class="agent-item">
        <span class="agent-id">${agent.agent_id}</span>
        <span class="agent-zone">${agent.zone}</span>
        <span class="status-badge ${agent.status}">${agent.status}</span>
    </div>`;
}

async function createTask() {
    const title = document.getElementById('task-title').value;
    const description = document.getElementById('task-description').value;
    const zone = document.getElementById('task-zone').value;
    const agent = document.getElementById('task-agent').value;
    
    const response = await fetch('/orchestrator/create_task', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({title, description, zone, agent_id: agent})
    });
    
    if (response.ok) {
        document.getElementById('create-task-form').reset();
        loadTasks();
    }
}

async function assignAgentPrompt(taskId) {
    const agentId = prompt('Введите ID агента:');
    if (!agentId) return;
    await fetch('/orchestrator/set_status', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({task_id: taskId, status: 'in_progress', agent_id: agentId})
    });
    loadTasks();
}

async function registerAgentPrompt() {
    const agentId = prompt('Введите ID агента (например: claude, parser_bot):');
    if (!agentId) return;
    const zone = prompt('Введите зону (parser, engine, model, connection, report, web, cli):');
    if (!zone) return;
    await fetch('/orchestrator/register_agent', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({agent_id: agentId, zone: zone})
    });
    loadAgents();
}

async function deleteTask(taskId) {
    if (!confirm('Удалить задачу ' + taskId + '?')) return;
    await fetch('/orchestrator/delete_task/' + taskId, {method: 'DELETE'});
    loadTasks();
}

async function verifyAllTasks() {
    try {
        const response = await fetch('/orchestrator/tasks');
        const data = await response.json();

        console.log('Tasks to verify:', data.tasks);

        for (const task of data.tasks) {
            // Check tasks that need validation
            if (['pending', 'in_progress', 'verification_pending'].includes(task.status)) {
                console.log('Verifying task:', task.task_id);
                try {
                    const verifyResp = await fetch('/orchestrator/verify', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({task_id: task.task_id})
                    });
                    const result = await verifyResp.json();
                    console.log('Verify result for ' + task.task_id + ':', result);
                } catch (err) {
                    console.error('Verify error for ' + task.task_id + ':', err);
                }
            }
        }
        loadTasks();
    } catch (err) {
        console.error('Failed to load tasks:', err);
        alert('Ошибка: ' + err.message);
    }
}