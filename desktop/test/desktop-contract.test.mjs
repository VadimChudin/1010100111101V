import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

async function source(name) {
  return readFile(path.join(root, name), 'utf8')
}

test('desktop renderer remains isolated from Node and credentials', async () => {
  const main = await source('main.mjs')
  const preload = await source('preload.cjs')
  assert.match(main, /contextIsolation: true/)
  assert.match(main, /nodeIntegration: false/)
  assert.match(main, /safeStorage\.encryptString/)
  assert.match(main, /X-Desktop-Authorization/)
  assert.match(preload, /contextBridge\.exposeInMainWorld\('agentRoom'/)
  assert.match(preload, /beginAuthorization/)
  assert.match(preload, /listGitHubRepositories/)
  assert.match(preload, /chooseCloneDestination/)
  assert.match(preload, /cloneGitHubRepository/)
  assert.doesNotMatch(preload, /sessionToken|requestSecret|access_token|GIT_ASKPASS|execFile|spawn/)
})

test('desktop GitHub clone flow validates server source and uses an ephemeral askpass credential boundary', async () => {
  const main = await source('main.mjs')
  assert.match(main, /desktop:list-github-repositories/)
  assert.match(main, /desktop:clone-github-repository/)
  assert.match(main, /clone-source/)
  assert.match(main, /GIT_ASKPASS/)
  assert.match(main, /GIT_TERMINAL_PROMPT: '0'/)
  assert.match(main, /readdir\(destination\)/)
  assert.match(main, /rm\(askpass\.directory/)
})

test('repository access recovery guides a legacy desktop authorization through one-time reconnect and automatic reload', async () => {
  const renderer = await source('renderer/app.mjs')
  const markup = await source('renderer/index.html')
  assert.match(markup, /Reconnect GitHub and load repositories/)
  assert.match(renderer, /refreshRepositoriesAfterAuthorization/)
  assert.match(renderer, /GitHub request failed \(409\)/)
  assert.match(renderer, /await loadGitHubRepositories\(\)/)
  assert.match(renderer, /startAuthorization\(\{ refreshRepositories: true \}\)/)
})

test('desktop component commands retain local-only Serena boundary and verified runtime bootstrap', async () => {
  const main = await source('main.mjs')
  assert.match(main, /installerPath\(\)/)
  assert.match(main, /--host', '127\.0\.0\.1'/)
  assert.match(main, /--auto-update/)
  assert.match(main, /'docker', \['compose'/)
  assert.match(main, /shell\.openExternal/)
})


test('desktop Cloud cookie and remote workspace share one persistent Electron session', async () => {
  const main = await source('main.mjs')
  assert.match(main, /session\.fromPartition\('persist:agent-room'\)/)
  assert.match(main, /partition: 'persist:agent-room'/)
  assert.match(main, /sameSite: 'no_restriction'/)
  assert.match(main, /await setSessionCookie\(state\.sessionToken\)/)
})

test('desktop reopens a successfully paired workspace rather than returning to setup', async () => {
  const main = await source('main.mjs')
  const renderer = await source('renderer/app.mjs')
  assert.match(main, /pairedWorkspacePath/)
  assert.match(main, /existsSync\(runtimePaths\(\)\.config\)/)
  assert.match(renderer, /status\.workspacePath && status\.paired/)
  assert.match(renderer, /await window\.agentRoom\.openWorkspace\(\)/)
})
