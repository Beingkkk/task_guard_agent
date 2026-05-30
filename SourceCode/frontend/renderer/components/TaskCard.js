/**
 * TaskCard Component
 * Relates-to: FR-4
 *
 * Renders a single task card with status indicator, metrics, progress, and logs.
 */

class TaskCard {
  constructor(task, onDelete) {
    this.task = task;
    this.onDelete = onDelete;
    this.element = null;
    this._render();
  }

  /**
   * Determine card status class based on task data.
   */
  _getStatusClass(data) {
    const metrics = data?.latest_metrics;
    const progress = data?.latest_progress;

    // Critical: process exited or OOM
    if (metrics?.status === 'exited' || metrics?.status === 'oom') {
      return 'status-critical';
    }

    // Danger: high CPU/memory or error status
    if (
      (metrics?.cpu_percent ?? 0) > 90 ||
      (metrics?.memory_percent ?? 0) > 90 ||
      progress?.status === 'error'
    ) {
      return 'status-danger';
    }

    // Warning: stalled or high but not critical
    if (
      data?.state?.file?.stalled ||
      (metrics?.cpu_percent ?? 0) > 70 ||
      (metrics?.memory_percent ?? 0) > 70 ||
      progress?.status === 'stalled'
    ) {
      return 'status-warning';
    }

    return '';
  }

  _render() {
    const data = this.task;
    const statusClass = this._getStatusClass(data);
    const alias = data.alias || data.registered?.alias || 'Unknown';
    const pid = data.registered?.pid || data.pid || '-';
    const logPaths = data.registered?.log_source?.paths ||
      (data.log_source?.paths ? data.log_source.paths : ['-']);
    const metrics = data.latest_metrics || data.metrics || {};
    const progress = data.latest_progress || data.progress || null;
    const recentLogs = data.recent_logs || data.log_lines || [];

    const el = document.createElement('div');
    el.className = `task-card ${statusClass}`;
    el.dataset.alias = alias;

    el.innerHTML = `
      <div class="task-card-header">
        <div class="task-card-title">${this._escapeHtml(alias)}</div>
        <div class="task-card-actions">
          <button class="btn-icon btn-delete" title="注销任务">🗑️</button>
        </div>
      </div>
      <div class="task-card-meta">
        <span>🆔 PID: ${pid}</span>
        <span>📁 ${this._escapeHtml(logPaths[0]?.split('\\').pop() || logPaths[0] || '-')}</span>
      </div>
      <div class="metrics-grid">
        <div class="metric-item">
          <div class="metric-label">CPU</div>
          <div class="metric-value">${metrics.cpu_percent !== undefined ? metrics.cpu_percent.toFixed(1) + '%' : '-'}</div>
        </div>
        <div class="metric-item">
          <div class="metric-label">内存</div>
          <div class="metric-value">${metrics.memory_working_set !== undefined ? this._formatBytes(metrics.memory_working_set) : '-'}</div>
        </div>
        <div class="metric-item">
          <div class="metric-label">状态</div>
          <div class="metric-value ${metrics.status ? 'status-' + metrics.status : ''}">${metrics.status || '-'}</div>
        </div>
        <div class="metric-item">
          <div class="metric-label">退出码</div>
          <div class="metric-value">${metrics.exit_code !== undefined && metrics.exit_code !== null ? metrics.exit_code : '-'}</div>
        </div>
      </div>
      ${this._renderProgress(progress)}
      ${this._renderLogs(recentLogs)}
    `;

    // Bind delete button
    const deleteBtn = el.querySelector('.btn-delete');
    deleteBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (this.onDelete) this.onDelete(alias);
    });

    this.element = el;
    return el;
  }

  _renderProgress(progress) {
    if (!progress) {
      return `
        <div class="progress-section">
          <div class="progress-header">
            <span class="progress-label">进度</span>
            <span class="progress-percent">—</span>
          </div>
          <div class="progress-bar"><div class="progress-fill" style="width: 0%"></div></div>
        </div>
      `;
    }

    const pct = progress.percentage ?? 0;
    const speed = progress.speed || '-';
    const eta = progress.eta || '-';
    const summary = progress.raw_summary || '';

    return `
      <div class="progress-section">
        <div class="progress-header">
          <span class="progress-label">进度</span>
          <span class="progress-percent">${pct.toFixed(1)}%</span>
        </div>
        <div class="progress-bar">
          <div class="progress-fill" style="width: ${Math.min(pct, 100)}%"></div>
        </div>
        <div class="progress-details">
          <span>⚡ ${this._escapeHtml(speed)}</span>
          <span>⏱️ ${this._escapeHtml(eta)}</span>
        </div>
        ${summary ? `<div class="progress-details">${this._escapeHtml(summary)}</div>` : ''}
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

    const lines = logs.slice(-5).map((line) =>
      `<div class="log-line">${this._escapeHtml(String(line))}</div>`
    ).join('');

    return `
      <div class="log-preview">
        <div class="log-preview-label">最近日志 (${logs.length} 行)</div>
        ${lines}
      </div>
    `;
  }

  /**
   * Update card with new data from WebSocket event.
   */
  update(data) {
    // Re-render with merged data
    const merged = { ...this.task, ...data };
    this.task = merged;

    const newEl = this._render();
    if (this.element && this.element.parentNode) {
      this.element.parentNode.replaceChild(newEl, this.element);
    }
    this.element = newEl;
  }

  _formatBytes(bytes) {
    if (bytes === undefined || bytes === null) return '-';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
    return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' GB';
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}
