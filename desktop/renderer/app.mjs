const panels = {
  intro: document.querySelector('#intro-panel'),
  authorizing: document.querySelector('#authorizing-panel'),
  source: document.querySelector('#source-panel'),
  setup: document.querySelector('#setup-panel'),
  ready: document.querySelector('#ready-panel'),
}
const connectButton = document.querySelector('#connect-button')
const retryBrowserButton = document.querySelector('#retry-browser-button')
const localSourceButton = document.querySelector('#local-source-button')
const githubSourceButton = document.querySelector('#github-source-button')
const localSourceSection = document.querySelector('#local-source-section')
const githubSourceSection = document.querySelector('#github-source-section')
const chooseWorkspaceButton = document.querySelector('#choose-workspace-button')
const localWorkspacePath = document.querySelector('#local-workspace-path')
const refreshRepositoriesButton = document.querySelector('#refresh-repositories-button')
const repositoryList = document.querySelector('#repository-list')
const chooseCloneDestinationButton = document.querySelector('#choose-clone-destination-button')
const cloneDestination = document.querySelector('#clone-destination')
const cloneRepositoryButton = document.querySelector('#clone-repository-button')
const githubSourceNote = document.querySelector('#github-source-note')
const reconnectGitHubButton = document.querySelector('#reconnect-github-button')
const sourceNote = document.querySelector('#source-note')
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
let selectedRepository = null
let selectedCloneDestination = ''
let repositories = []
let sourceMode = 'local'
let authorizationPoll = null
let refreshRepositoriesAfterAuthorization = false

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

function setSourceMode(mode, loadRepositories = true) {
  sourceMode = mode
  const local = mode === 'local'
  localSourceButton.classList.toggle('active', local)
  githubSourceButton.classList.toggle('active', !local)
  localSourceSection.classList.toggle('hidden', !local)
  githubSourceSection.classList.toggle('hidden', local)
  sourceNote.textContent = local
    ? 'Select a local Git project to prepare this computer.'
    : 'Choose a repository, then select an empty local destination for its clone.'
  if (!local && loadRepositories && repositories.length === 0) loadGitHubRepositories()
}

function continueToSetup(workspace, sourceDetail) {
  selectedWorkspace = workspace
  workspacePath.value = workspace
  installButton.disabled = false
  setSetupNote(`${sourceDetail} Ready to install the loopback-only local runtime and pair this computer.`)
  showPanel('setup')
}

function renderRepositories() {
  repositoryList.replaceChildren()
  if (repositories.length === 0) {
    const message = document.createElement('p')
    message.className = 'repository-empty'
    message.textContent = 'No repositories were returned for this GitHub account.'
    repositoryList.append(message)
    return
  }
  for (const repository of repositories) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'repository-row'
    button.classList.toggle('selected', selectedRepository?.id === repository.id)
    const name = document.createElement('strong')
    name.textContent = repository.full_name
    const meta = document.createElement('span')
    const visibility = repository.private ? 'Private' : 'Public'
    meta.textContent = `${visibility} · ${repository.default_branch || 'default branch'}`
    const description = document.createElement('small')
    description.textContent = repository.description || 'No description'
    button.append(name, meta, description)
    button.addEventListener('click', () => {
      selectedRepository = repository
      renderRepositories()
      updateCloneAction()
      githubSourceNote.textContent = `Selected ${repository.full_name}. Choose an empty folder for the local clone.`
    })
    repositoryList.append(button)
  }
}

function updateCloneAction() {
  cloneRepositoryButton.disabled = !(selectedRepository && selectedCloneDestination)
}

async function loadGitHubRepositories() {
  refreshRepositoriesButton.disabled = true
  githubSourceNote.textContent = 'Loading repositories available to your authorized GitHub account…'
  try {
    repositories = await window.agentRoom.listGitHubRepositories()
    selectedRepository = repositories.find((repository) => repository.id === selectedRepository?.id) || null
    renderRepositories()
    updateCloneAction()
    githubSourceNote.textContent = repositories.length
      ? 'Select a repository. Private and public repositories are shown when your GitHub authorization allows them.'
      : 'No repositories were returned. You can refresh after adjusting GitHub access.'
  } catch (error) {
    repositories = []
    selectedRepository = null
    renderRepositories()
    updateCloneAction()
    const message = String(error?.message || '')
    githubSourceNote.textContent = message.includes('GitHub request failed (409)')
      ? 'Repository access needs a one-time GitHub refresh. Select “Reconnect GitHub” below, approve access in the browser, then this list will reload automatically.'
      : 'Repository list could not be loaded. Select “Reconnect GitHub” below to renew access, then try again.'
  } finally {
    refreshRepositoriesButton.disabled = false
  }
}

async function restoreState() {
  const status = await window.agentRoom.status()
  buildLabel.textContent = `Agent Room Desktop · ${status.version}`
  if (status.workspacePath) {
    selectedWorkspace = status.workspacePath
    workspacePath.value = selectedWorkspace
    localWorkspacePath.value = status.projectSource?.kind === 'local' ? selectedWorkspace : ''
    installButton.disabled = false
  }
  if (status.connected) {
    if (status.workspacePath && status.paired) {
      // Returning users should enter their last paired project immediately.
      // Source selection and setup remain available only when changing project.
      await window.agentRoom.openWorkspace()
      return
    }
    if (status.workspacePath) {
      showPanel('setup')
      setSetupNote(`Connected as ${status.user?.login ?? 'GitHub user'}. Finish pairing this local project once to open it automatically on future launches.`)
    } else {
      showPanel('source')
      sourceNote.textContent = `Connected as ${status.user?.login ?? 'GitHub user'}. Choose the project source for this computer.`
    }
  }
}

async function startAuthorization({ refreshRepositories = false } = {}) {
  refreshRepositoriesAfterAuthorization = refreshRepositories
  connectButton.disabled = true
  reconnectGitHubButton.disabled = true
  try {
    const authorization = await window.agentRoom.beginAuthorization()
    authExpiry.textContent = `Approval expires at ${new Date(authorization.expiresAt).toLocaleTimeString()}.`
    showPanel('authorizing')
    authorizationPoll = window.setInterval(pollAuthorization, 1800)
  } catch (error) {
    connectButton.disabled = false
    reconnectGitHubButton.disabled = false
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
      showPanel('source')
      sourceNote.textContent = `Connected as ${connected.user.login}. Choose the project source for this computer.`
      if (refreshRepositoriesAfterAuthorization) {
        refreshRepositoriesAfterAuthorization = false
        repositories = []
        selectedRepository = null
        setSourceMode('github', false)
        githubSourceNote.textContent = 'GitHub access refreshed. Loading repositories…'
        await loadGitHubRepositories()
      }
      reconnectGitHubButton.disabled = false
      return
    }
    if (result.status === 'expired') {
      window.clearInterval(authorizationPoll)
      authorizationPoll = null
      connectButton.disabled = false
      reconnectGitHubButton.disabled = false
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
  try {
    const folder = await window.agentRoom.chooseWorkspace()
    if (!folder) return
    localWorkspacePath.value = folder
    continueToSetup(folder, 'Local Git project selected.')
  } catch (error) {
    sourceNote.textContent = error.message
  }
}

async function chooseCloneDestination() {
  try {
    const folder = await window.agentRoom.chooseCloneDestination()
    if (!folder) return
    selectedCloneDestination = folder
    cloneDestination.value = folder
    updateCloneAction()
    githubSourceNote.textContent = selectedRepository
      ? `Ready to clone ${selectedRepository.full_name} into the selected empty folder.`
      : 'Choose a repository to continue.'
  } catch (error) {
    githubSourceNote.textContent = error.message
  }
}

async function cloneSelectedRepository() {
  if (!selectedRepository || !selectedCloneDestination) return
  cloneRepositoryButton.disabled = true
  refreshRepositoriesButton.disabled = true
  chooseCloneDestinationButton.disabled = true
  githubSourceNote.textContent = `Cloning ${selectedRepository.full_name}. Private credentials remain inside the desktop main process…`
  try {
    const result = await window.agentRoom.cloneGitHubRepository({
      repositoryId: selectedRepository.id,
      destination: selectedCloneDestination,
    })
    continueToSetup(result.workspacePath, `GitHub repository ${result.repository.fullName} cloned locally.`)
  } catch (error) {
    githubSourceNote.textContent = error.message
    updateCloneAction()
  } finally {
    refreshRepositoriesButton.disabled = false
    chooseCloneDestinationButton.disabled = false
  }
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
localSourceButton.addEventListener('click', () => setSourceMode('local'))
githubSourceButton.addEventListener('click', () => setSourceMode('github'))
chooseWorkspaceButton.addEventListener('click', chooseWorkspace)
refreshRepositoriesButton.addEventListener('click', loadGitHubRepositories)
chooseCloneDestinationButton.addEventListener('click', chooseCloneDestination)
cloneRepositoryButton.addEventListener('click', cloneSelectedRepository)
reconnectGitHubButton.addEventListener('click', () => startAuthorization({ refreshRepositories: true }))
installButton.addEventListener('click', installAndPair)
openWorkspaceButton.addEventListener('click', () => window.agentRoom.openWorkspace())
diagnosticsButton.addEventListener('click', async () => window.agentRoom.openDiagnostics())

restoreState().catch((error) => window.alert(`Could not restore desktop state: ${error.message}`))
