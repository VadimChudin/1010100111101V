const panels = {
  intro: document.querySelector('#intro-panel'),
  authorizing: document.querySelector('#authorizing-panel'),
  setup: document.querySelector('#setup-panel'),
  ready: document.querySelector('#ready-panel'),
}
const connectButton = document.querySelector('#connect-button')
const retryBrowserButton = document.querySelector('#retry-browser-button')
const chooseWorkspaceButton = document.querySelector('#choose-workspace-button')
const installButton = document.querySelector('#install-button')
const openWorkspaceButton = document.querySelector('#open-workspace-button')
const diagnosticsButton = document.querySelector('#diagnostics-button')
const workspacePath = document.querySelector('#workspace-path')
const setupNote = document.querySelector('#setup-note')
const authExpiry = document.querySelector('#auth-expiry')
const readyDetail = document.querySelector('#ready-detail')
const readyWorkspace = document.querySelector('#ready-workspace')
const buildLabel = document.querySelector('#build-label')

let selectedWorkspace = ''
let authorizationPoll = null

function showPanel(name) {
  Object.entries(panels).forEach(([key, panel]) => panel.classList.toggle('hidden', key !== name))
}

function setComponent(component, state, detail) {
  const marker = document.querySelector(`#${component}-status`)
  const description = document.querySelector(`#${component}-detail`)
  marker.className = `status ${state}`
  if (detail) description.textContent = detail
}

function setSetupNote(text) {
  setupNote.textContent = text
}

async function restoreState() {
  const status = await window.agentRoom.status()
  buildLabel.textContent = `Agent Room Desktop · ${status.version}`
  if (status.workspacePath) {
    selectedWorkspace = status.workspacePath
    workspacePath.value = selectedWorkspace
    installButton.disabled = false
  }
  if (status.connected) {
    showPanel('setup')
    setSetupNote(`Connected as ${status.user?.login ?? 'GitHub user'}. Select the repository stored on this computer.`)
  }
}

async function startAuthorization() {
  connectButton.disabled = true
  try {
    const authorization = await window.agentRoom.beginAuthorization()
    authExpiry.textContent = `Approval expires at ${new Date(authorization.expiresAt).toLocaleTimeString()}.`
    showPanel('authorizing')
    authorizationPoll = window.setInterval(pollAuthorization, 1800)
  } catch (error) {
    connectButton.disabled = false
    window.alert(`Could not start browser authorization: ${error.message}`)
  }
}

async function pollAuthorization() {
  try {
    const result = await window.agentRoom.authorizationStatus()
    if (result.status === 'completed') {
      window.clearInterval(authorizationPoll)
      authorizationPoll = null
      const connected = await window.agentRoom.claimAuthorization()
      showPanel('setup')
      setSetupNote(`Connected as ${connected.user.login}. Select the repository stored on this computer.`)
      return
    }
    if (result.status === 'expired') {
      window.clearInterval(authorizationPoll)
      authorizationPoll = null
      connectButton.disabled = false
      showPanel('intro')
      window.alert('Browser authorization expired. Please try again.')
    }
  } catch (error) {
    window.clearInterval(authorizationPoll)
    authorizationPoll = null
    connectButton.disabled = false
    showPanel('intro')
    window.alert(`Authorization check failed: ${error.message}`)
  }
}

async function chooseWorkspace() {
  const folder = await window.agentRoom.chooseWorkspace()
  if (!folder) return
  selectedWorkspace = folder
  workspacePath.value = folder
  installButton.disabled = false
  setSetupNote('Ready. Installation creates only outbound local synchronization and a loopback-only Serena endpoint.')
}

async function installAndPair() {
  if (!selectedWorkspace) return
  installButton.disabled = true
  setComponent('runtime', 'working', 'Installing verified local runtime…')
  setComponent('serena', 'idle', 'Waiting for runtime registration')
  setComponent('graphiti', 'idle', 'Will use the local Docker profile if Docker is available')
  setSetupNote('This may take several minutes the first time. You can keep this window open.')
  try {
    const result = await window.agentRoom.installAndPair({ workspacePath: selectedWorkspace })
    setComponent('runtime', 'running', result.runtime)
    setComponent('serena', result.serena.ready ? 'running' : 'warning', result.serena.detail)
    setComponent('graphiti', result.graphiti.ready ? 'running' : 'warning', result.graphiti.detail)
    readyWorkspace.textContent = selectedWorkspace.split(/[\\/]/).filter(Boolean).pop() || 'Selected'
    readyDetail.textContent = result.graphiti.ready
      ? 'The runtime, Serena semantic index and local Graphiti memory profile are running. Open the same secure Agent Room control surface used in the browser.'
      : 'The runtime and Serena are running. Graphiti will activate automatically when Docker is available; its durable provenance envelopes are already synchronized.'
    showPanel('ready')
  } catch (error) {
    installButton.disabled = false
    setComponent('runtime', 'warning', 'Setup did not complete')
    setSetupNote(error.message)
  }
}

connectButton.addEventListener('click', startAuthorization)
retryBrowserButton.addEventListener('click', () => window.agentRoom.reopenAuthorization())
chooseWorkspaceButton.addEventListener('click', chooseWorkspace)
installButton.addEventListener('click', installAndPair)
openWorkspaceButton.addEventListener('click', () => window.agentRoom.openWorkspace())
diagnosticsButton.addEventListener('click', async () => window.agentRoom.openDiagnostics())

restoreState().catch((error) => window.alert(`Could not restore desktop state: ${error.message}`))
