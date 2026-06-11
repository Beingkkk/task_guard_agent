/**
 * TaskCard Component — Refactored
 * Relates-to: FR-4
 *
 * State-driven diff update: build DOM once, update references in-place.
 * Events bound once at construction. No innerHTML replace on update.
 */

class TaskCard {
  constructor(task, onClick, onDelete) {
    this.task = task;
    this.onClick = onClick;
    this.onDelete = onDelete;
    this._isLoading = true;
    this.element = null;
    // Cached DOM references for diff-update
    this._els = {};
    this._build();
  }

  /* ── Public API ─────────────────────────────────────────────────────────── */

  update(data) {
    this._isLoading = false;

    // Normalize WebSocket vs REST field names
    const normalized = { ...data };
    if (normalized.metrics && !normalized.latest_metrics) {
      normalized.latest_metrics = normalized.metrics;
    }
    if (normalized.progress && !normalized.latest_progress) {
      normalized.latest_progress = normalized.progress;
    }
    if (normalized.log_lines && !normalized.recent_logs) {
      normalized.recent_logs = normalized.log_lines;
    }
    if (normalized.recent_logs && typeof normalized.recent_logs === 'object' && !Array.isArray(normalized.recent_logs)) {
      normalized.recent_logs = normalized.recent_logs.lines || [];
    }

    this.task = { ...this.task, ...normalized };
    this._syncUI();
  }

  /* ── DOM Building (once) ────────────────────────────────────────────────── */

  _build() {
    const el = document.createElement('div');
    el.className = 'task-card';
    el.innerHTML = `
      <div class="task-card-header">
        <div class="task-card-title"></div>
        <div class="task-card-actions">
          <button class="btn-icon btn-delete" title="注销任务">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </button>
        </div>
      </div>
      <div class="task-card-meta">
        <span class="tc-pid"></span>
        <span class="tc-log"></span>
      </div>
      <div class="metrics-grid">
        <div class="metric-item">
          <div class="metric-label">CPU</div>
          <div class="metric-value" data-key="cpu"></div>
        </div>
        <div class="metric-item">
          <div class="metric-label">内存</div>
          <div class="metric-value" data-key="mem"></div>
        </div>
        <div class="metric-item">
          <div class="metric-label">状态</div>
          <div class="metric-value" data-key="status"></div>
        </div>
        <div class="metric-item">
          <div class="metric-label">内存%</div>
          <div class="metric-value" data-key="memPct"></div>
        </div>
      </div>
      <div class="progress-area"></div>
      <div class="log-area"></div>
    `;

    // Cache refs
    this._els.title = el.querySelector('.task-card-title');
    this._els.pid = el.querySelector('.tc-pid');
    this._els.logPath = el.querySelector('.tc-log');
    this._els.cpu = el.querySelector('[data-key="cpu"]');
    this._els.mem = el.querySelector('[data-key="mem"]');
    this._els.status = el.querySelector('[data-key="status"]');
    this._els.memPct = el.querySelector('[data-key="memPct"]');
    this._els.progress = el.querySelector('.progress-area');
    this._els.logs = el.querySelector('.log-area');

    // Static content that never changes
    const alias = this._alias();
    this._els.title.textContent = alias;
    el.dataset.alias = alias;

    const pid = this.task.pid || this.task.registered?.pid || '-';
    this._els.pid.textContent = `PID: ${pid}`;

    let logPath = '-';
    if (this.task.log_source?.path) {
      logPath = this.task.log_source.path.split('\\').pop() || this.task.log_source.path;
    } else if (this.task.registered?.log_source?.paths) {
      logPath = this.task.registered.log_source.paths[0]?.split('\\').pop() || '-';
    }
    this._els.logPath.textContent = logPath;

    // Events — bound once forever
    el.addEventListener('click', (e) => {
      if (e.target.closest('.btn-delete')) return;
      if (this.onClick) this.onClick(alias);
    });
    el.querySelector('.btn-delete').addEventListener('click', (e) => {
      e.stopPropagation();
      if (this.onDelete) this.onDelete(alias);
    });

    this.element = el;
    this._syncUI();
  }

  /* ── Diff Sync (called on build + every update) ─────────────────────────── */

  _syncUI() {
    const data = this.task;
    const metrics = data.latest_metrics || data.metrics || {};
    const progress = data.latest_progress || data.progress || null;
    const logs = this._getLogsArray(data);

    // Status class (border color)
    const statusClass = this._statusClass(metrics, progress, data);
    this.element.className = `task-card ${statusClass}`;

    // Loading vs real data
    const hasMetrics = metrics.cpu_percent != null || metrics.status != null;
    const showLoading = this._isLoading && !hasMetrics;

    // CPU
    this._setMetric(this._els.cpu, showLoading, metrics.cpu_percent, (v) => `${v.toFixed(1)}%`);

    // Memory
    this._setMetric(this._els.mem, showLoading, metrics.memory_working_set, (v) => this._fmtBytes(v));

    // Status
    this._els.status.className = `metric-value ${metrics.status ? 'status-' + metrics.status : ''}`;
    this._els.status.textContent = showLoading ? '—' : (metrics.status || '—');

    // Memory %
    this._setMetric(this._els.memPct, showLoading, metrics.memory_percent, (v) => `${v.toFixed(1)}%`);

    // Progress
    this._els.progress.innerHTML = this._renderProgress(progress);

    // Logs
    this._els.logs.innerHTML = showLoading ? this._renderLoadingLogs() : this._renderLogs(logs);
  }

  _setMetric(el, showLoading, value, fmt) {
    if (showLoading) {
      el.textContent = '—';
      el.classList.add('placeholder');
      return;
    }
    el.classList.remove('placeholder');
    el.textContent = value != null ? fmt(value) : '—';
  }

  /* ── Helpers ────────────────────────────────────────────────────────────── */

  _alias() {
    return this.task.alias || this.task.registered?.alias || 'Unknown';
  }

  _statusClass(metrics, progress, data) {
    if (metrics?.status === 'exited' || metrics?.status === 'oom') return 'status-critical';
    if ((metrics?.cpu_percent ?? 0) > 90 || (metrics?.memory_percent ?? 0) > 90 || progress?.status === 'error') {
      return 'status-danger';
    }
    if (data?.state?.file?.stalled || (metrics?.cpu_percent ?? 0) > 70 || (metrics?.memory_percent ?? 0) > 70 || progress?.status === 'stalled') {
      return 'status-warning';
    }
    return '';
  }

  _getLogsArray(data) {
    const logs = data.recent_logs || data.log_lines || [];
    if (logs && typeof logs === 'object' && !Array.isArray(logs)) return logs.lines || [];
    return Array.isArray(logs) ? logs : [];
  }

  _renderProgress(progress) {
    if (!progress) return '';
    const hasPct = progress.percentage != null && progress.percentage > 0;
    const hasSpeed = progress.speed && progress.speed !== '0 B/s';
    const hasEta = progress.eta && progress.eta !== '';
    const hasStatus = progress.status && progress.status !== 'unknown' && progress.status !== 'normal';
    const summary = progress.raw_summary || '';
    if (!hasPct && !hasSpeed && !hasEta && !hasStatus && !summary) return '';

    const parts = [];
    if (hasPct) parts.push(`${progress.percentage.toFixed(1)}%`);
    if (hasSpeed) parts.push(`速度 ${progress.speed}`);
    if (hasEta) parts.push(`预计 ${progress.eta}`);
    if (hasStatus) parts.push(`状态 ${progress.status}`);

    return `
      <div class="progress-summary">
        ${parts.length > 0 ? `<span class="progress-badge">${this._esc(parts.join(' | '))}</span>` : ''}
        ${summary ? `<span class="progress-text">${this._esc(summary)}</span>` : ''}
      </div>
    `;
  }

  _renderLoadingLogs() {
    return `
      <div class="log-preview">
        <div class="log-preview-label">最近日志</div>
        <div class="log-line log-loading">正在同步历史数据…</div>
      </div>
    `;
  }

  _renderLogs(logs) {
    if (!logs || logs.length === 0) {
      return `
        <div class="log-preview">
          <div class="log-preview-label">最近日志</div>
          <div class="log-line" style="color: var(--text-muted)">暂无日志</div>
        </div>
      `;
    }
    const lines = logs.slice(-5).map((line) => `<div class="log-line">${this._esc(String(line))}</div>`).join('');
    return `
      <div class="log-preview">
        <div class="log-preview-label">最近日志 (${logs.length} 行)</div>
        ${lines}
      </div>
    `;
  }

  _fmtBytes(bytes) {
    if (bytes == null) return '—';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
    return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' GB';
  }

  _esc(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}
