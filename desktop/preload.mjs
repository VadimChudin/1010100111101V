import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('agentRoom', {
  status: () => ipcRenderer.invoke('desktop:status'),
  beginAuthorization: () => ipcRenderer.invoke('desktop:begin-authorization'),
  reopenAuthorization: () => ipcRenderer.invoke('desktop:reopen-authorization'),
  authorizationStatus: () => ipcRenderer.invoke('desktop:authorization-status'),
  claimAuthorization: () => ipcRenderer.invoke('desktop:claim-authorization'),
  chooseWorkspace: () => ipcRenderer.invoke('desktop:choose-workspace'),
  installAndPair: (payload) => ipcRenderer.invoke('desktop:install-and-pair', payload),
  openWorkspace: () => ipcRenderer.invoke('desktop:open-workspace'),
  openDiagnostics: () => ipcRenderer.invoke('desktop:open-diagnostics'),
})
