/**
 * TaskGrid Component — Refactored
 * Relates-to: FR-4
 *
 * Manages the grid of task cards. Handles initial load, updates from
 * WebSocket events, and empty state.
 */

class TaskGrid {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    this.emptyState = document.getElementById('empty-state');
    this.cards = new Map(); // alias -> TaskCard
    this.onClick = options.onClick || (() => {});
    this.onDelete = options.onDelete || (() => {});
    this.onTaskUpdated = options.onTaskUpdated || (() => {});
  }

  renderTasks(tasks) {
    this.container.innerHTML = '';
    this.cards.clear();

    if (!tasks || tasks.length === 0) {
      this._showEmpty(true);
      return;
    }

    this._showEmpty(false);

    for (const task of tasks) {
      this._addCard(task);
    }
  }

  addOrUpdateTask(taskData) {
    const alias = taskData.alias || taskData.registered?.alias;
    if (!alias) return;

    const isUpdate = this.cards.has(alias);
    if (isUpdate) {
      this.cards.get(alias).update(taskData);
    } else {
      this._showEmpty(false);
      this._addCard(taskData);
    }

    this.onTaskUpdated(alias, taskData, isUpdate);
  }

  removeTask(alias) {
    const card = this.cards.get(alias);
    if (card?.element) {
      card.element.remove();
    }
    this.cards.delete(alias);
    if (this.cards.size === 0) {
      this._showEmpty(true);
    }
  }

  getTaskAliases() {
    return Array.from(this.cards.keys());
  }

  _addCard(task) {
    const alias = task.alias || task.registered?.alias;
    if (!alias || this.cards.has(alias)) return;

    const card = new TaskCard(task, (a) => this.onClick(a), (a) => this.onDelete(a));
    this.cards.set(alias, card);
    this.container.appendChild(card.element);
  }

  _showEmpty(show) {
    if (this.emptyState) {
      this.emptyState.style.display = show ? 'flex' : 'none';
    }
  }
}
