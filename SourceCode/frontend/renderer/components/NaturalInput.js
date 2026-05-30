/**
 * NaturalInput Component
 * Relates-to: FR-4
 *
 * Bottom-fixed natural language input bar.
 */

class NaturalInput {
  constructor(options = {}) {
    this.onSubmit = options.onSubmit || (() => {});
    this.input = document.getElementById('natural-input');
    this.sendBtn = document.getElementById('btn-send-natural');
    this.feedback = document.getElementById('natural-feedback');
    this._bindEvents();
  }

  _bindEvents() {
    if (!this.input) return;

    // Enter key to submit
    this.input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.submit();
      }
    });

    // Send button
    this.sendBtn?.addEventListener('click', () => this.submit());
  }

  submit() {
    const text = this.input?.value?.trim();
    if (!text) return;

    this.onSubmit(text);
    this.input.value = '';
  }

  showFeedback(message, type = 'info') {
    if (!this.feedback) return;
    this.feedback.textContent = message;
    this.feedback.className = `natural-feedback ${type}`;

    // Auto-clear after 5s
    setTimeout(() => {
      if (this.feedback.textContent === message) {
        this.feedback.textContent = '';
        this.feedback.className = 'natural-feedback';
      }
    }, 5000);
  }

  focus() {
    this.input?.focus();
  }
}
