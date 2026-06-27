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
    return `<div class="task-item status-${task.status}">
        <strong>${task.task_id}</strong>: ${task.title}
        <div>Зона: <span class="agent-zone">${task.zone}</span> | Попытки: ${task.revision_count}</div>
        ${errors}
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

async function verifyAllTasks() {
    const response = await fetch('/orchestrator/tasks');
    const data = await response.json();
    
    for (const task of data.tasks) {
        if (task.status === 'in_progress') {
            await fetch('/orchestrator/verify', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_id: task.task_id})
            });
        }
    }
    loadTasks();
}