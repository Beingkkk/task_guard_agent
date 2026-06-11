/**
 * TaskGuard Preload Script
 * Relates-to: FR-4
 *
 * Exposes a secure API surface to the renderer process via contextBridge.
 * All backend communication goes through the main process.
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // ── HTTP API ──────────────────────────────────────────────────────────────

  /**
   * Make an HTTP request to the Python backend (proxied through main process).
   * @param {{ method: string, path: string, body?: object }} options
   * @returns {Promise<{ status: number, data: object }>}
   */
  invoke: (channel, payload) => ipcRenderer.invoke(channel, payload),

  // Convenience wrappers
  apiGet: (path) => ipcRenderer.invoke('api:request', { method: 'GET', path }),
  apiPost: (path, body) => ipcRenderer.invoke('api:request', { method: 'POST', path, body }),
  apiDelete: (path) => ipcRenderer.invoke('api:request', { method: 'DELETE', path }),
  apiPatch: (path, body) => ipcRenderer.invoke('api:request', { method: 'PATCH', path, body }),

  // ── WebSocket Events ──────────────────────────────────────────────────────

  /**
   * Subscribe to WebSocket messages from the main process.
   * @param {string} event - 'ws:message' | 'ws:connected' | 'ws:disconnected'
   * @param {function} callback
   */
  onWsMessage: (callback) => {
    ipcRenderer.on('ws:message', (_event, msg) => callback(msg));
  },

  onWsConnected: (callback) => {
    ipcRenderer.on('ws:connected', () => callback());
  },

  onWsDisconnected: (callback) => {
    ipcRenderer.on('ws:disconnected', () => callback());
  },

  onBackendError: (callback) => {
    ipcRenderer.on('backend:error', (_event, msg) => callback(msg));
  },

  // ── App Info ──────────────────────────────────────────────────────────────
  getVersion: () => '0.1.0',
  getAppPath: () => ipcRenderer.invoke('app:get-path'),

  // ── Window Controls ───────────────────────────────────────────────────────
  minimizeWindow: () => ipcRenderer.invoke('window:minimize'),
  maximizeWindow: () => ipcRenderer.invoke('window:maximize'),
  closeWindow: () => ipcRenderer.invoke('window:close'),
  onMaximizeChange: (callback) => {
    ipcRenderer.on('window:maximize-change', (_event, isMaximized) => callback(isMaximized));
    ipcRenderer.send('window:listen-maximize');
  },

  // ── Shell Operations ──────────────────────────────────────────────────────
  /** Open a file or directory with the system's default application. */
  shellOpenPath: (filePath) => ipcRenderer.invoke('shell:open-path', filePath),

  // ── File Dialog ────────────────────────────────────────────────────────────
  /**
   * Show a system file/directory open dialog.
   * @param {{ properties: string[], defaultPath?: string, filters?: object[] }} options
   * @returns {Promise<{ canceled: boolean, filePaths: string[] }>}
   */
  showOpenDialog: (options) => ipcRenderer.invoke('dialog:show-open', options),
});
