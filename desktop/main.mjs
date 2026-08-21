import { app, BrowserWindow, dialog, ipcMain, Menu, safeStorage, session, shell } from 'electron'
import { execFile, spawn } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { existsSync } from 'node:fs'
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
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
  // `windowsHide` is deliberate: local services are implementation detail, not UI.
  // `unref` lets runtime/Serena survive the setup call without creating a console window.
  const child = spawn(command, args, {
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
    windowsVerbatimArguments: false,
    env: options.env || process.env,
  })
  child.unref()
  return child.pid
}

async function ensureGit() {
  const executable = process.platform === 'win32' ? 'git.exe' : 'git'
  const current = await run(executable, ['--version'], { timeout: 20_000 })
  if (current.ok) return executable
  if (process.platform === 'win32') {
    const install = await run('winget.exe', ['install', '--id', 'Git.Git', '--exact', '--source', 'winget', '--accept-package-agreements', '--accept-source-agreements'], { timeout: 600_000 })
    if (install.ok) {
      const installed = await run(executable, ['--version'], { timeout: 20_000 })
      if (installed.ok) return executable
    }
  }
  throw new Error('Git is required to open a project. Install Git for Windows and restart Agent Room.')
}

async function ensureGitWorkspace(workspacePath) {
  const git = await ensureGit()
  const result = await run(git, ['-C', workspacePath, 'rev-parse', '--is-inside-work-tree'], { timeout: 20_000 })
  if (!result.ok || result.stdout !== 'true') throw new Error('Select a folder that contains a Git project, or choose a GitHub repository to clone.')
  return git
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

async function githubApiRequest(sessionToken, pathname) {
  const response = await fetch(`${API_URL}/v1${pathname}`, {
    headers: { Cookie: `${COOKIE_NAME}=${sessionToken}` },
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`GitHub request failed (${response.status})${detail ? `: ${detail}` : ''}`)
  }
  return response.json()
}

async function createGitAskpass(accessToken) {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'agent-room-git-'))
  const scriptPath = path.join(directory, process.platform === 'win32' ? 'askpass.cmd' : 'askpass.sh')
  const script = process.platform === 'win32'
    ? '@echo off\r\necho %1 | findstr /I "username" >nul\r\nif not errorlevel 1 (echo x-access-token) else (echo %AGENT_ROOM_GIT_TOKEN%)\r\n'
    : '#!/bin/sh\ncase "$1" in *Username*) printf "%s\\n" "x-access-token" ;; *) printf "%s\\n" "$AGENT_ROOM_GIT_TOKEN" ;; esac\n'
  await writeFile(scriptPath, script, { mode: 0o700 })
  return { directory, scriptPath }
}

async function cloneGitHubRepository(sessionToken, repositoryId, destination) {
  if (!repositoryId || !destination) throw new Error('A repository and an empty destination folder are required.')
  const entries = await readdir(destination)
  if (entries.length > 0) throw new Error('Choose an empty folder for the repository clone.')
  const source = await githubApiRequest(sessionToken, `/auth/github/repositories/${encodeURIComponent(repositoryId)}/clone-source`)
  const git = await ensureGit()
  const askpass = await createGitAskpass(source.access_token)
  const cloneEnvironment = {
    ...process.env,
    GIT_ASKPASS: askpass.scriptPath,
    AGENT_ROOM_GIT_TOKEN: source.access_token,
    GIT_TERMINAL_PROMPT: '0',
  }
  try {
    const result = await run(git, ['clone', '--origin', 'origin', '--', source.clone_url, destination], { env: cloneEnvironment, timeout: 900_000 })
    if (!result.ok) throw new Error(`Repository clone failed: ${result.stderr || result.stdout || 'Git returned a non-zero exit code'}`)
  } finally {
    delete cloneEnvironment.AGENT_ROOM_GIT_TOKEN
    await rm(askpass.directory, { recursive: true, force: true })
  }
  return { workspacePath: destination, repository: { id: source.id, fullName: source.full_name } }
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
    // The remote Agent Room frontend must use the same persistent Electron
    // session that receives the Cloud HttpOnly cookie after browser OAuth.
    // Without this explicit partition, the token was saved successfully but
    // loaded in a different renderer session, producing Chat 401 responses.
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), partition: 'persist:agent-room', contextIsolation: true, nodeIntegration: false, sandbox: true },
  })
  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'))
  if (process.env.AGENT_ROOM_SMOKE_BRIDGE === '1') {
    mainWindow.webContents.once('did-finish-load', async () => {
      try {
        const bridgeReady = await mainWindow.webContents.executeJavaScript("typeof window.agentRoom === 'object' && typeof window.agentRoom.beginAuthorization === 'function'")
        if (!bridgeReady) throw new Error('renderer preload bridge is unavailable')
        console.log('AGENT_ROOM_BRIDGE_OK')
        app.exit(0)
      } catch (error) {
        console.error(`AGENT_ROOM_BRIDGE_FAILED: ${error.message}`)
        app.exit(1)
      }
    })
  }
}

function openWorkspaceInMainWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    createMainWindow()
  }
  mainWindow.maximize()
  mainWindow.loadURL(FRONTEND_URL)
}

ipcMain.handle('desktop:status', async () => {
  const state = await readState()
  // Migration for users paired before pairedWorkspacePath was introduced:
  // a verified runtime config plus a saved workspace is proof of completed setup.
  const paired = Boolean(
    (state.pairedWorkspacePath && state.pairedWorkspacePath === state.workspacePath)
    || (state.workspacePath && existsSync(runtimePaths().config)),
  )
  if (paired && state.workspacePath && state.pairedWorkspacePath !== state.workspacePath) {
    await patchState({ pairedWorkspacePath: state.workspacePath })
  }
  return { connected: Boolean(state.sessionToken), paired, user: state.user || null, workspacePath: state.workspacePath || '', projectSource: state.projectSource || null, version: app.getVersion() }
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
  await ensureGitWorkspace(workspacePath)
  await patchState({ workspacePath, projectSource: { kind: 'local' } })
  return workspacePath
})

ipcMain.handle('desktop:list-github-repositories', async () => {
  const state = await readState()
  if (!state.sessionToken) throw new Error('Browser authorization is required before loading GitHub repositories')
  return githubApiRequest(state.sessionToken, '/auth/github/repositories')
})

ipcMain.handle('desktop:choose-clone-destination', async () => {
  const selection = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory', 'createDirectory'],
    title: 'Choose an empty destination folder for the repository clone',
  })
  if (selection.canceled || !selection.filePaths[0]) return null
  const destination = selection.filePaths[0]
  const entries = await readdir(destination)
  if (entries.length > 0) throw new Error('Choose an empty folder for the repository clone.')
  return destination
})

ipcMain.handle('desktop:clone-github-repository', async (_event, payload) => {
  const state = await readState()
  if (!state.sessionToken) throw new Error('Browser authorization is required before cloning a repository')
  const result = await cloneGitHubRepository(state.sessionToken, payload?.repositoryId, payload?.destination)
  await patchState({
    workspacePath: result.workspacePath,
    projectSource: { kind: 'github', repositoryId: result.repository.id, repositoryFullName: result.repository.fullName },
  })
  return result
})

ipcMain.handle('desktop:install-and-pair', async (_event, payload) => {
  const state = await readState()
  if (!state.sessionToken) throw new Error('Browser authorization is required before pairing this computer')
  const workspacePath = state.workspacePath
  if (!workspacePath || payload?.workspacePath !== workspacePath) throw new Error('Choose a workspace using the native source chooser before installation')
  await ensureGitWorkspace(workspacePath)
  const paths = await bootstrapRuntime()
  const deviceName = `Agent Room Desktop · ${os.hostname()}`
  const init = await run(paths.binary, ['init', '--cloud-url', API_URL, '--project-id', 'default', '--workspace-root', workspacePath, '--state-dir', path.dirname(paths.config), '--device-name', deviceName])
  if (!init.ok) throw new Error(`Runtime configuration failed: ${init.stderr || init.stdout}`)
  const pairing = await requestPairing(state.sessionToken)
  const registration = await run(paths.binary, ['register', '--config', paths.config, '--pairing-token', pairing.pairing_token])
  if (!registration.ok) throw new Error(`Device registration failed: ${registration.stderr || registration.stdout}`)
  startDetached(paths.binary, ['serve', '--config', paths.config, '--auto-update'])
  const [serena, graphiti] = await Promise.all([configureSerena(paths, workspacePath), configureGraphiti()])
  await patchState({ pairedWorkspacePath: workspacePath, pairedAt: new Date().toISOString() })
  return { runtime: 'Registered and synchronizing with verified auto-update.', serena, graphiti }
})

ipcMain.handle('desktop:open-workspace', () => openWorkspaceInMainWindow())
ipcMain.handle('desktop:open-diagnostics', async () => shell.openPath(runtimeHome()))

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null)
  DESKTOP_SESSION = session.fromPartition('persist:agent-room')
  const state = await readState()
  if (state.sessionToken) await setSessionCookie(state.sessionToken)
  await createMainWindow()
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createMainWindow() })
})

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
