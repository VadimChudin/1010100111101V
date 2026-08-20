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
  const preload = await source('preload.mjs')
  assert.match(main, /contextIsolation: true/)
  assert.match(main, /nodeIntegration: false/)
  assert.match(main, /safeStorage\.encryptString/)
  assert.match(main, /X-Desktop-Authorization/)
  assert.doesNotMatch(preload, /sessionToken|requestSecret|execFile|spawn/)
})

test('desktop component commands retain local-only Serena boundary and verified runtime bootstrap', async () => {
  const main = await source('main.mjs')
  assert.match(main, /installerPath\(\)/)
  assert.match(main, /--host', '127\.0\.0\.1'/)
  assert.match(main, /--auto-update/)
  assert.match(main, /'docker', \['compose'/)
  assert.match(main, /shell\.openExternal/)
})
