/**
 * TaskDetailPanel Component
 * Relates-to: FR-4
 *
 * Collapsible detail panel with task info, log details, and LLM Q&A.
 */

class TaskDetailPanel {
  constructor(options = {}) {
    this.panel = document.getElementById('detail-panel');
    this.titleEl = document.getElementById('detail-title');
    this.infoEl = document.getElementById('detail-info');
    this.historyEl = document.getElementById('ask-history');
    this.inputEl = document.getElementById('ask-input');
    this.sendBtn = document.getElementById('btn-send-ask');
    this.closeBtn = document.getElementById('btn-close-detail');
    this.refreshBtn = document.getElementById('btn-refresh-detail');
    this.onClose = options.onClose || (() => {});
    this.apiRequest = options.apiRequest || (() => {});

    this.currentAlias = null;
    this.messages = []; // { role: 'user' | 'assistant', content: string }
    this._logInfo = null; // cached log-info response
    this._changeLogPath = null; // temporary path for change-log dialog

    this._bindEvents();
  }

  _bindEvents() {
    this.closeBtn?.addEventListener('click', () => {
      this.hide();
      this.onClose();
    });

    this.refreshBtn?.addEventListener('click', () => {
      if (this.currentAlias) {
        this._refreshTaskInfo();
      }
    });

    this.sendBtn?.addEventListener('click', () => {
      this._sendQuestion();
    });

    this.inputEl?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this._sendQuestion();
      }
    });

    // Delegate click events for dynamically created buttons
    this.infoEl?.addEventListener('click', (e) => {
      const target = e.target.closest('[data-action]');
      if (!target) return;
      const action = target.dataset.action;
      if (action === 'open-log') {
        const path = target.dataset.path;
        if (path) this._openLogPath(path);
      } else if (action === 'change-log') {
        this._showChangeLogInput();
      } else if (action === 'browse-change-file') {
        this._browseChangeFile();
      } else if (action === 'browse-change-dir') {
        this._browseChangeDir();
      } else if (action === 'confirm-change-log') {
        this._confirmChangeLog();
      } else if (action === 'cancel-change-log') {
        this._hideChangeLogInput();
      }
    });
  }

  async _refreshTaskInfo() {
    if (!this.currentAlias) return;

    this.refreshBtn?.classList.add('spinning');
    try {
      await this._loadTaskInfo(this.currentAlias);
      if (typeof window.showToast === 'function') {
        window.showToast('任务状态已刷新', 'success', 1500);
      }
    } catch (err) {
      console.error('[DetailPanel] Refresh failed:', err);
      if (typeof window.showToast === 'function') {
        window.showToast('刷新失败', 'error', 1500);
      }
    } finally {
      this.refreshBtn?.classList.remove('spinning');
    }
  }

  show(alias) {
    this.currentAlias = alias;
    this.messages = [];
    if (this.historyEl) this.historyEl.innerHTML = '';
    if (this.titleEl) this.titleEl.textContent = alias;

    this.panel?.classList.remove('hidden');
    this._loadTaskInfo(alias);
  }

  hide() {
    this.panel?.classList.add('hidden');
    this.currentAlias = null;
  }

  isVisible() {
    return this.panel && !this.panel.classList.contains('hidden');
  }

  async _loadTaskInfo(alias) {
    try {
      // Fetch both status and log-info in parallel
      const [statusResp, logInfoResp] = await Promise.all([
        this.apiRequest('GET', `/api/tasks/${encodeURIComponent(alias)}/status`),
        this.apiRequest('GET', `/api/tasks/${encodeURIComponent(alias)}/log-info`),
      ]);

      if (statusResp.status === 200 && statusResp.data) {
        this._logInfo = logInfoResp.status === 200 ? logInfoResp.data : null;
        this._renderInfo(statusResp.data);
      }
    } catch (err) {
      console.error('[DetailPanel] Failed to load task info:', err);
      if (this.infoEl) {
        this.infoEl.innerHTML = '<div style="color: var(--color-danger);">加载任务信息失败</div>';
      }
    }
  }

  _renderInfo(data) {
    if (!this.infoEl) return;

    const pid = data.pid || data.registered?.pid || '-';
    const status = data.latest_metrics?.status || '-';
    const cpu = data.latest_metrics?.cpu_percent;
    const mem = data.latest_metrics?.memory_percent;
    const memWset = data.latest_metrics?.memory_working_set;
    const logSource = data.log_source || data.registered?.log_source || '-';
    const progress = data.latest_progress;

    const statusColor = status === 'running' ? 'var(--color-success)' :
      status === 'exited' ? 'var(--color-danger)' :
      status === 'stalled' ? 'var(--color-warning)' : 'var(--text-secondary)';

    let html = '';

    html += this._infoRow('任务名称', data.alias || this.currentAlias);
    html += this._infoRow('进程 PID', pid);
    html += this._infoRow('状态', `<span style="color:${statusColor}">${status}</span>`);

    if (cpu !== undefined) {
      html += this._infoRow('CPU', `${cpu.toFixed(1)}%`);
    }
    if (mem !== undefined) {
      html += this._infoRow('内存占用', `${mem.toFixed(1)}%`);
    }
    if (memWset !== undefined) {
      html += this._infoRow('工作集内存', this._formatBytes(memWset));
    }

    if (progress) {
      html += this._infoRow('进度', `${progress.percentage?.toFixed(1) ?? 0}%`);
      if (progress.speed) {
        html += this._infoRow('速度', progress.speed);
      }
      if (progress.eta) {
        html += this._infoRow('预计剩余', progress.eta);
      }
    }

    // Log source info with open button
    html += this._renderLogSection(logSource);

    this.infoEl.innerHTML = html;
  }

  _renderLogSection(logSource) {
    const logPath = typeof logSource === 'string' ? logSource : (logSource?.paths?.join('; ') || '-');
    const logInfo = this._logInfo;

    let html = '<div class="detail-log-section">';
    html += this._infoRow('日志路径', logPath);

    if (logInfo && logInfo.type !== 'none') {
      if (logInfo.type === 'dir') {
        // Directory mode
        const count = logInfo.count ?? 0;
        const currentFile = logInfo.current_file || '-';
        html += this._infoRow('日志文件数', `${count} 个`);
        html += this._infoRow('当前文件', currentFile);

        if (logInfo.path) {
          html += `<div class="detail-log-actions">
            <button class="btn btn-sm btn-secondary" data-action="open-log" data-path="${this._escapeHtml(logInfo.path)}">
              📁 打开日志目录
            </button>
          </div>`;
        }
      } else if (logInfo.type === 'file') {
        // File mode
        const size = logInfo.size !== null && logInfo.size !== undefined
          ? this._formatBytes(logInfo.size)
          : '-';
        html += this._infoRow('日志大小', size);

        if (logInfo.path) {
          html += `<div class="detail-log-actions">
            <button class="btn btn-sm btn-secondary" data-action="open-log" data-path="${this._escapeHtml(logInfo.path)}">
              📄 用记事本打开
            </button>
          </div>`;
        }
      }
    }

    // Change log source button
    html += `<div class="detail-log-actions">
      <button class="btn btn-sm btn-link" data-action="change-log">更换日志路径</button>
    </div>`;

    // Hidden change-log picker (shown on click)
    html += `<div id="change-log-box" class="change-log-box hidden">
      <div class="change-log-picker">
        <span id="change-log-display" class="change-log-display">未选择</span>
        <button class="btn btn-sm btn-secondary" data-action="browse-change-file">📄 选择文件</button>
        <button class="btn btn-sm btn-secondary" data-action="browse-change-dir">📁 选择目录</button>
      </div>
      <div class="change-log-buttons">
        <button class="btn btn-sm btn-primary" data-action="confirm-change-log">确认更换</button>
        <button class="btn btn-sm btn-secondary" data-action="cancel-change-log">取消</button>
      </div>
    </div>`;

    html += '</div>';
    return html;
  }

  async _openLogPath(filePath) {
    if (!window.electronAPI?.shellOpenPath) {
      console.error('[DetailPanel] shellOpenPath not available');
      if (typeof window.showToast === 'function') {
        window.showToast('无法打开文件：IPC 未就绪', 'error', 2000);
      }
      return;
    }
    try {
      const result = await window.electronAPI.shellOpenPath(filePath);
      if (!result.ok) {
        console.error('[DetailPanel] Open failed:', result.error);
        if (typeof window.showToast === 'function') {
          window.showToast(`打开失败: ${result.error}`, 'error', 2000);
        }
      }
    } catch (err) {
      console.error('[DetailPanel] shellOpenPath error:', err);
      if (typeof window.showToast === 'function') {
        window.showToast('打开文件失败', 'error', 2000);
      }
    }
  }

  _getDefaultPath() {
    // Use current log path's directory as default, or empty string for system default
    const currentPath = this._logInfo?.path || this._logInfo?.current_file;
    if (!currentPath) return '';
    const lastSep = Math.max(currentPath.lastIndexOf('\\'), currentPath.lastIndexOf('/'));
    return lastSep >= 0 ? currentPath.substring(0, lastSep + 1) : currentPath;
  }

  _showChangeLogInput() {
    const box = this.infoEl?.querySelector('#change-log-box');
    if (box) box.classList.remove('hidden');
    this._changeLogPath = null;
    this._updateChangeLogDisplay(null);
  }

  _hideChangeLogInput() {
    const box = this.infoEl?.querySelector('#change-log-box');
    if (box) box.classList.add('hidden');
    this._changeLogPath = null;
  }

  _updateChangeLogDisplay(paths) {
    const display = this.infoEl?.querySelector('#change-log-display');
    if (!display) return;
    if (!paths) {
      display.textContent = '未选择';
      return;
    }
    const parts = paths.split(';');
    if (parts.length === 1) {
      display.textContent = parts[0];
      display.title = parts[0];
    } else {
      display.textContent = `${parts[0]} 等 ${parts.length} 个文件`;
      display.title = paths;
    }
  }

  async _browseChangeFile() {
    if (!window.electronAPI?.showOpenDialog) {
      if (typeof window.showToast === 'function') {
        window.showToast('文件选择不可用', 'error');
      }
      return;
    }
    const defaultPath = this._getDefaultPath();
    const result = await window.electronAPI.showOpenDialog({
      defaultPath,
      properties: ['openFile', 'multiSelections'],
      filters: [
        { name: '日志文件', extensions: ['log', 'txt', 'out'] },
        { name: '所有文件', extensions: ['*'] },
      ],
    });
    if (result.canceled || !result.filePaths?.length) return;

    this._changeLogPath = result.filePaths.join(';');
    this._updateChangeLogDisplay(this._changeLogPath);
  }

  async _browseChangeDir() {
    if (!window.electronAPI?.showOpenDialog) {
      if (typeof window.showToast === 'function') {
        window.showToast('文件选择不可用', 'error');
      }
      return;
    }
    const defaultPath = await this._getDefaultPath();
    const result = await window.electronAPI.showOpenDialog({
      defaultPath,
      properties: ['openDirectory'],
    });
    if (result.canceled || !result.filePaths?.length) return;

    let dirPath = result.filePaths[0];
    if (!dirPath.endsWith('\\') && !dirPath.endsWith('/')) {
      dirPath += '\\';
    }
    this._changeLogPath = dirPath;
    this._updateChangeLogDisplay(this._changeLogPath);
  }

  async _confirmChangeLog() {
    if (!this.currentAlias) return;
    const newPath = this._changeLogPath;
    if (!newPath) {
      if (typeof window.showToast === 'function') {
        window.showToast('请先选择文件或目录', 'warning', 1500);
      }
      return;
    }

    try {
      const resp = await this.apiRequest('PATCH', `/api/tasks/${encodeURIComponent(this.currentAlias)}`, {
        log: newPath,
      });
      if (resp.status === 200) {
        if (typeof window.showToast === 'function') {
          window.showToast('日志路径已更新', 'success', 1500);
        }
        this._hideChangeLogInput();
        // Refresh to show updated info
        this._loadTaskInfo(this.currentAlias);
      } else {
        const msg = resp.data?.message || '更新失败';
        if (typeof window.showToast === 'function') {
          window.showToast(msg, 'error', 2000);
        }
      }
    } catch (err) {
      console.error('[DetailPanel] Change log failed:', err);
      if (typeof window.showToast === 'function') {
        window.showToast('更新日志路径失败', 'error', 2000);
      }
    }
  }

  _infoRow(label, value) {
    return `
      <div class="detail-info-row">
        <span class="detail-info-label">${this._escapeHtml(label)}</span>
        <span class="detail-info-value">${value}</span>
      </div>
    `;
  }

  async _sendQuestion() {
    if (!this.inputEl || !this.currentAlias) return;

    const question = this.inputEl.value.trim();
    if (!question) return;

    // Add user message
    this._addMessage('user', question);
    this.inputEl.value = '';

    // Show loading
    const loadingId = this._addMessage('loading', '思考中...');

    try {
      const resp = await this.apiRequest('POST', `/api/tasks/${encodeURIComponent(this.currentAlias)}/ask`, {
        question,
      });

      // Remove loading
      this._removeMessage(loadingId);

      if (resp.status === 200 && resp.data?.answer) {
        this._addMessage('assistant', resp.data.answer);
      } else {
        const msg = resp.data?.message || '获取回答失败';
        this._addMessage('error', msg);
      }
    } catch (err) {
      this._removeMessage(loadingId);
      this._addMessage('error', '请求失败: ' + err.message);
      console.error('[DetailPanel] Ask failed:', err);
    }
  }

  _addMessage(role, content) {
    if (!this.historyEl) return '';

    const id = 'msg-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
    const el = document.createElement('div');
    el.id = id;
    el.className = `ask-message ${role}`;
    el.textContent = content;
    this.historyEl.appendChild(el);
    this.historyEl.scrollTop = this.historyEl.scrollHeight;
    return id;
  }

  _removeMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
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
