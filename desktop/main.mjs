import { app, BrowserWindow, dialog, ipcMain, safeStorage, session, shell } from 'electron'
import { execFile, spawn } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { existsSync } from 'node:fs'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'

const executeFile = promisify(execFile)
const __dirname = path.dirname(fileURLToPath(import.meta.url))
const API_URL = (process.env.AGENT_ROOM_API_URL || 'https://app-production-cc16.up.railway.app').replace(/\/$/, '')
const FRONTEND_URL = process.env.AGENT_ROOM_FRONTEND_URL || 'https://frontend-swart-alpha-20.vercel.app'
const COOKIE_NAME = process.env.AGENT_ROOM_SESSION_COOKIE || 'agent_platform_session'
let DESKTOP_SESSION = null
let mainWindow = null
let workspaceWindow = null

function statePath() {
  return path.join(app.getPath('userData'), 'desktop-secrets.bin')
}

async function readState() {
  try {
    const payload = await readFile(statePath())
    if (!safeStorage.isEncryptionAvailable()) throw new Error('Operating-system credential encryption is unavailable')
    return JSON.parse(safeStorage.decryptString(payload))
  } catch (error) {
    if (error?.code === 'ENOENT') return {}
    throw error
  }
}

async function writeState(state) {
  if (!safeStorage.isEncryptionAvailable()) throw new Error('Operating-system credential encryption is unavailable')
  await mkdir(path.dirname(statePath()), { recursive: true })
  await writeFile(statePath(), safeStorage.encryptString(JSON.stringify(state)), { mode: 0o600 })
}

async function patchState(patch) {
  const next = { ...(await readState()), ...patch }
  await writeState(next)
  return next
}

function runtimeHome() {
  return process.env.AGENT_ROOM_HOME || path.join(app.getPath('home'), '.agent-room')
}

function runtimePaths() {
  const home = runtimeHome()
  const isWindows = process.platform === 'win32'
  return {
    home,
    config: path.join(home, 'default', 'runtime.json'),
    binary: isWindows ? path.join(home, 'venv', 'Scripts', 'agent-room-runtime.exe') : path.join(home, 'venv', 'bin', 'agent-room-runtime'),
    python: isWindows ? path.join(home, 'venv', 'Scripts', 'python.exe') : path.join(home, 'venv', 'bin', 'python'),
    uv: isWindows ? path.join(home, 'venv', 'Scripts', 'uv.exe') : path.join(home, 'venv', 'bin', 'uv'),
  }
}

function installerPath() {
  const root = app.isPackaged ? path.join(process.resourcesPath, 'runtime-installer') : path.join(__dirname, '..', 'local-runtime', 'installer')
  return process.platform === 'win32' ? path.join(root, 'install.ps1') : path.join(root, 'install.sh')
}

function graphitiComposePath() {
  return app.isPackaged ? path.join(process.resourcesPath, 'compose.graphiti.yml') : path.join(__dirname, '..', 'local-runtime', 'compose.graphiti.yml')
}

async function run(command, args, options = {}) {
  try {
    const result = await executeFile(command, args, { windowsHide: true, timeout: options.timeout || 300_000, env: options.env || process.env })
    return { ok: true, stdout: result.stdout.trim(), stderr: result.stderr.trim() }
  } catch (error) {
    return { ok: false, stdout: error.stdout?.trim() || '', stderr: error.stderr?.trim() || error.message }
  }
}

function startDetached(command, args, options = {}) {
  const child = spawn(command, args, { detached: true, stdio: 'ignore', windowsHide: true, env: options.env || process.env })
  child.unref()
  return child.pid
}

async function bootstrapRuntime() {
  const paths = runtimePaths()
  if (existsSync(paths.binary)) return paths
  const environment = { ...process.env, AGENT_ROOM_HOME: paths.home }
  const result = process.platform === 'win32'
    ? await run('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', installerPath()], { env: environment, timeout: 600_000 })
    : await run('bash', [installerPath()], { env: environment, timeout: 600_000 })
  if (!result.ok || !existsSync(paths.binary)) {
    throw new Error(`Verified runtime installation failed: ${result.stderr || result.stdout || 'runtime executable was not created'}`)
  }
  return paths
}

async function requestPairing(sessionToken) {
  const response = await fetch(`${API_URL}/v1/projects/default/devices/pair`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Cookie: `${COOKIE_NAME}=${sessionToken}` },
    body: JSON.stringify({ name_hint: `Agent Room Desktop · ${os.hostname()}`, expires_in_seconds: 600 }),
  })
  if (!response.ok) throw new Error(`Cloud pairing request failed (${response.status})`)
  return response.json()
}

async function configureSerena(paths, workspacePath) {
  const uvInstall = await run(paths.python, ['-m', 'pip', 'install', '--disable-pip-version-check', '--upgrade', 'uv'], { timeout: 300_000 })
  if (!uvInstall.ok) return { ready: false, detail: `Could not install the Serena package manager: ${uvInstall.stderr || uvInstall.stdout}` }
  const install = await run(paths.uv, ['tool', 'install', '-p', '3.13', 'serena-agent'], { timeout: 600_000 })
  if (!install.ok) return { ready: false, detail: `Serena package install failed: ${install.stderr || install.stdout}` }
  const init = await run(paths.uv, ['tool', 'run', '--from', 'serena-agent', 'serena', 'init'], { timeout: 300_000 })
  if (!init.ok) return { ready: false, detail: `Serena initialization needs attention: ${init.stderr || init.stdout}` }
  startDetached(paths.uv, ['tool', 'run', '--from', 'serena-agent', 'serena', 'start-mcp-server', '--transport', 'streamable-http', '--host', '127.0.0.1', '--port', '9121', '--project', workspacePath, '--open-web-dashboard', 'false'])
  return { ready: true, detail: 'Installed and running with the language-server backend on loopback; Agent Room exposes read-only tools only.' }
}

async function configureGraphiti() {
  const docker = await run(process.platform === 'win32' ? 'docker.exe' : 'docker', ['info'], { timeout: 20_000 })
  if (!docker.ok) return { ready: false, detail: 'Docker is not running. The local Graphiti profile is deferred; cloud provenance envelopes continue to synchronize.' }
  const graphitiDir = path.join(runtimeHome(), 'graphiti')
  await mkdir(graphitiDir, { recursive: true })
  const envFile = path.join(graphitiDir, '.env')
  if (!existsSync(envFile)) await writeFile(envFile, `NEO4J_PASSWORD=${randomBytes(24).toString('base64url')}\n`, { mode: 0o600 })
  const result = await run(process.platform === 'win32' ? 'docker.exe' : 'docker', ['compose', '--env-file', envFile, '-f', graphitiComposePath(), 'up', '-d'], { timeout: 300_000 })
  return result.ok ? { ready: true, detail: 'Local Neo4j memory profile is running on loopback only.' } : { ready: false, detail: `Graphiti profile could not start: ${result.stderr || result.stdout}` }
}

async function setSessionCookie(token) {
  if (!DESKTOP_SESSION) throw new Error('Desktop browser session is not ready')
  await DESKTOP_SESSION.cookies.set({
    url: API_URL,
    name: COOKIE_NAME,
    value: token,
    httpOnly: true,
    secure: API_URL.startsWith('https://'),
    sameSite: 'no_restriction',
    expirationDate: Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 7,
    path: '/',
  })
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 900,
    height: 760,
    minWidth: 650,
    minHeight: 600,
    backgroundColor: '#090d14',
    title: 'Agent Room',
    webPreferences: { preload: path.join(__dirname, 'preload.mjs'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  })
  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'))
}

function createWorkspaceWindow() {
  if (workspaceWindow && !workspaceWindow.isDestroyed()) {
    workspaceWindow.show()
    workspaceWindow.focus()
    return
  }
  workspaceWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 900,
    minHeight: 640,
    backgroundColor: '#080c11',
    title: 'Agent Room · Workspace',
    webPreferences: { partition: 'persist:agent-room', contextIsolation: true, nodeIntegration: false, sandbox: true },
  })
  workspaceWindow.loadURL(FRONTEND_URL)
  workspaceWindow.on('closed', () => { workspaceWindow = null })
}

ipcMain.handle('desktop:status', async () => {
  const state = await readState()
  return { connected: Boolean(state.sessionToken), user: state.user || null, workspacePath: state.workspacePath || '', version: app.getVersion() }
})

ipcMain.handle('desktop:begin-authorization', async () => {
  const response = await fetch(`${API_URL}/v1/auth/desktop/start`, { method: 'POST' })
  if (!response.ok) throw new Error(`Cloud authorization request failed (${response.status})`)
  const payload = await response.json()
  await patchState({ pendingAuthorization: { requestId: payload.request_id, requestSecret: payload.request_secret, authorizeUrl: payload.authorize_url, expiresAt: payload.expires_at } })
  await shell.openExternal(payload.authorize_url)
  return { expiresAt: payload.expires_at }
})

ipcMain.handle('desktop:reopen-authorization', async () => {
  const state = await readState()
  if (!state.pendingAuthorization?.authorizeUrl) throw new Error('There is no pending browser authorization')
  await shell.openExternal(state.pendingAuthorization.authorizeUrl)
})

ipcMain.handle('desktop:authorization-status', async () => {
  const state = await readState()
  const pending = state.pendingAuthorization
  if (!pending) throw new Error('There is no pending browser authorization')
  const response = await fetch(`${API_URL}/v1/auth/desktop/${pending.requestId}`, { headers: { 'X-Desktop-Authorization': pending.requestSecret } })
  if (!response.ok) throw new Error(`Authorization check failed (${response.status})`)
  return response.json()
})

ipcMain.handle('desktop:claim-authorization', async () => {
  const state = await readState()
  const pending = state.pendingAuthorization
  if (!pending) throw new Error('There is no pending browser authorization')
  const response = await fetch(`${API_URL}/v1/auth/desktop/${pending.requestId}/claim`, { method: 'POST', headers: { 'X-Desktop-Authorization': pending.requestSecret } })
  if (!response.ok) throw new Error(`Authorization completion failed (${response.status})`)
  const payload = await response.json()
  await setSessionCookie(payload.session_token)
  await patchState({ sessionToken: payload.session_token, user: payload.user, pendingAuthorization: null })
  return { user: payload.user }
})

ipcMain.handle('desktop:choose-workspace', async () => {
  const selection = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory'], title: 'Select a local Git workspace' })
  if (selection.canceled || !selection.filePaths[0]) return null
  const workspacePath = selection.filePaths[0]
  await patchState({ workspacePath })
  return workspacePath
})

ipcMain.handle('desktop:install-and-pair', async (_event, payload) => {
  const state = await readState()
  if (!state.sessionToken) throw new Error('Browser authorization is required before pairing this computer')
  const workspacePath = state.workspacePath
  if (!workspacePath || payload?.workspacePath !== workspacePath) throw new Error('Choose a workspace using the native folder picker before installation')
  const paths = await bootstrapRuntime()
  const deviceName = `Agent Room Desktop · ${os.hostname()}`
  const init = await run(paths.binary, ['init', '--cloud-url', API_URL, '--project-id', 'default', '--workspace-root', workspacePath, '--state-dir', path.dirname(paths.config), '--device-name', deviceName])
  if (!init.ok) throw new Error(`Runtime configuration failed: ${init.stderr || init.stdout}`)
  const pairing = await requestPairing(state.sessionToken)
  const registration = await run(paths.binary, ['register', '--config', paths.config, '--pairing-token', pairing.pairing_token])
  if (!registration.ok) throw new Error(`Device registration failed: ${registration.stderr || registration.stdout}`)
  startDetached(paths.binary, ['serve', '--config', paths.config, '--auto-update'])
  const [serena, graphiti] = await Promise.all([configureSerena(paths, workspacePath), configureGraphiti()])
  return { runtime: 'Registered and synchronizing with verified auto-update.', serena, graphiti }
})

ipcMain.handle('desktop:open-workspace', () => createWorkspaceWindow())
ipcMain.handle('desktop:open-diagnostics', async () => shell.openPath(runtimeHome()))

app.whenReady().then(async () => {
  DESKTOP_SESSION = session.fromPartition('persist:agent-room')
  await createMainWindow()
  const state = await readState()
  if (state.sessionToken) await setSessionCookie(state.sessionToken)
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createMainWindow() })
})

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
