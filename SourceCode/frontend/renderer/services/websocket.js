/**
 * WebSocket Service (Renderer-side)
 * Relates-to: FR-4
 *
 * Wraps Electron IPC WebSocket events from the main process.
 * Provides a simple event-driven API for components.
 */

class WsService {
  constructor() {
    this._listeners = {};
    this._connected = false;
    this._setupIPC();
  }

  _setupIPC() {
    if (typeof window.electronAPI === 'undefined') {
      console.warn('[WS] electronAPI not available — running in browser?');
      return;
    }

    window.electronAPI.onWsConnected(() => {
      this._connected = true;
      this._emit('connected');
      console.log('[WS] Connected');
    });

    window.electronAPI.onWsDisconnected(() => {
      this._connected = false;
      this._emit('disconnected');
      console.log('[WS] Disconnected');
    });

    window.electronAPI.onWsMessage((msg) => {
      this._emit('message', msg);
      // Also emit by event type for convenience
      if (msg.type) {
        this._emit(msg.type, msg.data);
      }
    });
  }

  on(event, callback) {
    if (!this._listeners[event]) {
      this._listeners[event] = [];
    }
    this._listeners[event].push(callback);
    return () => this.off(event, callback);
  }

  off(event, callback) {
    if (!this._listeners[event]) return;
    this._listeners[event] = this._listeners[event].filter((cb) => cb !== callback);
  }

  _emit(event, data) {
    if (!this._listeners[event]) return;
    this._listeners[event].forEach((cb) => {
      try {
        cb(data);
      } catch (err) {
        console.error('[WS] Listener error:', err);
      }
    });
  }

  get connected() {
    return this._connected;
  }
}

// Singleton instance
const wsService = new WsService();
