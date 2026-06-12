/**
 * TaskGuard Renderer App (Refactored)
 * Relates-to: FR-4
 *
 * Two-panel layout: process list on the left, task monitoring on the right.
 * Status bar with refresh interval and manual refresh.
 * Detail panel with LLM Q&A on card click.
 */

(function () {
  'use strict';

  // ── API Helper ─────────────────────────────────────────────────────────────

  async function apiRequest(method, path, body) {
    if (typeof window.electronAPI === 'undefined') {
      throw new Error('electronAPI not available');
    }
    const response = await window.electronAPI.invoke('api:request', { method, path, body });
    return response;
  }

  // Expose for components
  window.apiRequest = apiRequest;

  // ── Toast Notification ─────────────────────────────────────────────────────

  function showToast(message, type = 'info', duration = 3000) {
    const toast = document.getElementById('toast');
    const toastMsg = document.getElementById('toast-message');
    if (!toast || !toastMsg) return;

    toastMsg.textContent = message;
    toast.className = `toast ${type}`;

    setTimeout(() => {
      toast.classList.add('hidden');
    }, duration);
  }

  window.showToast = showToast;

  // ── Confirm Dialog ─────────────────────────────────────────────────────────

  function showConfirm(message) {
    return new Promise((resolve) => {
      const dialog = document.getElementById('confirm-dialog');
      const messageEl = document.getElementById('confirm-message');
      const okBtn = document.getElementById('btn-confirm-ok');
      const cancelBtn = document.getElementById('btn-confirm-cancel');
      const overlay = dialog?.querySelector('.modal-overlay');

      if (!dialog || !messageEl || !okBtn || !cancelBtn) {
        resolve(false);
        return;
      }

      // Prevent re-entry while a confirm is already open
      if (!dialog.classList.contains('hidden')) {
        resolve(false);
        return;
      }

      messageEl.textContent = message;
      dialog.classList.remove('hidden');

      let resolved = false;

      const cleanup = () => {
        if (resolved) return;
        resolved = true;
        dialog.classList.add('hidden');
        okBtn.removeEventListener('click', onOk);
        cancelBtn.removeEventListener('click', onCancel);
        overlay?.removeEventListener('click', onCancel);
        document.removeEventListener('keydown', onKeyDown);
      };

      const onOk = () => {
        cleanup();
        resolve(true);
      };

      const onCancel = () => {
        cleanup();
        resolve(false);
      };

      const onKeyDown = (e) => {
        if (e.key === 'Escape') {
          e.preventDefault();
          onCancel();
          return;
        }
        if (e.key === 'Tab') {
          const focusable = [cancelBtn, okBtn];
          const current = document.activeElement;
          const idx = focusable.indexOf(current);
          if (idx === -1) {
            e.preventDefault();
            focusable[0].focus();
            return;
          }
          const nextIdx = e.shiftKey
            ? (idx - 1 + focusable.length) % focusable.length
            : (idx + 1) % focusable.length;
          e.preventDefault();
          focusable[nextIdx].focus();
        }
      };

      okBtn.addEventListener('click', onOk);
      cancelBtn.addEventListener('click', onCancel);
      overlay?.addEventListener('click', onCancel);
      document.addEventListener('keydown', onKeyDown);

      // Focus the OK button by default; Tab cycles between buttons, Escape cancels
      requestAnimationFrame(() => {
        if (!resolved) okBtn.focus();
      });
    });
  }

  window.showConfirm = showConfirm;

  // ── Status Bar ─────────────────────────────────────────────────────────────

  let refreshIntervalSec = 60;
  let refreshTimer = null;

  function initStatusBar() {
    const input = document.getElementById('refresh-interval');
    const applyBtn = document.getElementById('btn-apply-refresh');

    if (input && applyBtn) {
      applyBtn.addEventListener('click', () => {
        let value = parseInt(input.value, 10);
        if (Number.isNaN(value) || value < 60) {
          value = 60;
          input.value = 60;
          showToast('刷新周期不能小于 60 秒，已设为 60 秒', 'warning', 2000);
        }
        refreshIntervalSec = value;
        restartRefreshTimer();
        showToast(`刷新周期已设为 ${value} 秒`, 'success', 1500);
      });

      // Allow Enter key to apply
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          applyBtn.click();
        }
      });
    }
  }

  function startRefreshTimer() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
      loadTasks();
    }, refreshIntervalSec * 1000);
  }

  function restartRefreshTimer() {
    startRefreshTimer();
  }

  // ── App State ──────────────────────────────────────────────────────────────

  const state = {
    tasks: [],
    connected: false,
    selectedProcess: null,
  };

  // ── Components ─────────────────────────────────────────────────────────────

  let processList = null;
  let taskGrid = null;
  let detailPanel = null;
  let watchDialog = null;

  // ── Process List ───────────────────────────────────────────────────────────

  async function loadProcesses() {
    await processList?.loadProcesses(apiRequest);
  }

  function handleProcessSelect(proc) {
    state.selectedProcess = proc;
  }

  function handleProcessWatch(proc) {
    state.selectedProcess = proc;
    watchDialog?.show(proc);
  }

  // ── Watch Dialog ───────────────────────────────────────────────────────────

  class WatchDialog {
    constructor() {
      this.dialog = document.getElementById('watch-dialog');
      this.form = document.getElementById('watch-form');
      this.overlay = this.dialog?.querySelector('.modal-overlay');
      this.processInfoEl = document.getElementById('watch-process-info');
      this.aliasInput = document.getElementById('watch-alias');
      this.logInput = document.getElementById('watch-log');
      this.logDisplay = document.getElementById('watch-log-display');
      this._defaultPath = null;
      this._bindEvents();
    }

    _bindEvents() {
      if (!this.dialog || !this.form) return;

      this.overlay?.addEventListener('click', () => this.hide());
      document.getElementById('btn-close-watch-dialog')?.addEventListener('click', () => this.hide());
      document.getElementById('btn-cancel-watch')?.addEventListener('click', () => this.hide());

      document.getElementById('btn-browse-file')?.addEventListener('click', () => this._browseFile());
      document.getElementById('btn-browse-dir')?.addEventListener('click', () => this._browseDir());

      this.form.addEventListener('submit', (e) => {
        e.preventDefault();
        this._handleSubmit();
      });
    }

    _getDefaultPath() {
      return this._defaultPath || '';
    }

    _extractDir(exePath) {
      if (!exePath) return '';
      const lastSep = Math.max(exePath.lastIndexOf('\\'), exePath.lastIndexOf('/'));
      return lastSep >= 0 ? exePath.substring(0, lastSep + 1) : exePath;
    }

    async _browseFile() {
      if (!window.electronAPI?.showOpenDialog) {
        showToast('文件选择不可用', 'error');
        return;
      }
      const result = await window.electronAPI.showOpenDialog({
        defaultPath: this._getDefaultPath(),
        properties: ['openFile', 'multiSelections'],
        filters: [
          { name: '日志文件', extensions: ['log', 'txt', 'out'] },
          { name: '所有文件', extensions: ['*'] },
        ],
      });
      if (result.canceled || !result.filePaths?.length) return;

      const paths = result.filePaths.join(';');
      this.logInput.value = paths;
      this._updateDisplay(paths);
    }

    async _browseDir() {
      if (!window.electronAPI?.showOpenDialog) {
        showToast('文件选择不可用', 'error');
        return;
      }
      const result = await window.electronAPI.showOpenDialog({
        defaultPath: this._getDefaultPath(),
        properties: ['openDirectory'],
      });
      if (result.canceled || !result.filePaths?.length) return;

      let dirPath = result.filePaths[0];
      // Ensure trailing separator for directory recognition
      if (!dirPath.endsWith('\\') && !dirPath.endsWith('/')) {
        dirPath += '\\';
      }
      this.logInput.value = dirPath;
      this._updateDisplay(dirPath);
    }

    _updateDisplay(paths) {
      if (!this.logDisplay) return;
      if (!paths) {
        this.logDisplay.textContent = '未选择';
        return;
      }
      // Show abbreviated path for display
      const parts = paths.split(';');
      if (parts.length === 1) {
        this.logDisplay.textContent = parts[0];
        this.logDisplay.title = parts[0];
      } else {
        this.logDisplay.textContent = `${parts[0]} 等 ${parts.length} 个文件`;
        this.logDisplay.title = paths;
      }
    }

    show(proc) {
      if (!this.dialog) return;

      this.currentProc = proc;
      this.aliasInput.value = proc.name || '';
      this.logInput.value = '';
      this._updateDisplay(null);

      // Default path = process exe directory
      this._defaultPath = this._extractDir(proc.exe);

      if (this.processInfoEl) {
        const name = this._escapeHtml(proc.name || 'Unknown');
        const exe = this._escapeHtml(proc.exe || '-');
        this.processInfoEl.innerHTML = `
          <table class="process-info-table">
            <tr><td class="pi-label">名称</td><td class="pi-value">${name}</td></tr>
            <tr><td class="pi-label">PID</td><td class="pi-value pi-mono">${proc.pid}</td></tr>
            <tr><td class="pi-label">路径</td><td class="pi-value pi-path">${exe}</td></tr>
          </table>
        `;
      }

      this.dialog.classList.remove('hidden');
      setTimeout(() => this.aliasInput?.focus(), 50);
    }

    hide() {
      if (!this.dialog) return;
      this.dialog.classList.add('hidden');
      this.form?.reset();
      this.logInput.value = '';
      this._updateDisplay(null);
      this.currentProc = null;
    }

    async _handleSubmit() {
      if (!this.currentProc) return;

      const alias = this.aliasInput?.value?.trim();
      const log = this.logInput?.value?.trim();

      if (!alias) {
        showToast('请填写监视名称', 'error');
        return;
      }

      const payload = {
        alias,
        pid: this.currentProc.pid,
      };
      if (log) {
        payload.log = log;
      }

      try {
        showToast('正在注册监控...', 'info', 2000);
        const resp = await apiRequest('POST', '/api/tasks', payload);

        if (resp.status === 201) {
          showToast(`任务 "${alias}" 注册成功`, 'success');
          this.hide();
          await loadTasks();
        } else if (resp.status === 409) {
          showToast(resp.data?.message || '任务已存在', 'error');
        } else {
          showToast(resp.data?.message || '注册失败', 'error');
        }
      } catch (err) {
        console.error('[App] Register failed:', err);
        showToast('注册失败: ' + err.message, 'error');
      }
    }

    _escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }
  }

  // ── Refresh Status Indicator ───────────────────────────────────────────────

  function setRefreshStatus(loading, text) {
    const item = document.getElementById('refresh-status-item');
    const spinner = document.getElementById('refresh-spinner');
    const label = document.getElementById('refresh-status-text');
    if (!item || !spinner || !label) return;

    if (loading) {
      item.style.opacity = '1';
      spinner.classList.add('spinning');
      label.textContent = text || '正在刷新…';
    } else {
      item.style.opacity = '0';
      spinner.classList.remove('spinning');
      label.textContent = '';
    }
  }

  // ── Task Grid ──────────────────────────────────────────────────────────────

  async function loadTasks() {
    setRefreshStatus(true, '正在刷新…');
    try {
      const resp = await apiRequest('GET', '/api/tasks');
      if (resp.status === 200 && resp.data?.tasks) {
        const basicTasks = resp.data.tasks;
        const currentAliases = new Set(taskGrid?.getTaskAliases() || []);
        const newAliases = new Set(basicTasks.map((t) => t.alias));

        // 1. Render cards immediately with basic info so the UI doesn't stay blank
        state.tasks = basicTasks;
        for (const task of basicTasks) {
          taskGrid?.addOrUpdateTask(task);
        }

        // 2. Fetch full status in batch to avoid browser connection limits
        if (basicTasks.length > 0) {
          const aliases = basicTasks.map((t) => t.alias);
          apiRequest('POST', '/api/tasks/batch-status', { aliases })
            .then((batchResp) => {
              if (batchResp.status === 200 && batchResp.data?.tasks) {
                for (const task of batchResp.data.tasks) {
                  taskGrid?.addOrUpdateTask(task);
                }
              }
            })
            .catch((e) => {
              console.error('[App] Batch status failed:', e);
            });
        }

        // Remove cards for tasks that no longer exist
        for (const alias of currentAliases) {
          if (!newAliases.has(alias)) {
            taskGrid?.removeTask(alias);
          }
        }
      } else {
        state.tasks = [];
        taskGrid?.renderTasks([]);
      }
    } catch (err) {
      console.error('[App] Failed to load tasks:', err);
    } finally {
      setRefreshStatus(false);
    }
  }

  function handleTaskClick(alias) {
    detailPanel?.show(alias);
  }

  const _deleting = new Set();

  async function deleteTask(alias) {
    if (_deleting.has(alias)) return;
    _deleting.add(alias);

    try {
      const confirmed = await showConfirm(`确定要注销任务 "${alias}" 吗？`);
      if (!confirmed) return;

      const resp = await apiRequest('DELETE', `/api/tasks/${encodeURIComponent(alias)}`);
      if (resp.status === 204) {
        showToast(`任务 "${alias}" 已注销`, 'success');
        taskGrid?.removeTask(alias);
        // Close detail panel if open for this task
        if (detailPanel?.currentAlias === alias) {
          detailPanel.hide();
        }
      } else {
        const message = resp.data?.message || `HTTP ${resp.status}`;
        showToast(`注销失败: ${message}`, 'error');
      }
    } catch (err) {
      console.error('[App] Delete failed:', err);
      showToast('注销失败: ' + err.message, 'error');
    } finally {
      _deleting.delete(alias);
    }
  }

  function handleTaskUpdated(alias, data, isUpdate) {
    if (isUpdate && detailPanel?.currentAlias === alias && detailPanel?.isVisible()) {
      detailPanel.refreshSilently();
    }
  }

  // ── WebSocket Event Handlers ───────────────────────────────────────────────

  function setupWebSocket() {
    if (typeof wsService === 'undefined') {
      console.warn('[App] wsService not available');
      return;
    }

    wsService.on('connected', () => {
      state.connected = true;
      showToast('WebSocket 已连接', 'success', 2000);
    });

    wsService.on('disconnected', () => {
      state.connected = false;
    });

    wsService.on('task.updated', (data) => {
      if (data?.alias) {
        taskGrid?.addOrUpdateTask({
          alias: data.alias,
          timestamp: data.timestamp,
          latest_metrics: data.metrics,
          latest_state_summary: data.state_summary,
          recent_logs: data.log_lines,
        });
      }
    });

    wsService.on('task.alert', (data) => {
      showToast(
        `[告警] ${data?.alias}: ${data?.message || data?.rule || '告警'}`,
        'error',
        5000
      );
    });

    wsService.on('task.oom', (data) => {
      showToast(
        `[异常退出] ${data?.alias}: 进程异常退出 / OOM`,
        'error',
        8000
      );
    });
  }

  // ── Title Bar ───────────────────────────────────────────────────────────────

  function initTitleBar() {
    const btnMin = document.getElementById('tb-minimize');
    const btnMax = document.getElementById('tb-maximize');
    const btnClose = document.getElementById('tb-close');
    if (!btnMin || !btnMax || !btnClose) return;

    btnMin.addEventListener('click', () => {
      window.electronAPI?.minimizeWindow?.();
    });

    btnMax.addEventListener('click', () => {
      window.electronAPI?.maximizeWindow?.();
    });

    btnClose.addEventListener('click', () => {
      window.electronAPI?.closeWindow?.();
    });

    if (window.electronAPI?.onMaximizeChange) {
      window.electronAPI.onMaximizeChange((isMaximized) => {
        const svg = btnMax.querySelector('svg');
        if (!svg) return;
        if (isMaximized) {
          svg.innerHTML = `
            <rect x="2.5" y="2.5" width="4" height="4" fill="none" stroke="currentColor" stroke-width="0.8"/>
            <rect x="3.5" y="3.5" width="4" height="4" fill="none" stroke="currentColor" stroke-width="0.8"/>
          `;
          btnMax.title = '还原';
          document.body.classList.add('maximized');
        } else {
          svg.innerHTML = `
            <rect x="0.5" y="0.5" width="9" height="9" fill="none" stroke="currentColor" stroke-width="1"/>
          `;
          btnMax.title = '最大化';
          document.body.classList.remove('maximized');
        }
      });
    }
  }

  // ── Initialization ─────────────────────────────────────────────────────────

  function init() {
    console.log('[App] Initializing TaskGuard renderer...');
    initTitleBar();
    initStatusBar();

    // Initialize components
    processList = new ProcessList('process-list', {
      onSelect: handleProcessSelect,
      onWatch: handleProcessWatch,
    });

    taskGrid = new TaskGrid('task-grid', {
      onClick: handleTaskClick,
      onDelete: deleteTask,
      onTaskUpdated: handleTaskUpdated,
    });

    detailPanel = new TaskDetailPanel({
      onClose: () => {},
      apiRequest,
    });

    watchDialog = new WatchDialog();

    // Set up WebSocket listeners
    setupWebSocket();

    // Backend error handler
    if (typeof window.electronAPI?.onBackendError === 'function') {
      window.electronAPI.onBackendError((msg) => {
        showToast(`后端错误: ${msg}`, 'error', 10000);
      });
    }

    // Initial load
    loadProcesses();
    loadTasks();

    // Start refresh timer
    startRefreshTimer();

    console.log('[App] Initialized');
  }

  // Start when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
