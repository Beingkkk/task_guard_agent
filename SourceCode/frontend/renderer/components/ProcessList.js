/**
 * ProcessList Component
 * Relates-to: FR-4
 *
 * Renders the left panel process list with search and selection.
 */

class ProcessList {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    this.searchInput = document.getElementById('process-search');
    this.countLabel = document.getElementById('process-count');
    this.watchButton = document.getElementById('btn-watch-selected');
    this.onSelect = options.onSelect || (() => {});
    this.onWatch = options.onWatch || (() => {});

    this.processes = [];
    this.filtered = [];
    this.selectedPid = null;

    this._bindEvents();
  }

  _bindEvents() {
    if (!this.searchInput) return;

    this.searchInput.addEventListener('input', () => {
      this._filter(this.searchInput.value.trim());
    });

    this.watchButton?.addEventListener('click', () => {
      const proc = this.processes.find((p) => p.pid === this.selectedPid);
      if (proc) {
        this.onWatch(proc);
      }
    });

    // Refresh button next to search box
    const refreshBtn = document.getElementById('btn-refresh-processes');
    refreshBtn?.addEventListener('click', () => {
      this.refresh();
    });
  }

  /**
   * Refresh the process list from the backend.
   */
  async refresh() {
    const btn = document.getElementById('btn-refresh-processes');
    if (btn) btn.classList.add('spinning');

    try {
      await this.loadProcesses(window.apiRequest);
      if (typeof window.showToast === 'function') {
        window.showToast('进程列表已更新', 'success', 1500);
      }
    } catch (err) {
      console.error('[ProcessList] Refresh failed:', err);
      if (typeof window.showToast === 'function') {
        window.showToast('更新失败', 'error', 1500);
      }
    } finally {
      if (btn) btn.classList.remove('spinning');
    }
  }

  /**
   * Load and render all processes from the backend.
   */
  async loadProcesses(apiFetch) {
    try {
      const resp = await apiFetch('GET', '/api/processes');
      if (resp.status === 200 && resp.data?.processes) {
        this.processes = resp.data.processes;
        this._filter(this.searchInput?.value?.trim() || '');
      }
    } catch (err) {
      console.error('[ProcessList] Failed to load processes:', err);
    }
  }

  _filter(query) {
    const q = query.toLowerCase();
    if (!q) {
      this.filtered = [...this.processes];
    } else {
      this.filtered = this.processes.filter((p) => {
        const nameMatch = (p.name || '').toLowerCase().includes(q);
        const pidMatch = String(p.pid).includes(q);
        const pathMatch = (p.exe || '').toLowerCase().includes(q);
        return nameMatch || pidMatch || pathMatch;
      });
    }
    this._render();
  }

  _render() {
    if (!this.container) return;

    this.container.innerHTML = '';

    if (this.filtered.length === 0) {
      this.container.innerHTML = `<div class="empty-state" style="padding: 20px;">
        <p style="font-size: 0.875rem; color: var(--text-muted);">无匹配进程</p>
      </div>`;
      this._updateCount(0);
      return;
    }

    for (const proc of this.filtered) {
      const el = document.createElement('div');
      el.className = 'process-item';
      if (proc.pid === this.selectedPid) {
        el.classList.add('selected');
      }
      el.dataset.pid = proc.pid;

      const displayName = this._escapeHtml(proc.name || 'Unknown');
      const displayPath = this._escapeHtml(proc.exe || '');

      el.innerHTML = `
        <div class="process-name">${displayName}</div>
        <div class="process-pid">PID: ${proc.pid}</div>
        ${displayPath ? `<div class="process-path" title="${displayPath}">${displayPath}</div>` : ''}
      `;

      el.addEventListener('click', () => {
        this._select(proc.pid);
      });

      this.container.appendChild(el);
    }

    this._updateCount(this.filtered.length);
  }

  _select(pid) {
    this.selectedPid = pid;

    // Update visual selection
    const items = this.container?.querySelectorAll('.process-item');
    items?.forEach((item) => {
      item.classList.toggle('selected', Number(item.dataset.pid) === pid);
    });

    // Enable/disable watch button
    if (this.watchButton) {
      this.watchButton.disabled = false;
    }

    const proc = this.processes.find((p) => p.pid === pid);
    if (proc) {
      this.onSelect(proc);
    }
  }

  _updateCount(count) {
    if (this.countLabel) {
      this.countLabel.textContent = `${count} 个进程`;
    }
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}
