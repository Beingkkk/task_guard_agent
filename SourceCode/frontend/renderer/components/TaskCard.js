/**
 * TaskCard Component
 * Relates-to: FR-4
 *
 * Renders a single task card with status indicator, metrics, and logs.
 * Progress (if any) is shown as compact text, not a bar.
 * Clicking the card opens the detail panel; delete button removes the task.
 */

class TaskCard {
  constructor(task, onClick, onDelete) {
    this.task = task;
    this.onClick = onClick;
    this.onDelete = onDelete;
    this.element = null;
    this._render();
  }

  /**
   * Determine card status class based on task data.
   */
  _getStatusClass(data) {
    const metrics = data?.latest_metrics || data?.metrics;
    const progress = data?.latest_progress || data?.progress;

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

  /**
   * Normalize logs field: handles both {lines: [...], entry_count: N} (from
   * query_status) and plain [...] (from WebSocket) formats.
   */
  _getLogsArray(data) {
    const logs = data.recent_logs || data.log_lines || [];
    if (logs && typeof logs === 'object' && !Array.isArray(logs)) {
      return logs.lines || [];
    }
    return Array.isArray(logs) ? logs : [];
  }

  _render() {
    const data = this.task;
    const statusClass = this._getStatusClass(data);
    const alias = data.alias || data.registered?.alias || 'Unknown';
    const pid = data.pid || data.registered?.pid || '-';

    // Handle both log_source formats: query_status returns {type,path,extensions}
    let logPath = '-';
    if (data.log_source?.path) {
      logPath = data.log_source.path.split('\\').pop() || data.log_source.path;
    } else if (data.registered?.log_source?.paths) {
      logPath = data.registered.log_source.paths[0]?.split('\\').pop() || '-';
    }

    const metrics = data.latest_metrics || data.metrics || {};
    const progress = data.latest_progress || data.progress || null;
    const recentLogs = this._getLogsArray(data);

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
        <span>📁 ${this._escapeHtml(logPath)}</span>
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
          <div class="metric-label">内存%</div>
          <div class="metric-value">${metrics.memory_percent !== undefined ? metrics.memory_percent.toFixed(1) + '%' : '-'}</div>
        </div>
      </div>
      ${this._renderProgress(progress)}
      ${this._renderLogs(recentLogs)}
    `;

    // Click card to open detail
    el.addEventListener('click', (e) => {
      if (e.target.closest('.btn-delete')) return;
      if (this.onClick) this.onClick(alias);
    });

    // Bind delete button
    const deleteBtn = el.querySelector('.btn-delete');
    deleteBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (this.onDelete) this.onDelete(alias);
    });

    this.element = el;
    return el;
  }

  /**
   * Render compact progress text (no bar). Returns empty string if no
   * *meaningful* progress — avoids showing progress UI for non-download tasks.
   */
  _renderProgress(progress) {
    if (!progress) return '';

    const hasPercentage = progress.percentage !== undefined &&
                          progress.percentage !== null &&
                          progress.percentage > 0;
    const hasSpeed = progress.speed && progress.speed !== '0 B/s';
    const hasEta = progress.eta && progress.eta !== '';
    const hasMeaningfulStatus = progress.status &&
                                 progress.status !== 'unknown' &&
                                 progress.status !== 'normal';
    const summary = progress.raw_summary || '';

    if (!hasPercentage && !hasSpeed && !hasEta && !hasMeaningfulStatus && !summary) {
      return '';
    }

    const parts = [];
    if (hasPercentage) {
      parts.push(`${progress.percentage.toFixed(1)}%`);
    }
    if (hasSpeed) parts.push(`速度 ${progress.speed}`);
    if (hasEta) parts.push(`预计 ${progress.eta}`);
    if (hasMeaningfulStatus) {
      parts.push(`状态 ${progress.status}`);
    }

    return `
      <div class="progress-summary">
        ${parts.length > 0 ? `<span class="progress-badge">${this._escapeHtml(parts.join(' | '))}</span>` : ''}
        ${summary ? `<span class="progress-text">${this._escapeHtml(summary)}</span>` : ''}
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
   * Normalizes field names before merging.
   */
  update(data) {
    // Normalize incoming data format differences between WebSocket and REST API
    const normalized = { ...data };

    // WebSocket sends 'metrics' / 'progress' / 'log_lines'
    // query_status returns 'latest_metrics' / 'latest_progress' / 'recent_logs'
    if (normalized.metrics && !normalized.latest_metrics) {
      normalized.latest_metrics = normalized.metrics;
    }
    if (normalized.progress && !normalized.latest_progress) {
      normalized.latest_progress = normalized.progress;
    }
    if (normalized.log_lines && !normalized.recent_logs) {
      normalized.recent_logs = normalized.log_lines;
    }
    // query_status returns recent_logs as {lines, entry_count}
    if (normalized.recent_logs && typeof normalized.recent_logs === 'object' && !Array.isArray(normalized.recent_logs)) {
      normalized.recent_logs = normalized.recent_logs.lines || [];
    }

    const merged = { ...this.task, ...normalized };
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
