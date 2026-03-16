/**
 * SQL AI Agent — Frontend Application
 * Multi-DB Intelligence Platform
 */

(() => {
    'use strict';

    // ===== CONFIG =====
    const API_BASE = window.location.origin;
    const TOAST_DURATION = 4000;

    // ===== STATE =====
    const state = {
        dbUrl: '',
        connected: false,
        safeMode: true,
        dialect: '',
        schemas: [],
        queryHistory: [],
        currentPage: 'connect',
        sidebarCollapsed: false,
        currentTable: null,
        pagination: {
            page: 1,
            limit: 20,
            total: 0,
            totalPages: 1
        }
    };

    // ===== DOM REFS =====
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const dom = {
        sidebar: $('#sidebar'),
        sidebarToggle: $('#sidebarToggle'),
        toggleIcon: $('#toggleIcon'),
        mobileMenuBtn: $('#mobileMenuBtn'),
        mobileOverlay: $('#mobileOverlay'),
        headerTitle: $('#headerTitle'),
        statusChip: $('#statusChip'),
        statusText: $('#statusText'),
        dialectBadge: $('#dialectBadge'),
        safeModeToggle: $('#safeModeToggle'),
        themeToggle: $('#themeToggle'),

        // Connect
        dbUrlInput: $('#dbUrlInput'),
        connectBtn: $('#connectBtn'),
        connectingAnim: $('#connectingAnim'),

        // Schema
        schemaEmpty: $('#schemaEmpty'),
        schemaGrid: $('#schemaGrid'),
        schemaSkeleton: $('#schemaSkeleton'),
        schemaTablesList: $('#schemaTablesList'),
        schemaDetailView: $('#schemaDetailView'),

        // AI Query
        aiQueryInput: $('#aiQueryInput'),
        aiSendBtn: $('#aiSendBtn'),
        aiThinking: $('#aiThinking'),
        retryIndicator: $('#retryIndicator'),
        resultsArea: $('#resultsArea'),
        sqlOutput: $('#sqlOutput'),
        copySqlBtn: $('#copySqlBtn'),
        dataTable: $('#dataTable'),
        chartsGrid: $('#chartsGrid'),
        chartsEmpty: $('#chartsEmpty'),
        csvPreview: $('#csvPreview'),
        csvInfo: $('#csvInfo'),
        downloadCsvBtn: $('#downloadCsvBtn'),
        responseMessage: $('#responseMessage'),
        responseMessageText: $('#responseMessageText'),
        historyList: $('#historyList'),

        // Dashboard
        genDashboardBtn: $('#genDashboardBtn'),
        dashboardEmpty: $('#dashboardEmpty'),
        dashboardSkeleton: $('#dashboardSkeleton'),
        dashboardGrid: $('#dashboardGrid'),

        // Optimizer
        optimizerInput: $('#optimizerInput'),
        optimizeBtn: $('#optimizeBtn'),
        optimizerResults: $('#optimizerResults'),
        optimizerSkeleton: $('#optimizerSkeleton'),
        perfScoreValue: $('#perfScoreValue'),
        perfScoreFill: $('#perfScoreFill'),
        origQueryDisplay: $('#origQueryDisplay'),
        optQueryDisplay: $('#optQueryDisplay'),
        copyOptimizedBtn: $('#copyOptimizedBtn'),
        explanationContent: $('#explanationContent'),

        // Modal
        chartModal: $('#chartModal'),
        chartModalTitle: $('#chartModalTitle'),
        chartModalClose: $('#chartModalClose'),
        chartModalImg: $('#chartModalImg'),
        chartNewTabBtn: $('#chartNewTabBtn'),

        // Toast
        toastContainer: $('#toastContainer'),
    };

    // ===== TOAST SYSTEM =====
    function showToast(message, type = 'info') {
        const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
      <span class="toast-icon">${icons[type]}</span>
      <span>${escapeHtml(message)}</span>
    `;
        toast.addEventListener('click', () => removeToast(toast));
        dom.toastContainer.appendChild(toast);
        setTimeout(() => removeToast(toast), TOAST_DURATION);
    }

    function removeToast(toast) {
        if (!toast.parentNode) return;
        toast.classList.add('toast-out');
        setTimeout(() => toast.remove(), 200);
    }

    // ===== UTILITY =====
    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function detectDialect(url) {
        if (url.includes('postgres')) return 'postgres';
        if (url.includes('mysql')) return 'mysql';
        if (url.includes('oracle')) return 'oracle';
        return '';
    }

    function copyToClipboard(text) {
        navigator.clipboard.writeText(text).then(() => {
            showToast('Copied to clipboard!', 'success');
        }).catch(() => {
            showToast('Failed to copy', 'error');
        });
    }

    function formatTime(date) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    async function apiCall(endpoint, body) {
        const res = await fetch(`${API_BASE}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }
        return res.json();
    }

    // ===== NAVIGATION =====
    const pageTitles = {
        connect: 'Connect Database',
        schema: 'Schema Explorer',
        query: 'AI Query',
        dashboard: 'Auto Dashboard',
        optimizer: 'SQL Optimizer',
    };

    function navigateTo(page) {
        state.currentPage = page;

        // Update nav items
        $$('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.page === page);
        });

        // Update pages
        $$('.page').forEach(p => {
            p.classList.toggle('active', p.id === `page-${page}`);
        });

        // Update header title
        dom.headerTitle.textContent = pageTitles[page] || page;

        // Close mobile sidebar
        dom.sidebar.classList.remove('mobile-open');
        dom.mobileOverlay.classList.remove('show');
    }

    // ===== SIDEBAR =====
    function toggleSidebar() {
        state.sidebarCollapsed = !state.sidebarCollapsed;
        dom.sidebar.classList.toggle('collapsed', state.sidebarCollapsed);
        dom.toggleIcon.textContent = state.sidebarCollapsed ? '▶' : '◀';
    }

    // ===== THEME =====
    function toggleTheme() {
        const html = document.documentElement;
        const current = html.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-theme', next);
        dom.themeToggle.textContent = next === 'dark' ? '🌙' : '☀️';
        localStorage.setItem('theme', next);
    }

    function loadTheme() {
        const saved = localStorage.getItem('theme') || 'dark';
        document.documentElement.setAttribute('data-theme', saved);
        dom.themeToggle.textContent = saved === 'dark' ? '🌙' : '☀️';
    }

    // ===== SAFE MODE =====
    function toggleSafeMode() {
        state.safeMode = !state.safeMode;
        dom.safeModeToggle.classList.toggle('active', state.safeMode);
        dom.safeModeToggle.setAttribute('aria-checked', state.safeMode);
        showToast(state.safeMode ? 'Safe Mode ON — SELECT only' : 'Safe Mode OFF — All SQL allowed', state.safeMode ? 'success' : 'warning');
    }

    // ===== CONNECTION STATUS =====
    function updateConnectionStatus(connected, dialect) {
        state.connected = connected;
        state.dialect = dialect;

        dom.statusChip.className = `status-chip ${connected ? 'connected' : 'disconnected'}`;
        dom.statusText.textContent = connected ? 'Connected' : 'Disconnected';

        if (dialect) {
            dom.dialectBadge.textContent = `🗄 ${dialect.toUpperCase()}`;
            dom.dialectBadge.className = `dialect-badge ${dialect}`;
            dom.dialectBadge.classList.remove('hidden');
        } else {
            dom.dialectBadge.classList.add('hidden');
        }
    }

    // ===== CONNECT PAGE =====
    async function handleConnect() {
        const url = dom.dbUrlInput.value.trim();
        if (!url) {
            showToast('Please enter a database connection URL', 'warning');
            dom.dbUrlInput.focus();
            return;
        }

        state.dbUrl = url;
        const dialect = detectDialect(url);

        // Show loading
        dom.connectBtn.disabled = true;
        dom.connectingAnim.classList.add('show');

        try {
            const data = await apiCall('/schemas', { db_url: url });
            state.schemas = data.tables || [];

            updateConnectionStatus(true, dialect);
            showToast(`Connected! Found ${state.schemas.length} tables.`, 'success');

            // Load schema page
            dom.connectingAnim.classList.remove('show');
            dom.connectBtn.disabled = false;
            loadSchemaList();
            navigateTo('schema');
        } catch (err) {
            dom.connectingAnim.classList.remove('show');
            dom.connectBtn.disabled = false;
            updateConnectionStatus(false, '');
            showToast(`Connection failed: ${err.message}`, 'error');
        }
    }

    // ===== SCHEMA EXPLORER =====
    function loadSchemaList() {
        if (!state.schemas.length) {
            dom.schemaEmpty.classList.remove('hidden');
            dom.schemaGrid.classList.add('hidden');
            return;
        }

        dom.schemaEmpty.classList.add('hidden');
        dom.schemaGrid.classList.remove('hidden');

        dom.schemaTablesList.innerHTML = state.schemas.map(table => `
      <div class="schema-table-item" data-table="${escapeHtml(table)}" tabindex="0" role="button" aria-label="View table ${escapeHtml(table)}">
        <span class="table-icon">📋</span>
        <span>${escapeHtml(table)}</span>
      </div>
    `).join('');

        // Reset detail view
        dom.schemaDetailView.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">👈</div>
        <h3>Select a Table</h3>
        <p>Click a table from the list to view its details and preview data.</p>
      </div>
    `;
    }

    async function loadTableDetails(tableName) {
        state.currentTable = tableName;
        state.pagination.page = 1;

        // Mark active
        $$('.schema-table-item').forEach(item => {
            item.classList.toggle('active', item.dataset.table === tableName);
        });

        // Show skeleton
        dom.schemaDetailView.innerHTML = `
          <div class="skeleton skeleton-text" style="width:50%;margin-bottom:16px"></div>
          <div class="skeleton-row"><div class="skeleton"></div><div class="skeleton"></div></div>
          <div class="skeleton skeleton-block"></div>
        `;

        try {
            // Parallel fetch: Metadata + First Page Data
            const [metaData, pageData] = await Promise.all([
                apiCall(`/schemas/${encodeURIComponent(tableName)}`, { db_url: state.dbUrl }),
                apiCall(`/schemas/${encodeURIComponent(tableName)}/data`, {
                    db_url: state.dbUrl,
                    page: 1,
                    limit: state.pagination.limit
                })
            ]);

            state.pagination.total = pageData.total_rows;
            state.pagination.totalPages = pageData.total_pages;

            renderTableDetails(metaData, pageData.data);
        } catch (err) {
            dom.schemaDetailView.innerHTML = `
            <div class="empty-state">
              <div class="empty-icon">❌</div>
              <h3>Error Loading Details</h3>
              <p>${escapeHtml(err.message)}</p>
            </div>
          `;
            showToast(`Failed to load table: ${err.message}`, 'error');
        }
    }

    async function loadTablePage(page) {
        if (!state.currentTable) return;
        state.pagination.page = page;

        // Show loading overlay on table
        const tableContainer = dom.schemaDetailView.querySelector('.data-table-wrapper');
        if (tableContainer) tableContainer.style.opacity = '0.5';

        try {
            const data = await apiCall(`/schemas/${encodeURIComponent(state.currentTable)}/data`, {
                db_url: state.dbUrl,
                page: page,
                limit: state.pagination.limit
            });

            state.pagination.total = data.total_rows;
            state.pagination.totalPages = data.total_pages;

            // Re-render just the data section
            updateTableData(data.data);
        } catch (err) {
            showToast(`Failed to load page ${page}: ${err.message}`, 'error');
            if (tableContainer) tableContainer.style.opacity = '1';
        }
    }

    function renderTableDetails(metaData, rows) {
        const columnsHtml = metaData.columns.map(col => `<span class="meta-chip"><code style="font-family:var(--font-mono);font-size:12px;">${escapeHtml(col)}</code></span>`).join('');

        dom.schemaDetailView.innerHTML = `
          <div class="schema-detail-header">
            <h3>📋 ${escapeHtml(metaData.table_name)}</h3>
          </div>
          <div class="schema-meta">
            <span class="meta-chip">Rows: <span class="meta-value" id="totalRowsCount">${state.pagination.total.toLocaleString()}</span></span>
            <span class="meta-chip">Columns: <span class="meta-value">${metaData.columns.length}</span></span>
          </div>
          <div class="schema-section">
            <h4>Columns</h4>
            <div style="display:flex;flex-wrap:wrap;gap:6px;max-height:100px;overflow-y:auto;padding-bottom:10px;">${columnsHtml}</div>
          </div>
          <div class="schema-section">
            <div class="flex items-center justify-between mb-sm">
                <h4>Table Data</h4>
                <div class="pagination-controls">
                    <button class="btn btn-sm btn-ghost" id="prevPageBtn" disabled>◀ Prev</button>
                    <span class="text-secondary" style="font-size:12px;">Page <span id="curPageDisplay">1</span> of <span id="totalPagesDisplay">${state.pagination.totalPages}</span></span>
                    <button class="btn btn-sm btn-ghost" id="nextPageBtn" ${state.pagination.totalPages <= 1 ? 'disabled' : ''}>Next ▶</button>
                </div>
            </div>
            <div id="tableContainer">
                ${renderTableHTML(rows, metaData.columns)}
            </div>
          </div>
        `;

        // Animate in
        dom.schemaDetailView.style.animation = 'none';
        dom.schemaDetailView.offsetHeight; // trigger reflow
        dom.schemaDetailView.style.animation = 'pageIn var(--duration-slow) var(--ease-default)';

        bindPaginationEvents();
    }

    function renderTableHTML(rows, explicitColumns = null) {
        if (!rows || !rows.length) return `<div class="empty-state" style="padding:20px;"><p class="text-secondary">No data available</p></div>`;

        const cols = explicitColumns || Object.keys(rows[0]);
        return `
            <div class="data-table-wrapper" style="max-height:400px;overflow:auto;">
              <table class="data-table">
                <thead><tr>${cols.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr></thead>
                <tbody>${rows.map(r => `<tr>${cols.map(c => `<td title="${escapeHtml(String(r[c] ?? ''))}">${escapeHtml(String(r[c] ?? 'NULL'))}</td>`).join('')}</tr>`).join('')}</tbody>
              </table>
            </div>
        `;
    }

    function updateTableData(rows) {
        // We need columns from somewhere. Since we are updating, we assume the table structure is known.
        // We can get columns from the first row if available, or we might need to store columns in state.
        // For now, let's try to infer from data or use the existing header if possible.
        // Better: store columns in state.

        // Actually, let's just grab the headers from the DOM to be safe if 'rows' is empty? 
        // No, if rows is empty we can't infer.
        // Let's modify renderTableDetails to store columns in a closure or state if needed.
        // Simpler: Just render with keys of first row. If empty, the specific message is shown.

        let cols = null;
        const existingThs = dom.schemaDetailView.querySelectorAll('.data-table th');
        if (existingThs.length) {
            cols = Array.from(existingThs).map(th => th.textContent);
        }

        const container = document.getElementById('tableContainer');
        if (container) {
            container.innerHTML = renderTableHTML(rows, cols);
            container.style.opacity = '1';
        }

        // Update controls
        document.getElementById('curPageDisplay').textContent = state.pagination.page;
        document.getElementById('totalPagesDisplay').textContent = state.pagination.totalPages;
        document.getElementById('totalRowsCount').textContent = state.pagination.total.toLocaleString();

        document.getElementById('prevPageBtn').disabled = state.pagination.page <= 1;
        document.getElementById('nextPageBtn').disabled = state.pagination.page >= state.pagination.totalPages;
    }

    function bindPaginationEvents() {
        const prevBtn = document.getElementById('prevPageBtn');
        const nextBtn = document.getElementById('nextPageBtn');

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                if (state.pagination.page > 1) loadTablePage(state.pagination.page - 1);
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                if (state.pagination.page < state.pagination.totalPages) loadTablePage(state.pagination.page + 1);
            });
        }
    }

    // ===== AI QUERY =====
    async function handleAIQuery() {
        const query = dom.aiQueryInput.value.trim();
        if (!query) {
            showToast('Please enter a question', 'warning');
            dom.aiQueryInput.focus();
            return;
        }
        if (!state.dbUrl) {
            showToast('Connect to a database first', 'warning');
            return;
        }

        // Show thinking
        dom.aiSendBtn.disabled = true;
        dom.aiThinking.classList.add('show');
        dom.resultsArea.classList.add('hidden');
        dom.responseMessage.classList.add('hidden');
        dom.retryIndicator.classList.add('hidden');

        try {
            const data = await apiCall('/generate', {
                db_url: state.dbUrl,
                query: query,
                safe_mode: state.safeMode,
            });

            dom.aiThinking.classList.remove('show');
            dom.aiSendBtn.disabled = false;

            if (data.error) {
                showToast(`Error: ${data.error}`, 'error');
                if (data.sql_query) {
                    renderQueryResults(data);
                }
                return;
            }

            // Check for self-healing
            if (data.message && data.message.includes('auto-correction')) {
                dom.retryIndicator.classList.remove('hidden');
            }

            renderQueryResults(data);
            addToHistory(query);

            if (data.message) {
                dom.responseMessage.classList.remove('hidden');
                dom.responseMessageText.textContent = data.message;
            }

            showToast('Query executed successfully!', 'success');
        } catch (err) {
            dom.aiThinking.classList.remove('show');
            dom.aiSendBtn.disabled = false;
            showToast(`Query failed: ${err.message}`, 'error');
        }
    }

    function renderQueryResults(data) {
        dom.resultsArea.classList.remove('hidden');

        // SQL Output with typewriter effect
        typewriterEffect(dom.sqlOutput, data.sql_query || 'No SQL generated');

        // Data Table
        if (data.data_preview && data.data_preview.length) {
            const cols = Object.keys(data.data_preview[0]);
            let tableHtml = `
        <thead><tr>${cols.map(c => `<th data-col="${escapeHtml(c)}">${escapeHtml(c)} <span class="sort-icon">↕</span></th>`).join('')}</tr></thead>
        <tbody>${data.data_preview.map(row => `<tr>${cols.map(c => `<td title="${escapeHtml(String(row[c] ?? ''))}">${escapeHtml(String(row[c] ?? 'NULL'))}</td>`).join('')}</tr>`).join('')}</tbody>
      `;
            dom.dataTable.innerHTML = tableHtml;
            dom.dataTable.dataset.rows = JSON.stringify(data.data_preview);
        } else {
            dom.dataTable.innerHTML = '<tbody><tr><td style="text-align:center;padding:24px;color:var(--text-tertiary);">No data to display</td></tr></tbody>';
        }

        // Charts
        if (data.graphs_base64 && data.graphs_base64.length) {
            dom.chartsGrid.innerHTML = data.graphs_base64.map((img, i) => `
        <div class="card chart-card" style="animation-delay:${i * 100}ms;" data-img="${img}" role="button" aria-label="View chart fullscreen">
          <img src="data:image/png;base64,${img}" alt="Chart ${i + 1}">
        </div>
      `).join('');
            dom.chartsEmpty.classList.add('hidden');
            dom.chartsGrid.classList.remove('hidden');
        } else {
            dom.chartsGrid.innerHTML = '';
            dom.chartsGrid.classList.add('hidden');
            dom.chartsEmpty.classList.remove('hidden');
        }

        // CSV
        if (data.csv_base64) {
            const csvText = atob(data.csv_base64);
            const lines = csvText.split('\n');
            dom.csvPreview.textContent = lines.slice(0, 20).join('\n') + (lines.length > 20 ? '\n...' : '');
            dom.csvInfo.textContent = `${lines.length - 1} rows`;
            dom.downloadCsvBtn.onclick = () => downloadCSV(csvText, 'query_results.csv');
        } else {
            dom.csvPreview.textContent = 'No CSV data available';
            dom.csvInfo.textContent = '';
        }

        // Reset to table tab
        switchTab('table-tab');
    }

    function typewriterEffect(element, text) {
        element.textContent = '';
        element.classList.add('typewriter');
        let i = 0;
        const speed = Math.max(5, Math.min(30, 1500 / text.length));
        function type() {
            if (i < text.length) {
                element.textContent += text.charAt(i);
                i++;
                setTimeout(type, speed);
            } else {
                element.classList.remove('typewriter');
            }
        }
        type();
    }

    function downloadCSV(csvText, filename) {
        const blob = new Blob([csvText], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
        showToast('CSV downloaded!', 'success');
    }

    // Table sorting
    function sortTable(colIdx, ascending) {
        const rows = JSON.parse(dom.dataTable.dataset.rows || '[]');
        if (!rows.length) return;
        const keys = Object.keys(rows[0]);
        const key = keys[colIdx];
        rows.sort((a, b) => {
            const va = a[key], vb = b[key];
            if (va == null) return 1;
            if (vb == null) return -1;
            if (typeof va === 'number') return ascending ? va - vb : vb - va;
            return ascending ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
        });
        dom.dataTable.dataset.rows = JSON.stringify(rows);
        const cols = keys;
        const tbody = dom.dataTable.querySelector('tbody');
        tbody.innerHTML = rows.map(row => `<tr>${cols.map(c => `<td title="${escapeHtml(String(row[c] ?? ''))}">${escapeHtml(String(row[c] ?? 'NULL'))}</td>`).join('')}</tr>`).join('');
    }

    // ===== TABS =====
    function switchTab(tabId) {
        $$('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabId);
            btn.setAttribute('aria-selected', btn.dataset.tab === tabId);
        });
        $$('.tab-content').forEach(c => {
            c.classList.toggle('active', c.id === tabId);
        });
    }

    // ===== QUERY HISTORY =====
    function addToHistory(query) {
        state.queryHistory.unshift({ query, time: new Date() });
        if (state.queryHistory.length > 20) state.queryHistory.pop();
        renderHistory();
    }

    function renderHistory() {
        if (!state.queryHistory.length) return;
        dom.historyList.innerHTML = state.queryHistory.map((item, i) => `
      <div class="history-item" data-idx="${i}" tabindex="0" role="button" aria-label="Re-run query: ${escapeHtml(item.query.substring(0, 50))}">
        <span class="history-query">${escapeHtml(item.query)}</span>
        <span class="history-time">${formatTime(item.time)}</span>
      </div>
    `).join('');
    }

    // ===== DASHBOARD =====
    async function handleGenDashboard() {
        if (!state.dbUrl) {
            showToast('Connect to a database first', 'warning');
            return;
        }

        dom.genDashboardBtn.disabled = true;
        dom.dashboardEmpty.classList.add('hidden');
        dom.dashboardGrid.classList.add('hidden');
        dom.dashboardSkeleton.classList.remove('hidden');

        try {
            const data = await apiCall('/gen-dashboard', { db_url: state.dbUrl });

            dom.dashboardSkeleton.classList.add('hidden');
            dom.genDashboardBtn.disabled = false;

            if (data.error) {
                showToast(`Dashboard error: ${data.error}`, 'error');
                dom.dashboardEmpty.classList.remove('hidden');
                return;
            }

            if (!data.charts || !data.charts.length) {
                dom.dashboardEmpty.classList.remove('hidden');
                showToast('No insights could be generated', 'warning');
                return;
            }

            renderDashboard(data.charts);
            showToast(`Dashboard generated with ${data.charts.length} insights!`, 'success');
        } catch (err) {
            dom.dashboardSkeleton.classList.add('hidden');
            dom.genDashboardBtn.disabled = false;
            dom.dashboardEmpty.classList.remove('hidden');
            showToast(`Dashboard failed: ${err.message}`, 'error');
        }
    }

    function renderDashboard(charts) {
        dom.dashboardGrid.classList.remove('hidden');
        dom.dashboardGrid.innerHTML = charts.map((chart, i) => `
      <div class="card dashboard-card animate-in" style="animation-delay:${i * 80}ms;" data-img="${chart.graph_base64}" data-title="${escapeHtml(chart.title)}" role="button" aria-label="View ${escapeHtml(chart.title)} fullscreen">
        <div class="fullscreen-hint">🔍 Click to expand</div>
        <div class="card-content">
          <h4>${escapeHtml(chart.title)}</h4>
          <p>${escapeHtml(chart.description)}</p>
          <img src="data:image/png;base64,${chart.graph_base64}" alt="${escapeHtml(chart.title)}" loading="lazy">
        </div>
      </div>
    `).join('');
    }

    // ===== SQL OPTIMIZER =====
    async function handleOptimize() {
        const sql = dom.optimizerInput.value.trim();
        if (!sql) {
            showToast('Please enter a SQL query to optimize', 'warning');
            dom.optimizerInput.focus();
            return;
        }
        if (!state.dbUrl) {
            showToast('Connect to a database first', 'warning');
            return;
        }

        dom.optimizeBtn.disabled = true;
        dom.optimizerResults.classList.add('hidden');
        dom.optimizerSkeleton.classList.remove('hidden');

        try {
            const data = await apiCall('/optimize', {
                db_url: state.dbUrl,
                query: sql,
            });

            dom.optimizerSkeleton.classList.add('hidden');
            dom.optimizeBtn.disabled = false;

            renderOptimizerResults(data);
            showToast('Query optimized!', 'success');
        } catch (err) {
            dom.optimizerSkeleton.classList.add('hidden');
            dom.optimizeBtn.disabled = false;
            showToast(`Optimization failed: ${err.message}`, 'error');
        }
    }

    function renderOptimizerResults(data) {
        dom.optimizerResults.classList.remove('hidden');

        // Performance score with animation
        const score = Math.min(100, Math.max(0, data.difference_score || 0));
        const scoreClass = score < 30 ? 'low' : score < 70 ? 'medium' : 'high';
        dom.perfScoreValue.textContent = `${score}%`;
        dom.perfScoreFill.className = `perf-score-fill ${scoreClass}`;
        setTimeout(() => {
            dom.perfScoreFill.style.width = `${score}%`;
        }, 100);

        // Original query
        dom.origQueryDisplay.textContent = data.original_query;

        // Optimized query
        dom.optQueryDisplay.textContent = data.optimized_query;

        // Explanation (render markdown-like content)
        dom.explanationContent.innerHTML = renderMarkdown(data.explanation);

        // Scroll into view
        dom.optimizerResults.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function renderMarkdown(text) {
        if (!text) return '<p>No explanation provided.</p>';
        // Simple markdown rendering
        return text
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/`(.+?)`/g, '<code style="background:var(--bg-tertiary);padding:2px 6px;border-radius:4px;font-family:var(--font-mono);font-size:12px;">$1</code>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n- /g, '</p><li>')
            .replace(/\n/g, '<br>')
            .replace(/^/, '<p>')
            .replace(/$/, '</p>');
    }

    // ===== MODAL =====
    function openChartModal(imgBase64, title) {
        dom.chartModalImg.src = `data:image/png;base64,${imgBase64}`;
        dom.chartModalTitle.textContent = title || 'Chart';
        dom.chartModal.classList.add('open');
        dom.chartModal.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
    }

    function closeChartModal() {
        dom.chartModal.classList.remove('open');
        dom.chartModal.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
    }

    // ===== EVENT LISTENERS =====
    function initEvents() {
        // Navigation
        $$('.nav-item').forEach(item => {
            item.addEventListener('click', () => navigateTo(item.dataset.page));
            item.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    navigateTo(item.dataset.page);
                }
            });
        });

        // Sidebar toggle
        dom.sidebarToggle.addEventListener('click', toggleSidebar);

        // Mobile
        dom.mobileMenuBtn.addEventListener('click', () => {
            dom.sidebar.classList.toggle('mobile-open');
            dom.mobileOverlay.classList.toggle('show');
        });
        dom.mobileOverlay.addEventListener('click', () => {
            dom.sidebar.classList.remove('mobile-open');
            dom.mobileOverlay.classList.remove('show');
        });

        // Theme
        dom.themeToggle.addEventListener('click', toggleTheme);

        // Safe mode
        dom.safeModeToggle.addEventListener('click', toggleSafeMode);
        dom.safeModeToggle.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                toggleSafeMode();
            }
        });

        // Connect
        dom.connectBtn.addEventListener('click', handleConnect);
        dom.dbUrlInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') handleConnect();
        });

        // Presets
        $$('.preset-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                dom.dbUrlInput.value = btn.dataset.preset;
                dom.dbUrlInput.focus();
            });
        });

        // Schema table clicks
        dom.schemaTablesList.addEventListener('click', (e) => {
            const item = e.target.closest('.schema-table-item');
            if (item) loadTableDetails(item.dataset.table);
        });

        // AI Query
        dom.aiSendBtn.addEventListener('click', handleAIQuery);
        dom.aiQueryInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleAIQuery();
            }
        });

        // Auto-resize textarea
        dom.aiQueryInput.addEventListener('input', () => {
            dom.aiQueryInput.style.height = 'auto';
            dom.aiQueryInput.style.height = Math.min(200, dom.aiQueryInput.scrollHeight) + 'px';
        });

        // Copy SQL
        dom.copySqlBtn.addEventListener('click', () => {
            copyToClipboard(dom.sqlOutput.textContent);
        });

        // Tabs
        $$('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => switchTab(btn.dataset.tab));
        });

        // Table sorting
        dom.dataTable.addEventListener('click', (e) => {
            const th = e.target.closest('th');
            if (!th) return;
            const idx = Array.from(th.parentNode.children).indexOf(th);
            const asc = th.dataset.sort !== 'asc';
            th.dataset.sort = asc ? 'asc' : 'desc';
            // Reset other headers
            th.parentNode.querySelectorAll('th').forEach(h => {
                if (h !== th) h.dataset.sort = '';
            });
            sortTable(idx, asc);
        });

        // Chart fullscreen clicks
        document.addEventListener('click', (e) => {
            const chartCard = e.target.closest('.chart-card, .dashboard-card');
            if (chartCard && chartCard.dataset.img) {
                openChartModal(chartCard.dataset.img, chartCard.dataset.title || 'Chart');
            }
        });

        // Modal actions
        dom.chartModalClose.addEventListener('click', closeChartModal);
        dom.chartNewTabBtn.addEventListener('click', () => {
            const win = window.open();
            win.document.write(`<iframe src="${dom.chartModalImg.src}" frameborder="0" style="border:0; top:0px; left:0px; bottom:0px; right:0px; width:100%; height:100%;" allowfullscreen></iframe>`);
        });
        dom.chartModal.addEventListener('click', (e) => {
            if (e.target === dom.chartModal) closeChartModal();
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeChartModal();
        });

        // Dashboard
        dom.genDashboardBtn.addEventListener('click', handleGenDashboard);

        // Optimizer
        dom.optimizeBtn.addEventListener('click', handleOptimize);
        dom.copyOptimizedBtn.addEventListener('click', () => {
            copyToClipboard(dom.optQueryDisplay.textContent);
        });

        // History clicks
        dom.historyList.addEventListener('click', (e) => {
            const item = e.target.closest('.history-item');
            if (item) {
                const idx = parseInt(item.dataset.idx);
                if (state.queryHistory[idx]) {
                    dom.aiQueryInput.value = state.queryHistory[idx].query;
                    dom.aiQueryInput.dispatchEvent(new Event('input'));
                }
            }
        });
    }

    // ===== INIT =====
    function init() {
        loadTheme();
        initEvents();
        navigateTo('connect');
    }

    // Go!
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
