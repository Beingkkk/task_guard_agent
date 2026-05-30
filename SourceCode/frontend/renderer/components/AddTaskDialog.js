/**
 * AddTaskDialog Component
 * Relates-to: FR-4
 *
 * Modal dialog for registering new tasks.
 */

class AddTaskDialog {
  constructor(options = {}) {
    this.onSubmit = options.onSubmit || (() => {});
    this.dialog = document.getElementById('add-task-dialog');
    this.form = document.getElementById('add-task-form');
    this.overlay = this.dialog?.querySelector('.modal-overlay');
    this._bindEvents();
  }

  _bindEvents() {
    if (!this.dialog || !this.form) return;

    // Close on overlay click
    this.overlay.addEventListener('click', () => this.hide());

    // Close button
    const closeBtn = document.getElementById('btn-close-dialog');
    closeBtn?.addEventListener('click', () => this.hide());

    // Cancel button
    const cancelBtn = document.getElementById('btn-cancel-dialog');
    cancelBtn?.addEventListener('click', () => this.hide());

    // Form submit
    this.form.addEventListener('submit', (e) => {
      e.preventDefault();
      this._handleSubmit();
    });

    // Open button (global)
    const openBtn = document.getElementById('btn-add-task');
    openBtn?.addEventListener('click', () => this.show());
  }

  show() {
    if (!this.dialog) return;
    this.dialog.classList.remove('hidden');
    // Focus alias input
    const aliasInput = document.getElementById('task-alias');
    setTimeout(() => aliasInput?.focus(), 50);
  }

  hide() {
    if (!this.dialog) return;
    this.dialog.classList.add('hidden');
    this.form?.reset();
  }

  _handleSubmit() {
    const formData = new FormData(this.form);
    const payload = {
      alias: formData.get('alias')?.trim(),
      log: formData.get('log')?.trim(),
    };

    const pid = formData.get('pid');
    if (pid && pid.trim()) {
      payload.pid = parseInt(pid, 10);
    }

    const toolHint = formData.get('tool_hint');
    if (toolHint) {
      payload.tool_hint = toolHint;
    }

    // Validate
    if (!payload.alias) {
      this._showFeedback('请填写任务别名', 'error');
      return;
    }
    if (!payload.log) {
      this._showFeedback('请填写日志文件路径', 'error');
      return;
    }

    this.onSubmit(payload);
    this.hide();
  }

  _showFeedback(message, type) {
    // Use the app's toast notification
    if (typeof window.showToast === 'function') {
      window.showToast(message, type);
    } else {
      console.log(`[Dialog] ${type}: ${message}`);
    }
  }
}
