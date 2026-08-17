#!/usr/bin/env node
// harmonyos-dev-mcp-for-dsh diagnostics / acceptance script.
//
// Usage:
//   node bin/check.js                # resolve runtime, probe, MCP handshake, tools/list
//   node bin/check.js --device       # also run list_devices / query_package / logs_query against hdc targets
//   node bin/check.js --verbose      # trace every JSON-RPC frame
//
// Uses the exact same runtime resolution and MCP stdio client as the plugin
// (lib/index.js), so a passing check predicts a working plugin activation.

import { McpStdioClient, resolvePythonSpec, probePythonSpec, connectSync, callServerTool } from '../lib/index.js'

const VERBOSE = process.argv.includes('--verbose')
const WITH_DEVICE = process.argv.includes('--device')
const log = (...args) => { if (VERBOSE) console.log('[check]', ...args) }

function summarize(call) {
  if (!call || !call.structured) return '(no envelope)'
  const sc = call.structured
  const payload = sc.result || {}
  const ok = sc.ok === true
  const head = {}
  for (const key of Object.keys(payload || {})) {
    const value = payload[key]
    if (typeof value === 'object' && value !== null) {
      const size = Array.isArray(value) ? value.length : Object.keys(value).length
      head[key] = `${Array.isArray(value) ? 'array' : 'object'}[${size}]`
    } else {
      head[key] = value
    }
  }
  return `${ok ? 'ok' : 'ERROR'} ${sc.error ? JSON.stringify(sc.error) : ''} ${JSON.stringify(head).slice(0, 400)}`
}

async function main() {
  console.log('=== harmonyos-dev-mcp-for-dsh check ===')
  console.log('node    :', process.version, process.platform, process.arch)
  console.log('dsh_home:', process.env.DSH_HOME || '(unset -> default)')

  const spec = resolvePythonSpec({})
  if (!spec) {
    console.error('ERROR: no python runtime could be resolved. Install uv or set plugin config pythonPath.')
    process.exit(1)
  }
  console.log('[runtime] resolved spec:', JSON.stringify({ command: spec.command, kind: spec.kind, env: spec.env }, null, 2).slice(0, 800))

  const probe = await probePythonSpec(spec, 240000)
  console.log('[runtime] probe import:', probe.ok ? `ok (harmonyos_dev_mcp ${(probe.stdout || '').trim() || '?'})` : `FAILED (${probe.stderr.trim() || probe.error})`)
  if (!probe.ok) {
    console.error('ERROR: bundled server cannot start. Run `uv sync --frozen` in the plugin directory first.')
    process.exit(1)
  }

  console.log('\n[mcp] spawning server:', spec.command, spec.mcpArgs.join(' '))
  const client = new McpStdioClient(spec.command, spec.mcpArgs, { cwd: spec.cwd, env: spec.env })
  if (VERBOSE) client.onLog = (text) => log('server stderr:', text.trim().split('\n').slice(0, 3).join(' | '))
  client.spawnProcess()
  try {
    const { serverInfo, tools } = await connectSync(client, 120000)
    console.log('[mcp] initialized:', JSON.stringify({ server: serverInfo, protocolVersion: '2025-03-26' }))
    console.log(`[mcp] tools/list: ${tools.length} tools`)
    for (const tool of tools) console.log('   -', tool.name)

    if (WITH_DEVICE) {
      console.log('\n[device] list_devices')
      const devices = await callServerTool(client, 'list_devices', {})
      console.log('  ', devices.text)
      const list = devices.structured?.result?.devices || []
      const deviceId = list[0]?.device_id
      if (!deviceId) {
        console.log('[device] no device returned; skipping device calls')
      } else {
        console.log(`[device] using device_id=${deviceId}`)

        console.log('\n[device] query_package (info_type=list)')
        const pkgs = await callServerTool(client, 'query_package', { device_id: deviceId, info_type: 'list' })
        console.log('  ', summarize({ structured: pkgs.structured }))

        console.log('\n[device] logs_query (mode=errors, lines=20)')
        const logs = await callServerTool(client, 'logs_query', { device_id: deviceId, mode: 'errors', lines: 20 })
        console.log('  ', summarize({ structured: logs.structured }))

        console.log('\n[device] get_ui_tree')
        const tree = await callServerTool(client, 'get_ui_tree', { device_id: deviceId })
        console.log('  ', summarize({ structured: tree.structured }))
      }
    }

    console.log('\n=== check finished ===')
    client.notify('notifications/exit', {})
    client.kill()
  } catch (error) {
    console.error('\nERROR during MCP session:', error.message)
    if (client.stderrTail) console.error('server stderr tail:\n' + client.stderrTail.slice(-1500))
    client.kill()
    process.exit(1)
  }
}

main().catch((error) => {
  console.error('FATAL:', error)
  process.exit(1)
})