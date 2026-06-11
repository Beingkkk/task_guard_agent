/**
 * TaskGuard Renderer App
 * Relates-to: FR-4
 *
 * Main application logic: coordinates API calls, WebSocket events,
 * and UI components.
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

  // Expose globally for components
  window.showToast = showToast;

  // ── Connection Status ──────────────────────────────────────────────────────

  function setConnectionStatus(connected) {
    const dot = document.getElementById('connection-status');
    if (!dot) return;
    dot.className = `status-dot ${connected ? 'online' : 'offline'}`;
    dot.title = connected ? '已连接' : '未连接';
  }

  // ── App State ──────────────────────────────────────────────────────────────

  const state = {
    tasks: [],
    connected: false,
  };

  // ── Components ─────────────────────────────────────────────────────────────

  let taskGrid = null;
  let addDialog = null;
  let naturalInput = null;

  // ── Load Tasks ─────────────────────────────────────────────────────────────

  async function loadTasks() {
    try {
      const resp = await apiRequest('GET', '/api/tasks');
      if (resp.status === 200 && resp.data?.tasks) {
        state.tasks = resp.data.tasks;
        taskGrid?.renderTasks(state.tasks);
      }
    } catch (err) {
      console.error('[App] Failed to load tasks:', err);
      showToast('加载任务列表失败', 'error');
    }
  }

  // ── Register Task ──────────────────────────────────────────────────────────

  async function registerTask(payload) {
    try {
      showToast('正在注册...', 'info', 2000);
      const resp = await apiRequest('POST', '/api/tasks', payload);

      if (resp.status === 201) {
        showToast(`任务 "${payload.alias}" 注册成功`, 'success');
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

  // ── Delete Task ────────────────────────────────────────────────────────────

  async function deleteTask(alias) {
    if (!confirm(`确定要注销任务 "${alias}" 吗？`)) return;

    try {
      const resp = await apiRequest('DELETE', `/api/tasks/${encodeURIComponent(alias)}`);
      if (resp.status === 204) {
        showToast(`任务 "${alias}" 已注销`, 'success');
        taskGrid?.removeTask(alias);
      } else {
        showToast('注销失败', 'error');
      }
    } catch (err) {
      console.error('[App] Delete failed:', err);
      showToast('注销失败: ' + err.message, 'error');
    }
  }

  // ── Natural Language ───────────────────────────────────────────────────────

  async function handleNaturalInput(text) {
    naturalInput?.showFeedback('处理中...', 'info');

    try {
      const resp = await apiRequest('POST', '/api/natural', { text });
      const data = resp.data;

      if (data?.executed) {
        naturalInput?.showFeedback(
          `✅ 已执行: ${data.intent}`,
          'success'
        );
        // Refresh task list if the operation might have changed it
        if (['watch_task', 'unwatch_task'].includes(data.intent)) {
          await loadTasks();
        }
      } else if (data?.missing_params?.length > 0) {
        naturalInput?.showFeedback(
          `⚠️ 缺少参数: ${data.missing_params.join(', ')}`,
          'error'
        );
      } else {
        naturalInput?.showFeedback(
          data?.message || '无法执行该指令',
          'error'
        );
      }
    } catch (err) {
      console.error('[App] Natural language failed:', err);
      naturalInput?.showFeedback('请求失败: ' + err.message, 'error');
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
      setConnectionStatus(true);
      showToast('WebSocket 已连接', 'success', 2000);
    });

    wsService.on('disconnected', () => {
      state.connected = false;
      setConnectionStatus(false);
    });

    wsService.on('task.updated', (data) => {
      // Merge updated data into existing task card
      if (data?.alias) {
        taskGrid?.addOrUpdateTask({
          alias: data.alias,
          latest_metrics: data.metrics,
          latest_progress: data.progress,
          recent_logs: data.log_lines,
        });
      }
    });

    wsService.on('task.alert', (data) => {
      showToast(
        `⚠️ ${data?.alias}: ${data?.message || data?.rule || '告警'}`,
        'error',
        5000
      );
    });

    wsService.on('task.oom', (data) => {
      showToast(
        `🔴 ${data?.alias}: 进程异常退出 / OOM`,
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

    // Update maximize button icon based on state
    if (window.electronAPI?.onMaximizeChange) {
      window.electronAPI.onMaximizeChange((isMaximized) => {
        const svg = btnMax.querySelector('svg');
        if (!svg) return;
        if (isMaximized) {
          // Restore icon (overlapping squares)
          svg.innerHTML = `
            <rect x="2.5" y="2.5" width="4" height="4" fill="none" stroke="currentColor" stroke-width="0.8"/>
            <rect x="3.5" y="3.5" width="4" height="4" fill="none" stroke="currentColor" stroke-width="0.8"/>
          `;
          btnMax.title = '还原';
          document.body.classList.add('maximized');
        } else {
          // Maximize icon (single square)
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

    // Initialize components
    taskGrid = new TaskGrid('task-grid', {
      onDelete: deleteTask,
    });

    addDialog = new AddTaskDialog({
      onSubmit: registerTask,
    });

    naturalInput = new NaturalInput({
      onSubmit: handleNaturalInput,
    });

    // Set up WebSocket listeners
    setupWebSocket();

    // Backend error handler (e.g., Python failed to start)
    if (typeof window.electronAPI?.onBackendError === 'function') {
      window.electronAPI.onBackendError((msg) => {
        showToast(`后端错误: ${msg}`, 'error', 10000);
        setConnectionStatus(false);
      });
    }

    // Initial load
    loadTasks();

    // Poll for updates every 10s as fallback (WebSocket is primary)
    setInterval(loadTasks, 10000);

    console.log('[App] Initialized');
  }

  // Start when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
