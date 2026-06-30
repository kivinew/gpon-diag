/* ============================================================
   GPON Diagnostics Dashboard — JavaScript
   ============================================================ */

(function() {
    'use strict';

    // ============================================================
    // State
    // ============================================================
    const state = {
        currentOlt: null,
        selectedOnt: null,
        searchResults: [],
        historyData: [],
        opticsInterval: null,
        currentDiagnosis: null,
        eventSource: null,
        autoRefreshOptics: true,
        opticsRefreshMs: 10000,
        portMonitorInterval: null,
        portMonitorReader: null,
        portSummaries: [],
        lastPortMonitored: null
    };

    // ============================================================
    // DOM Elements
    // ============================================================
    const els = {
        // Header
        oltSelect: document.getElementById('oltSelect'),
        refreshBtn: document.getElementById('refreshBtn'),
        currentOlt: document.getElementById('currentOlt'),

        // Search
        searchForm: document.getElementById('searchForm'),
        searchInput: document.getElementById('searchInput'),
        searchBtn: document.getElementById('searchBtn'),
        searchResults: document.getElementById('searchResults'),
        searchCount: document.getElementById('searchCount'),

        // Optics
        autoRefreshOptics: document.getElementById('autoRefreshOptics'),
        opticsInterval: document.getElementById('opticsInterval'),
        opticsContent: document.getElementById('opticsContent'),

        // Diagnostics
        diagContent: document.getElementById('diagContent'),
        runDiagBtn: document.getElementById('runDiagBtn'),
        historyDuringDiagnosis: document.getElementById('historyDuringDiagnosis'),

        // History
        historyFilter: document.getElementById('historyFilter'),
        historyLimit: document.getElementById('historyLimit'),
        historyBody: document.getElementById('historyBody'),

        // Detail panel
        detailPanel: document.getElementById('detailPanel'),
        detailTitle: document.getElementById('detailTitle'),
        closeDetail: document.getElementById('closeDetail'),
        detailTabs: document.querySelectorAll('.tab-btn'),
        detailContent: document.getElementById('detailContent'),

        // Overlay
        overlay: document.getElementById('overlay'),
        loadingStatus: document.getElementById('loadingStatus')
    };

    // ============================================================
    // Utility Functions
    // ============================================================
    const escapeHtml = (text) => {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    const formatValue = (val, unit = '', thresholds = null) => {
        if (val === null || val === undefined || val === 999.0 || val === 999 || val === -999 || val === -1 || val === '') {
            return '<span class="text-muted">—</span>';
        }
        let cls = '';
        if (thresholds) {
            if (val <= thresholds.crit) cls = 'crit';
            else if (val <= thresholds.warn) cls = 'warn';
            else cls = 'ok';
        }
        return `<span class="${cls}">${val}</span><span class="unit">${unit}</span>`;
    };

    const showOverlay = (msg = 'Выполняется диагностика…') => {
        els.loadingStatus.textContent = msg;
        els.overlay.style.display = 'flex';
    };

    const hideOverlay = () => {
        els.overlay.style.display = 'none';
    };

    const showDetail = () => {
        els.detailPanel.classList.add('open');
    };

    const hideDetail = () => {
        els.detailPanel.classList.remove('open');
    };

    // ============================================================
    // OLT Selection
    // ============================================================
    els.oltSelect.addEventListener('change', async () => {
        const host = els.oltSelect.value;
        state.currentOlt = host || null;
        els.currentOlt.textContent = host ? `OLT: ${host}` : '—';
        // Reset OLT connections when switching OLT to avoid blocked connections
        try {
            await fetch('/api/reset-connections', { method: 'POST' });
        } catch (e) {}
        await loadHistory();
        // Clear optics and port monitor panels
        els.opticsContent.innerHTML = '<div class="optics-empty">Выберите ONT для мониторинга</div>';
        const portPanel = document.getElementById('portMonitorPanel');
        if (portPanel) portPanel.style.display = 'none';
    });

    els.refreshBtn.addEventListener('click', async () => {
        els.refreshBtn.style.transform = 'rotate(360deg)';
        await loadHistory();
        if (state.selectedOnt) {
            await fetchOptics(state.selectedOnt);
        }
        setTimeout(() => els.refreshBtn.style.transform = '', 500);
    });

    // ============================================================
    // Search
    // ============================================================
    els.searchForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = els.searchInput.value.trim();
        if (!query) return;

        showOverlay('Поиск ONT…');
        try {
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, olt_host: state.currentOlt })
            });

            let data;
            try {
                data = await response.json();
            } catch (parseErr) {
                hideOverlay();
                console.error('JSON parse error:', parseErr);
                alert('Ошибка сервера: получен не JSON ответ. Проверьте доступность OLT.');
                return;
            }
            hideOverlay();

            if (data.error) {
                alert(data.error);
                return;
            }

            state.searchResults = data.results || [];
            renderSearchResults();
            els.searchCount.textContent = state.searchResults.length;

        } catch (err) {
            hideOverlay();
            console.error('Search error:', err);
            alert('Ошибка поиска: ' + err.message);
        }
    });

    function renderSearchResults() {
        if (state.searchResults.length === 0) {
            els.searchResults.innerHTML = '<div class="search-empty">Ничего не найдено</div>';
            return;
        }

        els.searchResults.innerHTML = state.searchResults.map((item, idx) => `
            <div class="search-result-item${idx === 0 ? ' selected' : ''}" data-index="${idx}">
                <div class="search-result-header">
                    <span class="search-result-ont">${escapeHtml(item.ont_address)}</span>
                    <span class="search-result-status ${item.is_online ? 'online' : 'offline'}">
                        ${item.is_online ? 'ONLINE' : 'OFFLINE'}
                    </span>
                </div>
                <div class="search-result-meta">
                    <span>OLT: ${escapeHtml(item.olt_name)}</span>
                    <span>SN: ${escapeHtml(item.serial)}</span>
                    <span>${escapeHtml(item.description)}</span>
                </div>
            </div>
        `).join('');

        // Add click handlers
        els.searchResults.querySelectorAll('.search-result-item').forEach((el, idx) => {
            el.addEventListener('click', () => selectSearchResult(idx));
        });

        // Auto-select first
        if (state.searchResults.length > 0) {
            selectSearchResult(0);
        }
    }

    function selectSearchResult(index) {
        const item = state.searchResults[index];
        if (!item) return;

        // Update UI
        els.searchResults.querySelectorAll('.search-result-item').forEach(el => el.classList.remove('selected'));
        els.searchResults.querySelector(`[data-index="${index}"]`)?.classList.add('selected');

        state.selectedOnt = {
            address: item.ont_address,
            olt_host: item.olt_host,
            olt_name: item.olt_name,
            serial: item.serial,
            description: item.description,
            is_online: item.is_online
        };

        // Enable diagnosis button
        els.runDiagBtn.disabled = false;

        // Update detail panel title
        els.detailTitle.textContent = `${item.olt_name} — ONT ${item.ont_address}`;
        showDetail();

        // Fetch optics and history
        fetchOptics(state.selectedOnt);
        loadHistoryForOnt(item.ont_address);

        // Auto-start diagnosis on first search result (if enabled)
        if (state.searchResults.length === 1 || localStorage.getItem('autoDiagnose') === 'true') {
            runDiagnosis(state.selectedOnt);
        }
    }

    // ============================================================
    // Optics Real-time
    // ============================================================
    async function fetchOptics(ont) {
        if (!ont) return;

        try {
            const params = new URLSearchParams({
                address: ont.address,
                olt_host: ont.olt_host
            });
            const response = await fetch(`/api/optics?${params}`);
            const data = await response.json();

            if (data.error) {
                els.opticsContent.innerHTML = `<div class="optics-empty">${escapeHtml(data.error)}</div>`;
                return;
            }

            renderOptics(data);
        } catch (err) {
            console.error('Optics fetch error:', err);
            els.opticsContent.innerHTML = '<div class="optics-empty">Ошибка загрузки оптики</div>';
        }
    }

    function renderOptics(data) {
        const thresholds = {
            ont_rx: { warn: -26.5, crit: -30.0 },
            olt_rx: { warn: -33.0, crit: -35.0 },
            ont_tx: { warn: -3.0, crit: -6.0 },
            bias: { warn: 80, crit: 95 },
            temp: { warn: 65, crit: 75 },
            voltage: { warn: 3.0, crit: 2.8 },
            distance: { warn: 18000, crit: 20000 },
            bip: { warn: 10000, crit: 100000 }
        };

        const cards = [
            { label: 'ONT Rx', value: data.ont_rx_power, unit: 'dBm', thresholds: thresholds.ont_rx, invert: true },
            { label: 'OLT Rx', value: data.olt_rx_power, unit: 'dBm', thresholds: thresholds.olt_rx, invert: true },
            { label: 'ONT Tx', value: data.ont_tx_power, unit: 'dBm', thresholds: thresholds.ont_tx, invert: true },
            { label: 'Laser Bias', value: data.laser_bias_current, unit: 'mA', thresholds: thresholds.bias },
            { label: 'Temperature', value: data.ont_temperature, unit: '°C', thresholds: thresholds.temp },
            { label: 'Voltage', value: data.supply_voltage, unit: 'V', thresholds: thresholds.voltage, invert: true },
            { label: 'Distance', value: data.distance_m, unit: 'm', thresholds: thresholds.distance },
            { label: 'BIP Errors', value: data.total_bip_errors, unit: '', thresholds: thresholds.bip }
        ];

        els.opticsContent.innerHTML = `
            <div class="optics-grid">
                ${cards.map(card => {
                    const val = card.value;
                    let cls = '';
                    let displayVal = val;
                    let isNa = false;

                    if (val === null || val === undefined || val === 999.0 || val === 999 || val === -999 || val === -1) {
                        isNa = true;
                        displayVal = '—';
                    } else if (card.thresholds) {
                        if (card.invert) {
                            if (val <= card.thresholds.crit) cls = 'critical';
                            else if (val <= card.thresholds.warn) cls = 'warning';
                        } else {
                            if (val >= card.thresholds.crit) cls = 'critical';
                            else if (val >= card.thresholds.warn) cls = 'warning';
                        }
                    }

                    const valCls = cls === 'critical' ? 'crit' : cls === 'warning' ? 'warn' : 'ok';

                    return `
                        <div class="optics-card ${cls}">
                            <div class="optics-card-header">
                                <span class="optics-card-label">${card.label}</span>
                                ${!isNa ? `<span class="optics-threshold ${valCls}">${valCls === 'crit' ? 'CRIT' : valCls === 'warn' ? 'WARN' : 'OK'}</span>` : ''}
                            </div>
                            <div class="optics-card-value ${valCls}">
                                ${isNa ? '—' : displayVal}
                                ${card.unit && !isNa ? `<span class="optics-card-unit">${card.unit}</span>` : ''}
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    }

    function startOpticsAutoRefresh() {
        if (state.opticsInterval) clearInterval(state.opticsInterval);
        state.opticsInterval = setInterval(() => {
            if (state.autoRefreshOptics && state.selectedOnt && state.selectedOnt.address) {
                fetchOptics(state.selectedOnt);
            }
        }, state.opticsRefreshMs);
    }

    els.autoRefreshOptics.addEventListener('change', () => {
        state.autoRefreshOptics = els.autoRefreshOptics.checked;
        if (state.autoRefreshOptics) startOpticsAutoRefresh();
        else if (state.opticsInterval) clearInterval(state.opticsInterval);
    });

    els.opticsInterval.addEventListener('change', () => {
        state.opticsRefreshMs = parseInt(els.opticsInterval.value);
        if (state.autoRefreshOptics) startOpticsAutoRefresh();
    });

    // ============================================================
    // Port Monitoring (runs parallel to diagnosis)
    // ============================================================
    function startPortMonitor(ont) {
        if (!ont || !ont.address) return;
        cancelPortMonitor();

        // Show placeholder panel immediately
        const portPanel = document.getElementById('portMonitorPanel');
        if (portPanel) {
            portPanel.style.display = 'flex';
            document.getElementById('portMonitorAddr').textContent = `${ont.address.split('/')[0]}/${ont.address.split('/')[1]}/${ont.address.split('/')[2]}`;
            document.getElementById('portTableBody').innerHTML = '<tr><td colspan="8" class="text-muted" style="text-align:center;">Загрузка...</td></tr>';
        }

        fetch('/api/port-monitor', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ address: ont.address, olt_host: ont.olt_host })
        }).then(response => {
            if (!response.ok) {
                console.error('Port monitor failed:', response.statusText);
                return;
            }
            state.portMonitorReader = response.body.getReader();
            state.lastPortMonitored = {
                frame: ont.address.split('/')[0],
                slot: ont.address.split('/')[1],
                port: ont.address.split('/')[2]
            };
            processPortMonitorStream();
        }).catch(err => {
            console.error('Port monitor error:', err);
        });
    }

    function cancelPortMonitor() {
        if (state.portMonitorReader) {
            try { state.portMonitorReader.cancel(); } catch (e) {}
            state.portMonitorReader = null;
        }
    }

    async function processPortMonitorStream() {
        if (!state.portMonitorReader) return;
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            try {
                const { done, value } = await state.portMonitorReader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const msg = JSON.parse(line.slice(6));
                        if (msg.type === 'result' && msg.summaries) {
                            state.portSummaries = msg.summaries;
                            renderPortMonitor(msg.summaries, msg.port);
                        } else if (msg.type === 'error') {
                            console.warn('Port monitor stream error:', msg.message);
                        }
                    } catch (e) {
                        console.error('Port monitor parse error:', e);
                    }
                }
            } catch (e) {
                if (e.name !== 'AbortError') console.error('Port monitor stream error:', e);
                break;
            }
        }
    }

    function renderPortMonitor(summaries, port) {
        let portPanel = document.getElementById('portMonitorPanel');
        if (!portPanel) {
            portPanel = document.createElement('section');
            portPanel.id = 'portMonitorPanel';
            portPanel.className = 'panel panel-port-monitor';
            portPanel.innerHTML = `
                <div class="panel-header">
                    <h2>ONT на порту ${port || '—'}</h2>
                    <span class="panel-badge" id="portOntCount">${summaries.length} ONT</span>
                </div>
                <div class="port-table-container">
                    <table class="port-table">
                        <thead>
                            <tr>
                                <th>ONT ID</th>
                                <th>Статус</th>
                                <th>Rx (dBm)</th>
                                <th>Tx (dBm)</th>
                                <th>Дист (м)</th>
                                <th>Причина</th>
                                <th>Дескрипшн</th>
                                <th>Время</th>
                            </tr>
                        </thead>
                        <tbody id="portTableBody"></tbody>
                    </table>
                </div>
            `;
            const opticsPanel = document.getElementById('opticsPanel');
            if (opticsPanel && opticsPanel.parentNode) {
                opticsPanel.parentNode.insertBefore(portPanel, opticsPanel.nextSibling);
            }
        }

        const countEl = document.getElementById('portOntCount');
        if (countEl) countEl.textContent = `${summaries.length} ONT`;

        const tbody = document.getElementById('portTableBody');
        if (tbody) {
            tbody.innerHTML = summaries.map(s => {
                const statusCls = s.is_online ? 'online' : 'offline';
                const statusText = s.is_online ? 'ONLINE' : (s.status || '—').toUpperCase();
                const rxCls = s.rx_power_status === 'ok' ? 'ok' : (s.rx_power_status === 'warn' ? 'warn' : 'crit');
                const rxDisplay = (s.rx_power < 900) ? s.rx_power.toFixed(2) : '—';
                const txDisplay = (s.tx_power < 900) ? s.tx_power.toFixed(2) : '—';

                return `
                    <tr>
                        <td><strong>${escapeHtml(s.ont_id)}</strong></td>
                        <td><span class="status-badge ${statusCls}">${escapeHtml(statusText)}</span></td>
                        <td class="${rxCls}">${rxDisplay}</td>
                        <td>${txDisplay}</td>
                        <td>${s.distance > 0 ? s.distance : '—'}</td>
                        <td>${escapeHtml(s.last_down_cause) || '—'}</td>
                        <td>${escapeHtml(s.description) || '—'}</td>
                        <td class="text-muted">${escapeHtml(s.collected_at || '—')}</td>
                    </tr>
                `;
            }).join('');
        }
    }

    // ============================================================
    // Diagnostics with SSE
    // ============================================================
    els.runDiagBtn.addEventListener('click', () => {
        if (!state.selectedOnt) return;
        // Start port monitoring in parallel
        startPortMonitor(state.selectedOnt);
        runDiagnosis(state.selectedOnt);
    });

    async function runDiagnosis(ont) {
        showOverlay('Подключение к OLT…');
        els.runDiagBtn.disabled = true;

        const steps = [
            { id: 'connect', label: 'Подключение к головной станции…' },
            { id: 'find', label: 'Поиск ONT…' },
            { id: 'collect', label: 'Сбор данных ONT…' },
            { id: 'analyze', label: 'Анализ и диагностика…' },
            { id: 'complete', label: 'Завершено' }
        ];

        els.diagContent.innerHTML = `
            <div class="diag-running">
                <div class="diag-progress" id="diagProgress">
                    ${steps.map(s => `<div class="diag-step" id="step-${s.id}"><span class="diag-step-icon">⏳</span>${s.label}</div>`).join('')}
                </div>
            </div>
        `;

        let currentStep = 0;
        let eventSource = null;

        try {
            const response = await fetch('/api/diagnose', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: ont.address,
                    olt_host: ont.olt_host
                })
            });

            if (!response.ok) throw new Error('Ошибка запуска диагностики');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            function updateStep(stepId, status) {
                const el = document.getElementById(`step-${stepId}`);
                if (el) {
                    el.className = `diag-step ${status}`;
                    el.querySelector('.diag-step-icon').textContent = status === 'active' ? '⟳' : status === 'done' ? '✓' : '✗';
                }
            }

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const msg = JSON.parse(line.slice(6));

                        switch (msg.type) {
                            case 'log':
                                // Update current step label
                                if (steps[currentStep]) {
                                    const stepEl = document.getElementById(`step-${steps[currentStep].id}`);
                                    if (stepEl) {
                                        const iconEl = stepEl.querySelector('.diag-step-icon');
                                        if (iconEl) iconEl.textContent = '⟳';
                                    }
                                }
                                break;

                            case 'olt_info':
                                updateStep('connect', 'done');
                                if (currentStep < 1) currentStep = 1;
                                updateStep('find', 'active');
                                els.loadingStatus.textContent = `Подключение к ${msg.model || 'OLT'}…`;
                                break;

                            case 'history':
                                // Save history to display after result
                                window.savedHistory = msg.history;
                                break;

                            case 'result':
                                updateStep('find', 'done');
                                updateStep('collect', 'done');
                                updateStep('analyze', 'done');
                                updateStep('complete', 'done');
                                hideOverlay();
                                els.runDiagBtn.disabled = false;
                                renderDiagResult(msg.report);
                                // Show history-during-diagnosis if we have history
                                if (window.savedHistory && window.savedHistory.length > 0) {
                                    renderHistoryDuringDiagnosis(window.savedHistory);
                                }
                                // Save for detail panel
                                state.currentDiagnosis = {
                                    ...ont,
                                    report: msg.report
                                };
                                break;

                            case 'error':
                                updateStep(steps[currentStep]?.id, 'error');
                                hideOverlay();
                                els.runDiagBtn.disabled = false;
                                renderDiagError(msg.message);
                                return;
                        }
                    } catch (err) {
                        console.error('Parse error:', err);
                    }
                }
            }
        } catch (err) {
            hideOverlay();
            els.runDiagBtn.disabled = false;
            renderDiagError(err.message);
        }
    }

function renderDiagResult(reportText) {
        els.historyDuringDiagnosis.style.display = 'none';
        els.diagContent.innerHTML = `
            <div class="diag-report-header">
                <h3>Результат диагностики</h3>
                <div class="diag-report-actions">
                    <button class="btn-copy" onclick="copyReport()">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>
                        Копировать
                    </button>
                </div>
            </div>
            <div class="diag-report" id="diagReport">${escapeHtml(reportText)}</div>
        `;
    }

    function renderDiagError(message) {
        els.diagContent.innerHTML = `
            <div class="diag-empty">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="15" y1="9" x2="9" y2="15"></line>
                    <line x1="9" y1="9" x2="15" y2="15"></line>
                </svg>
                <p>Ошибка диагностики</p>
                <div class="flash-msg error" style="max-width: 400px; text-align: left;">${escapeHtml(message)}</div>
                <button class="btn-primary" onclick="location.reload()">Повторить</button>
            </div>
        `;
    }

    // Global for inline onclick
    window.copyReport = () => {
        const reportEl = document.getElementById('diagReport') || document.getElementById('report');
        if (reportEl) {
            navigator.clipboard.writeText(reportEl.innerText).then(() => {
                const btn = document.querySelector('.btn-copy');
                if (btn) {
                    btn.classList.add('copied');
                    const old = btn.innerHTML;
                    btn.innerHTML = '✓ Скопировано!';
                    setTimeout(() => { btn.classList.remove('copied'); btn.innerHTML = old; }, 2000);
                }
            });
        }
    };

    // ============================================================
    // History
    // ============================================================
    async function loadHistory() {
        try {
            const params = new URLSearchParams({
                limit: els.historyLimit.value
            });
            if (state.currentOlt) params.append('olt_host', state.currentOlt);

            const response = await fetch(`/api/history?${params}`);
            const data = await response.json();
            state.historyData = data.history || [];
            renderHistory();
        } catch (err) {
            console.error('History load error:', err);
        }
    }

    async function loadHistoryForOnt(ontAddress) {
        try {
            const response = await fetch(`/api/history?q=${encodeURIComponent(ontAddress)}&limit=10`);
            const data = await response.json();
            // Could show in detail panel
        } catch (err) {
            console.error('History load error:', err);
        }
    }

    function renderHistory() {
        const filter = els.historyFilter.value.toLowerCase();
        const filtered = state.historyData.filter(row => {
            if (!filter) return true;
            const searchText = `${row.olt_name} ${row.ont_address} ${row.input_value} ${row.olt_host}`.toLowerCase();
            return searchText.includes(filter);
        });

        els.historyBody.innerHTML = filtered.map(row => {
            let statusBadge = '';
            let problemsCount = '<span class="problems-count ok">0</span>';

            try {
                // API returns 'report' (already parsed), but server-rendered data may have 'report_json'
                const report = row.report || {};
                if (report.is_online === false) {
                    statusBadge = '<span class="status-badge online">ONLINE</span>';
                } else {
                    statusBadge = '<span class="status-badge offline">OFFLINE</span>';
                }
                if (report.problems && report.problems.length > 0) {
                    problemsCount = `<span class="problems-count">${report.problems.length}</span>`;
                }
            } catch (e) {}

            return `
                <tr class="history-row" data-id="${row.id}" data-input="${escapeHtml(row.input_value)}" data-olt-host="${escapeHtml(row.olt_host)}">
                    <td>${escapeHtml(row.created_at)}</td>
                    <td>${escapeHtml(row.olt_name)} (${escapeHtml(row.olt_host)})</td>
                    <td>${escapeHtml(row.ont_address)}</td>
                    <td>${escapeHtml(row.input_value)}</td>
                    <td>${statusBadge}</td>
                    <td>${problemsCount}</td>
                </tr>
            `;
        }).join('');

        attachHistoryRowHandlers();
    }

function attachHistoryRowHandlers() {
        els.historyBody.querySelectorAll('.history-row').forEach(row => {
            row.addEventListener('click', async () => {
                const diagId = row.dataset.id;
                const inputValue = row.dataset.input;
                const oltHost = row.dataset.oltHost;
                const ontAddress = row.dataset.ontAddress;

                // Populate search fields
                els.searchInput.value = inputValue;
                if (oltHost) {
                    els.oltSelect.value = oltHost;
                    state.currentOlt = oltHost;
                }

                // Load and display report from DB history
                try {
                    const detailResp = await fetch(`/api/history/${diagId}`);
                    const detailData = await detailResp.json();

                    // Check if diagnosis was performed less than 1 hour ago
                    let isRecent = false;
                    if (detailData.created_at) {
                        const parts = detailData.created_at.split(' ');
                        if (parts.length >= 2) {
                            const dateStr = parts[0]; // DD.MM.YYYY
                            const timeStr = parts[1]; // HH:MM
                            const dateParts = dateStr.split('.');
                            const timeParts = timeStr.split(':');
                            if (dateParts.length === 3 && timeParts.length === 2) {
                                const diagDate = new Date(dateParts[2], dateParts[1] - 1, dateParts[0], timeParts[0], timeParts[1]);
                                const now = new Date();
                                const diffMs = now - diagDate;
                                const diffHours = diffMs / (1000 * 60 * 60);
                                isRecent = diffHours < 1;
                            }
                        }
                    }

                    if (isRecent && detailData.report) {
                        const reportText = formatReportForDisplay(detailData.report);
                        renderDiagResult(reportText);
                        state.currentDiagnosis = {
                            address: detailData.ont_address,
                            olt_host: detailData.olt_host,
                            report: detailData.report
                        };
                    }

                    // Load related history for the same ONT (multiple search strategies)
                    const searchTerms = [
                        ontAddress, 
                        detailData.ont_address, 
                        detailData.input_value,
                        detailData.report?.serial
                    ].filter(Boolean);

                    // Show "Предыдущие результаты" with at least current item
                    let historyItems = [{id: diagId, ...detailData}];
                    
                    if (searchTerms.length > 0) {
                        // Try each search term until we find additional matches
                        for (const term of searchTerms) {
                            const historyResp = await fetch(`/api/history?q=${encodeURIComponent(term)}&limit=10`);
                            const historyData = await historyResp.json();
                            if (historyData.history && historyData.history.length > 0) {
                                // Merge found items (avoid duplicates by id)
                                const existingIds = new Set(historyItems.map(h => h.id));
                                historyItems = [
                                    ...historyItems,
                                    ...historyData.history.filter(h => !existingIds.has(h.id))
                                ];
                            }
                        }
                    }
                    
                    if (historyItems.length > 0) {
                        renderHistoryDuringDiagnosis(historyItems);
                    } else {
                        els.historyDuringDiagnosis.style.display = 'none';
                    }
                } catch (e) {
                    console.error('Failed to load history detail:', e);
                    els.historyDuringDiagnosis.style.display = 'none';
                }
                // Refresh history list after selection
                await loadHistory();
            });
        });
    }

    function renderHistoryDuringDiagnosis(historyItems) {
        els.historyDuringDiagnosis.style.display = 'block';
        const summaryParts = [];
        historyItems.forEach(item => {
            const r = item.report || {};
            const statusBadge = r.is_online !== false
                ? '<span class="history-status online">ОНЛАЙН</span>'
                : '<span class="history-status offline">ОФФЛАЙН</span>';
            const problemsCount = (r.problems || []).length;
            summaryParts.push(`
                <div class="history-during-item">
                    <span class="history-date">${escapeHtml(item.created_at)}</span>
                    ${statusBadge}
                    ${problemsCount > 0 ? `<span class="history-problems">${problemsCount} проблем</span>` : ''}
                    <span class="history-olt">${escapeHtml(item.olt_name)}</span>
                </div>
            `);
        });
        els.historyDuringDiagnosis.innerHTML = `
            <div class="result-header"><h1>Предыдущие результаты (${historyItems.length})</h1></div>
            <div class="history-during-items">${summaryParts.join('')}</div>
        `;
    }

    els.historyFilter.addEventListener('input', renderHistory);
    els.historyLimit.addEventListener('change', loadHistory);

    async function loadHistoricalReport(diagId) {
        try {
            const response = await fetch(`/api/history/${diagId}`);
            const data = await response.json();
            if (data.error) {
                alert(data.error);
                return;
            }

            const report = data.report || {};
            const reportText = formatReportForDisplay(report);

            // Show in detail panel
            els.detailTitle.textContent = `${data.olt_name} — История`;
            showDetail();
            showTab('summary');
            els.detailContent.innerHTML = `
                <div class="diag-report-header">
                    <h3>${escapeHtml(data.created_at)} · ${escapeHtml(data.olt_name)}</h3>
                </div>
                <div class="diag-report" id="report">${escapeHtml(reportText)}</div>
            `;
        } catch (err) {
            console.error('Historical report error:', err);
            alert('Ошибка загрузки отчёта: ' + err.message);
        }
    }

    // ============================================================
    // Detail Panel Tabs
    // ============================================================
    function showTab(tabName) {
        els.detailTabs.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });

        const panels = document.querySelectorAll('.detail-panel');
        panels.forEach(p => p.classList.toggle('active', p.dataset.tab === tabName));

        if (tabName === 'optics' && state.selectedOnt) {
            fetchOptics(state.selectedOnt);
        }
    }

    els.detailTabs.forEach(btn => {
        btn.addEventListener('click', () => showTab(btn.dataset.tab));
    });

    els.closeDetail.addEventListener('click', hideDetail);

    // ============================================================
    // Report Formatting (from index.html)
    // ============================================================
    function formatReportForDisplay(report) {
        const lines = [];
        // Support both ont and ont_address field names
        const ont = report.ont || report.ont_address || '—';
        const headStation = report.head_station || '—';
        if (headStation && headStation !== '—') lines.push('Головная станция: ' + headStation + ' | ONT = ' + ont);
        if (report.serial) lines.push('PON SN = ' + report.serial);
        if (report.description && report.description !== 'ONT_NO_DESCRIPTION') {
            lines.push('Дескрипшн (лицевой счёт) = ' + report.description);
        } else if (report.description === 'ONT_NO_DESCRIPTION') {
            lines.push('Дескрипшн (лицевой счёт) не установлен');
        }

        if (!report.is_online) {
            lines.push('Терминал недоступен.');
            if (report.last_down_time && report.last_down_time !== '-') lines.push('Отключён: ' + report.last_down_time);
            if (report.last_up_time && report.last_up_time !== '-') lines.push('Время последнего включения: ' + report.last_up_time);
            if (report.distance_m >= 0) lines.push('Расстояние от OLT (м): ' + report.distance_m);
            if (report.last_down_cause && report.last_down_cause !== '-') {
                var cause = report.last_down_cause;
                if (cause === 'нет данных') {
                    lines.push('Причина недоступности не зафиксирована.');
                } else if (cause.indexOf('LOS') >= 0 || cause.indexOf('LOSI') >= 0 || cause.indexOf('LOBI') >= 0) {
                    lines.push('Причина: ' + cause + ' — отсутствует оптический сигнал.');
                } else if (cause.indexOf('LOFi') >= 0) {
                    lines.push('Причина: ' + cause + ' — низкий оптический сигнал.');
                } else if (cause.indexOf('dying-gasp') >= 0) {
                    lines.push('Причина: ' + cause + ' — отключение питания.');
                } else if (cause.indexOf('wire-down') >= 0) {
                    lines.push('Причина: ' + cause + ' — магистральный кабель (массовая проблема).');
                } else {
                    lines.push('Причина: ' + cause);
                }
            }
            if (report.last_down_cause === '-' && report.register_down_count === 0) {
                lines.push('Нет записей о падениях в реестре.');
            }
        } else {
            lines.push('Терминал доступен.');
            if (report.last_up_time) lines.push('Включён: ' + report.last_up_time);
            if (report.model) lines.push('Модель терминала: ' + report.model);
            if (report.version) {
                var bad = ['V1R003C00S108','V1R006C00S130','V1R006C00S205','V1R006C00S201','V1R006C01S201'].indexOf(report.version) >= 0 ? ' !!!' : '';
                lines.push('Версия ПО: ' + report.version + bad);
            }
            if (report.distance_m >= 0) lines.push('Расстояние от OLT (м): ' + report.distance_m);
            if (report.online_duration && report.online_duration !== '-') lines.push('Аптайм: ' + report.online_duration);
            if (report.power_reduction && report.power_reduction !== '-') lines.push('Power reduction: ' + report.power_reduction);
            lines.push('');

            if (report.ont_rx_power < 900) lines.push('ONT Rx (dBm): ' + report.ont_rx_power);
            if (report.olt_rx_power < 900) lines.push('OLT Rx (dBm): ' + report.olt_rx_power);
            if (report.ont_tx_power && report.ont_tx_power < 900) lines.push('ONT Tx (dBm): ' + report.ont_tx_power);
            if (report.laser_bias_current && report.laser_bias_current >= 0) lines.push('Laser Bias (mA): ' + report.laser_bias_current);
            if (report.ont_temperature && report.ont_temperature > -900) lines.push('Температура (°C): ' + report.ont_temperature);
            if (report.supply_voltage && report.supply_voltage >= 0) lines.push('Напряжение (V): ' + report.supply_voltage);
            if (report.module_subtype) lines.push('Тип модуля: ' + report.module_subtype);
            if (report.upstream_errors > 0 || report.downstream_errors > 0) {
                lines.push('Ошибки оптики: Up=' + report.upstream_errors + ', Down=' + report.downstream_errors);
            } else {
                lines.push('Ошибок оптики не обнаружено.');
            }
            lines.push('');

            if (report.lan_ports) {
                report.lan_ports.forEach(function(p) {
                    if (p.link === 'up') {
                        var errStr = '';
                        if (report.eth_errors && report.eth_errors[p.id]) {
                            var errs = report.eth_errors[p.id];
                            var fcs = errs.fcs || 0;
                            var rxBad = errs.received_bad_bytes || 0;
                            var txBad = errs.sent_bad_bytes || 0;
                            if (fcs + rxBad + txBad > 0) errStr = ' [FCS=' + fcs + ', bad=' + (rxBad + txBad) + ']';
                        }
                        lines.push('LAN' + p.id + ': ' + p.type + ', ' + p.speed + ' Mbps, ' + p.duplex + ', Link=up' + errStr);
                    }
                });
            }
            lines.push('');

            if (report.mac_devices && report.mac_devices.length > 0) {
                lines.push('MAC-адреса устройств за ONT:');
                var seen = {};
                report.mac_devices.forEach(function(d) {
                    if (seen[d.mac]) return;
                    seen[d.mac] = true;
                    var portLabel = d.port_type === 'ETH' ? 'LAN' : d.port_type;
                    lines.push(portLabel + d.port_number + ' ' + d.mac);
                });
                lines.push('');
            }

            if (report.ping_status) {
                var pr = report.ping_result;
                var target = report.ping_target || '1.1.1.1';
                if (pr && pr.transmit) {
                    lines.push('Пинг: ' + report.ping_status + ' (' + pr.receive + '/' + pr.transmit + ')');
                    if (pr.lost > 0) lines.push('Потеряно пакетов: ' + pr.lost);
                } else {
                    lines.push('Пинг: ' + report.ping_status);
                }
            }
        }

        if (report.problems && report.problems.length > 0) {
            lines.push('');
            lines.push('Рекомендации:');
            report.problems.forEach(function(p) {
                var icon = p.severity === 'critical' ? '!!!' : (p.severity === 'warning' ? '(!)' : '(i)');
                lines.push(icon + ' ' + p.recommendation);
            });
        } else {
            lines.push('');
            lines.push('Нарушений не выявлено.');
        }

        return lines.join('\n');
    }

    // ============================================================
    // Initialization
    // ============================================================
    async function init() {
        // Check server is running
        try {
            const pingResp = await fetch('/ping', { timeout: 3000 });
            if (!pingResp.ok) throw new Error('Server not responding');
        } catch (e) {
            console.error('Server health check failed:', e);
            // Wait and retry once
            await new Promise(r => setTimeout(r, 2000));
        }

        // Reset UI state - clear any stale selections
        state.selectedOnt = null;
        state.portSummaries = [];
        state.eventSource = null;
        state.portMonitorReader = null;

        // Load initial history
        await loadHistory();

        // Start optics auto-refresh
        startOpticsAutoRefresh();

        // Check for saved selection in URL
        const urlParams = new URLSearchParams(window.location.search);
        const savedQuery = urlParams.get('q');
        const savedOlt = urlParams.get('olt');

        if (savedQuery) {
            els.searchInput.value = savedQuery;
            if (savedOlt) {
                els.oltSelect.value = savedOlt;
                state.currentOlt = savedOlt;
                els.currentOlt.textContent = `OLT: ${savedOlt}`;
            }
            els.searchForm.dispatchEvent(new Event('submit'));
        }
        // Disable diagnosis button until ONT is selected
        els.runDiagBtn.disabled = true;
    }

    // Start when DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();