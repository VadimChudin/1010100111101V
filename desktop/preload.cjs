const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('agentRoom', {
  status: () => ipcRenderer.invoke('desktop:status'),
  beginAuthorization: () => ipcRenderer.invoke('desktop:begin-authorization'),
  reopenAuthorization: () => ipcRenderer.invoke('desktop:reopen-authorization'),
  authorizationStatus: () => ipcRenderer.invoke('desktop:authorization-status'),
  claimAuthorization: () => ipcRenderer.invoke('desktop:claim-authorization'),
  chooseWorkspace: () => ipcRenderer.invoke('desktop:choose-workspace'),
  listGitHubRepositories: () => ipcRenderer.invoke('desktop:list-github-repositories'),
  chooseCloneDestination: () => ipcRenderer.invoke('desktop:choose-clone-destination'),
  cloneGitHubRepository: (payload) => ipcRenderer.invoke('desktop:clone-github-repository', payload),
  installAndPair: (payload) => ipcRenderer.invoke('desktop:install-and-pair', payload),
  runtimeStatus: () => ipcRenderer.invoke('desktop:runtime-status'),
  repairRuntime: (component) => ipcRenderer.invoke('desktop:repair-runtime', { component }),
  openWorkspace: () => ipcRenderer.invoke('desktop:open-workspace'),
  openDiagnostics: () => ipcRenderer.invoke('desktop:open-diagnostics'),
})
