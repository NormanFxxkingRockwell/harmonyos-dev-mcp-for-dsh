#!/usr/bin/env node
// Best-effort Python environment warm-up, run by pnpm during
// `dsh plugin --profile <name> add <this-package>` (npm lifecycle "prepare").
//
// It never fails the install: if uv is missing or sync fails, the plugin falls
// back to resolving a runtime at activation time (`uv run` will then provision
// the project environment on first use, or a preinstalled `harmonyos-dev-mcp`
// is used as a last resort).
const { spawnSync } = require('node:child_process')
const { existsSync } = require('node:fs')
const { join } = require('node:path')

const PACKAGE_DIR = join(__dirname, '..')

function has(cmd) {
  const probe = spawnSync(process.platform === 'win32' ? 'where' : 'which', [cmd], {
    stdio: 'ignore',
    windowsHide: true,
  })
  return probe.status === 0
}

console.log('[harmonyos-dev-mcp-for-dsh] prepare: warming Python environment (best effort)')
if (!has('uv')) {
  console.log('[harmonyos-dev-mcp-for-dsh] prepare: uv not found, skipping warm-up (runtime will provision on demand)')
  process.exit(0)
}

const result = spawnSync('uv', ['sync', '--frozen'], {
  cwd: PACKAGE_DIR,
  stdio: 'inherit',
  windowsHide: true,
  env: { ...process.env },
})

if (result.status === 0) {
  console.log('[harmonyos-dev-mcp-for-dsh] prepare: uv sync ok')
} else {
  // A stale lockfile is common in git checkouts; retry without --frozen.
  console.log('[harmonyos-dev-mcp-for-dsh] prepare: frozen sync failed (status %s), retrying unfrozen', result.status)
  spawnSync('uv', ['sync'], { cwd: PACKAGE_DIR, stdio: 'inherit', windowsHide: true })
  console.log('[harmonyos-dev-mcp-for-dsh] prepare: done (best effort)')
}
process.exit(0)