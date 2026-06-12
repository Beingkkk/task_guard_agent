/**
 * TaskGuard Electron Main Process
 * Relates-to: FR-4
 *
 * Responsibilities:
 * 1. Spawn Python backend subprocess
 * 2. Wait for backend readiness
 * 3. Create BrowserWindow and load renderer
 * 4. Manage system tray (minimize to tray)
 * 5. Proxy HTTP requests and WebSocket messages via IPC
 */

const { app, BrowserWindow, Tray, Menu, ipcMain, shell, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

// ── Configuration ───────────────────────────────────────────────────────────
const API_HOST = '127.0.0.1';
const API_PORT = 18990;
const API_BASE = `http://${API_HOST}:${API_PORT}`;
const BACKEND_READY_TIMEOUT_MS = 30000;
const BACKEND_READY_POLL_MS = 500;

// ── Global State ────────────────────────────────────────────────────────────
let mainWindow = null;
let tray = null;
let pythonProcess = null;
let wsClient = null;

function getIsDev() {
  return !app.isPackaged || process.argv.includes('--dev');
}

// ── Python Backend Lifecycle ────────────────────────────────────────────────

function startPythonBackend() {
  return new Promise((resolve, reject) => {
    let pythonPath;
    let args;
    let cwd;

    if (getIsDev()) {
      // Development: run from SourceCode/ directory using project venv
      const sourceCodeDir = path.join(__dirname, '..');
      const venvPython = path.join(
        sourceCodeDir,
        'python-runtime',
        process.platform === 'win32' ? 'Scripts' : 'bin',
        process.platform === 'win32' ? 'python.exe' : 'python'
      );
      pythonPath = venvPython;
      args = ['-m', 'taskguard.api.server'];
      cwd = sourceCodeDir;
    } else {
      // Production: bundled executable
      pythonPath = path.join(process.resourcesPath, 'backend', 'taskguard-backend.exe');
      args = [];
      cwd = path.dirname(pythonPath);
    }

    console.log(`[Backend] Starting: ${pythonPath} ${args.join(' ')} (cwd: ${cwd})`);

    pythonProcess = spawn(pythonPath, args, {
      cwd,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });

    pythonProcess.stdout.on('data', (data) => {
      console.log(`[Backend stdout] ${data.toString().trim()}`);
    });

    pythonProcess.stderr.on('data', (data) => {
      console.error(`[Backend stderr] ${data.toString().trim()}`);
    });

    pythonProcess.on('error', (err) => {
      reject(new Error(`Failed to start backend: ${err.message}`));
    });

    pythonProcess.on('exit', (code) => {
      console.log(`[Backend] Exited with code ${code}`);
      if (wsClient) {
        wsClient.close();
        wsClient = null;
      }
    });

    // Wait for backend to be ready
    const startTime = Date.now();
    const checkReady = () => {
      const req = http.get(`${API_BASE}/api/tasks`, (res) => {
        if (res.statusCode === 200) {
          console.log('[Backend] Ready');
          resolve();
        } else {
          retry();
        }
      });
      req.on('error', retry);
      req.setTimeout(BACKEND_READY_POLL_MS, () => {
        req.destroy();
        retry();
      });

      function retry() {
        if (Date.now() - startTime > BACKEND_READY_TIMEOUT_MS) {
          reject(new Error('Backend failed to start within timeout'));
          return;
        }
        setTimeout(checkReady, BACKEND_READY_POLL_MS);
      }
    };

    // Give backend a moment before first poll
    setTimeout(checkReady, 1000);
  });
}

function stopPythonBackend() {
  if (pythonProcess && !pythonProcess.killed) {
    console.log('[Backend] Stopping...');
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', pythonProcess.pid, '/f', '/t']);
    } else {
      pythonProcess.kill('SIGTERM');
    }
  }
}

// ── WebSocket Client (in main process) ──────────────────────────────────────

function connectWebSocket() {
  const wsUrl = `ws://${API_HOST}:${API_PORT}/ws`;
  const WebSocket = require('ws');

  function doConnect() {
    wsClient = new WebSocket(wsUrl);

    wsClient.on('open', () => {
      console.log('[WS] Connected');
      if (mainWindow) {
        mainWindow.webContents.send('ws:connected');
      }
    });

    wsClient.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString());
        if (mainWindow) {
          mainWindow.webContents.send('ws:message', msg);
        }
      } catch (e) {
        console.error('[WS] Parse error:', e.message);
      }
    });

    wsClient.on('close', () => {
      console.log('[WS] Disconnected, reconnecting in 3s...');
      if (mainWindow) {
        mainWindow.webContents.send('ws:disconnected');
      }
      setTimeout(doConnect, 3000);
    });

    wsClient.on('error', (err) => {
      console.error('[WS] Error:', err.message);
    });
  }

  doConnect();
}

// ── IPC Handlers ────────────────────────────────────────────────────────────

/**
 * Window controls from custom titlebar.
 */
ipcMain.handle('window:minimize', () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.handle('window:maximize', () => {
  if (!mainWindow) return;
  if (mainWindow.isMaximized()) {
    mainWindow.unmaximize();
  } else {
    mainWindow.maximize();
  }
});

ipcMain.handle('window:close', () => {
  if (mainWindow) {
    mainWindow.hide();
  }
});

ipcMain.on('window:listen-maximize', (event) => {
  if (!mainWindow) return;
  const send = () => event.sender.send('window:maximize-change', mainWindow.isMaximized());
  mainWindow.on('maximize', send);
  mainWindow.on('unmaximize', send);
});

/**
 * Open a file or directory with the system's default application.
 * renderer: window.electronAPI.shellOpenPath(path)
 */
ipcMain.handle('shell:open-path', async (_event, filePath) => {
  if (!filePath) return { ok: false, error: 'No path provided' };
  try {
    const result = await shell.openPath(filePath);
    // shell.openPath returns empty string on success, error message on failure
    if (result) {
      return { ok: false, error: result };
    }
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

/**
 * Get the application path for default directory selection.
 * renderer: window.electronAPI.getAppPath()
 */
ipcMain.handle('app:get-path', () => {
  return app.getAppPath();
});

/**
 * Show system file/directory open dialog.
 * renderer: window.electronAPI.showOpenDialog(options)
 */
ipcMain.handle('dialog:show-open', async (_event, options) => {
  if (!mainWindow) return { canceled: true, filePaths: [] };
  const result = await dialog.showOpenDialog(mainWindow, options);
  return result;
});

/**
 * Proxy HTTP requests from renderer to Python backend.
 * renderer: window.electronAPI.invoke('api:request', { method, path, body })
 * main:     makes HTTP request, returns JSON
 */
ipcMain.handle('api:request', async (_event, { method, path, body }) => {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: API_HOST,
      port: API_PORT,
      path,
      method: method || 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 10000, // 10s timeout for backend API requests
    };

    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          resolve({ status: res.statusCode, data: json });
        } catch {
          resolve({ status: res.statusCode, data: data || null });
        }
      });
    });

    req.on('error', (err) => reject(err));
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });

    if (body) {
      req.write(JSON.stringify(body));
    }
    req.end();
  });
});

// ── Window Management ───────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: '智能任务监视',
    frame: false,
    icon: path.join(__dirname, 'assets', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  // Start maximized by default
  mainWindow.maximize();

  if (getIsDev()) {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on('close', (event) => {
    if (!app.isQuiting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

/**
 * Show/restore the main window from the tray.
 * Recreates the window if it has been destroyed.
 */
function showMainWindow() {
  if (!mainWindow) {
    createWindow();
    return;
  }
  if (mainWindow.isMinimized()) {
    mainWindow.restore();
  }
  if (!mainWindow.isVisible()) {
    mainWindow.show();
  }
  mainWindow.focus();
}

/**
 * Toggle the main window visibility from the tray.
 * Shows/restores when hidden or minimized, hides when visible.
 */
function toggleMainWindow() {
  if (!mainWindow || mainWindow.isMinimized() || !mainWindow.isVisible()) {
    showMainWindow();
  } else {
    mainWindow.hide();
  }
}

// ── Tray ────────────────────────────────────────────────────────────────────

function createTray() {
  const iconPath = path.join(__dirname, 'assets', 'tray-icon.png');
  tray = new Tray(iconPath);

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '显示窗口',
      click: () => {
        showMainWindow();
      },
    },
    {
      label: '退出',
      click: () => {
        app.isQuiting = true;
        app.quit();
      },
    },
  ]);

  tray.setToolTip('TaskGuard');
  tray.setContextMenu(contextMenu);

  tray.on('click', () => {
    toggleMainWindow();
  });

  tray.on('double-click', () => {
    toggleMainWindow();
  });
}

// ── App Lifecycle ───────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  let backendReady = false;
  try {
    await startPythonBackend();
    backendReady = true;
  } catch (err) {
    console.error('[App] Backend startup failed:', err.message);
  }

  createWindow();

  if (backendReady) {
    createTray();
    connectWebSocket();
  } else if (mainWindow) {
    // Show error in renderer even if backend failed
    mainWindow.webContents.once('dom-ready', () => {
      mainWindow.webContents.send('backend:error', 'Python 后端启动失败，请检查配置');
    });
  }
});

app.on('window-all-closed', () => {
  // Keep backend running when window is hidden (tray mode)
});

app.on('before-quit', () => {
  app.isQuiting = true;
});

app.on('will-quit', () => {
  stopPythonBackend();
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  } else {
    mainWindow.show();
  }
});
