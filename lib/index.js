// harmonyos-dev-mcp-for-dsh: DeepSeek Harness plugin that bridges the
// Python `harmonyos_dev_mcp` MCP server into DSH.
//
// What it does
// ------------
// 1. At activation it resolves a Python runtime that can run the bundled
//    server (bundled .venv -> `uv run` project env -> system python) and
//    spawns it over MCP stdio immediately (synchronous part of apply).
// 2. As soon as `tools/list` answers, the 18 tools are registered on
//    ctx.tools as `mcp__harmonyos__<tool>` using an embedded, dependency-free
//    MCP stdio client (newline-delimited JSON-RPC). A small supervisor
//    restarts a crashed server with bounded exponential backoff and
//    re-syncs the tool generation.
//
// Design rules
// ------------
// - ZERO npm dependencies (matches the dsh-plugin ecosystem norm): only
//   node builtins and the host services `ctx.tools` / `ctx.systemPrompt`.
//   Depending on @deepseek-ai/* packages locally shadows the harness
//   installation with a second copy of the service modules, which breaks
//   symbol-keyed host services (e.g. the tool scheduler).
// - Never throw from apply(): a failing runtime must not break profile boot.
//   Failures degrade to a loud log line plus a systemPrompt section that
//   tells the model/user exactly how to fix the environment.
// - Fast activation: no separate probe before registration; a failed server
//   surfaces through the connect error plus its stderr tail.
// - The Python source is vendored in this package (src/, pyproject.toml,
//   uv.lock); nothing is fetched at runtime when a venv/cache exists.

import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import os from 'node:os'

export const name = 'harmonyos-dev-mcp-for-dsh'

// Declared services. Cordis throws when a non-injected service is touched via
// ctx.<name>, so tools and systemPrompt must be listed here (logger, effect
// and plugin are core context capabilities and need no injection).
export const inject = ['tools', 'systemPrompt']

// Package root: this file lives at <pkg>/lib/index.js.
const PACKAGE_DIR = fileURLToPath(new URL('..', import.meta.url))

const IMPORT_PROBE = 'import harmonyos_dev_mcp, sys; print(harmonyos_dev_mcp.__version__, file=sys.stdout)'
const DEFAULT_SERVER_NAME = 'harmonyos'
const DEFAULT_TOOL_CALL_TIMEOUT_MS = 300000 // build_app is long-running
const DEFAULT_CONNECT_TIMEOUT_MS = 120000 // cold uv sync first-run budget
const RESTART_MAX_ATTEMPTS = 5
const RESTART_INITIAL_DELAY_MS = 500
const RESTART_MAX_DELAY_MS = 30000
const NAME_PREFIX = 'mcp__'
const NAME_LIMIT = 64

function venvPythonPath(dir) {
  const root = join(dir, '.venv')
  return process.platform === 'win32'
    ? join(root, 'Scripts', 'python.exe')
    : join(root, 'bin', 'python')
}

/** Default location for the shared project environment created by `uv run`. */
export function defaultEnvDir() {
  const dshHome = process.env.DSH_HOME || join(os.homedir(), '.dsh')
  return join(dshHome, 'plugin-envs', 'harmonyos-dev-mcp')
}

function normConfig(raw) {
  const config = raw || {}
  const pythonPath = typeof config.pythonPath === 'string' && config.pythonPath.trim()
    ? config.pythonPath.trim()
    : undefined
  const uvPath = typeof config.uvPath === 'string' && config.uvPath.trim()
    ? config.uvPath.trim()
    : undefined
  const useUv = config.useUv !== false
  const serverName = typeof config.serverName === 'string' && config.serverName.trim()
    ? config.serverName.trim()
    : DEFAULT_SERVER_NAME
  const toolCallTimeoutMs = Number.isFinite(config.toolCallTimeoutMs) && config.toolCallTimeoutMs > 0
    ? Math.round(config.toolCallTimeoutMs)
    : DEFAULT_TOOL_CALL_TIMEOUT_MS
  const connectTimeoutMs = Number.isFinite(config.connectTimeoutMs) && config.connectTimeoutMs > 0
    ? Math.round(config.connectTimeoutMs)
    : DEFAULT_CONNECT_TIMEOUT_MS
  const env = config.env && typeof config.env === 'object' && !Array.isArray(config.env)
    ? { ...config.env }
    : {}
  const envDir = typeof config.envDir === 'string' && config.envDir.trim()
    ? config.envDir.trim()
    : defaultEnvDir()
  return { pythonPath, uvPath, useUv, serverName, toolCallTimeoutMs, connectTimeoutMs, env, envDir }
}

/**
 * Resolve the spawn spec for the Python MCP server.
 *
 * Resolution order:
 *   1. `config.pythonPath` (explicit, trusted as-is)
 *   2. bundled `.venv` next to this package (dev checkouts, `uv sync`)
 *   3. `uv run --project <package>` with UV_PROJECT_ENVIRONMENT pinned to a
 *      DSH-managed directory (keeps the pnpm store read-only and clean)
 *   4. system `python`/`python3` (assumes `pip install harmonyos-dev-mcp`)
 *
 * Returns `{ command, mcpArgs, probeArgs, env, cwd, kind }` or `null` when
 * nothing usable is found.
 */
export function resolvePythonSpec(rawConfig) {
  const cfg = normConfig(rawConfig)
  const mcpArgs = ['-m', 'harmonyos_dev_mcp']
  const probeArgs = ['-c', IMPORT_PROBE]
  const env = { ...cfg.env }

  if (cfg.pythonPath) {
    return { command: cfg.pythonPath, mcpArgs, probeArgs, env, cwd: PACKAGE_DIR, kind: 'explicit' }
  }

  const bundled = venvPythonPath(PACKAGE_DIR)
  if (existsSync(bundled)) {
    return { command: bundled, mcpArgs, probeArgs, env, cwd: PACKAGE_DIR, kind: 'venv' }
  }

  if (cfg.useUv) {
    const uv = cfg.uvPath || 'uv'
    env.UV_PROJECT_ENVIRONMENT = cfg.envDir
    return {
      command: uv,
      mcpArgs: ['run', '--project', PACKAGE_DIR, 'python', ...mcpArgs],
      probeArgs: ['run', '--project', PACKAGE_DIR, 'python', ...probeArgs],
      env,
      cwd: PACKAGE_DIR,
      kind: 'uv',
    }
  }

  const fallback = process.platform === 'win32' ? 'python' : 'python3'
  return { command: fallback, mcpArgs, probeArgs, env, cwd: PACKAGE_DIR, kind: 'system' }
}

/** Run one probe of the interpreter importing the Python package. */
export function probePythonSpec(spec, timeoutMs) {
  return new Promise((resolve) => {
    let settled = false
    const child = spawn(spec.command, spec.probeArgs, {
      cwd: spec.cwd,
      env: { ...process.env, ...spec.env },
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    })
    let out = ''
    let err = ''
    child.stdout.on('data', (chunk) => {
      out += chunk.toString()
    })
    child.stderr.on('data', (chunk) => {
      err += chunk.toString()
    })
    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      child.kill()
      resolve({ ok: false, timedOut: true, stdout: out, stderr: err })
    }, timeoutMs)
    child.on('error', (error) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve({ ok: false, error: String(error && error.message || error), stdout: out, stderr: err })
    })
    child.on('close', (code) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve({ ok: code === 0, exitCode: code, stdout: out, stderr: err })
    })
  })
}

/**
 * Minimal MCP stdio client (newline-delimited JSON-RPC 2.0), shared with
 * bin/check.js so the diagnostics path exercises the same code as the plugin.
 */
export class McpStdioClient {
  constructor(command, args, opts) {
    this.command = command
    this.args = args
    this.opts = opts
    this.child = null
    this.buffer = ''
    this.pending = new Map()
    this.nextId = 1
    this.closed = false
    this.stderrTail = ''
    this.onLog = null
    this.onExit = null
  }

  spawnProcess() {
    const { command, args, opts } = this
    const child = spawn(command, args, {
      cwd: opts.cwd,
      env: { ...process.env, ...(opts.env || {}) },
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    })
    this.child = child
    this.buffer = ''
    this.closed = false
    child.stderr.on('data', (chunk) => {
      const text = chunk.toString()
      this.stderrTail = (this.stderrTail + text).slice(-4000)
      if (this.onLog) this.onLog(text)
    })
    child.stdout.on('data', (chunk) => this._onData(chunk.toString()))
    child.on('close', () => {
      this.closed = true
      for (const { reject, timer } of this.pending.values()) {
        clearTimeout(timer)
        reject(new Error('MCP server exited'))
      }
      this.pending.clear()
      if (this.onExit) this.onExit()
    })
    child.on('error', (error) => {
      this.closed = true
      for (const { reject, timer } of this.pending.values()) {
        clearTimeout(timer)
        reject(error)
      }
      this.pending.clear()
      if (this.onExit) this.onExit()
    })
  }

  _onData(text) {
    this.buffer += text
    let idx
    while ((idx = this.buffer.indexOf('\n')) >= 0) {
      const line = this.buffer.slice(0, idx).trim()
      this.buffer = this.buffer.slice(idx + 1)
      if (!line) continue
      let msg
      try {
        msg = JSON.parse(line)
      } catch {
        continue
      }
      if (msg.id !== undefined && this.pending.has(msg.id)) {
        const { resolve, reject, timer } = this.pending.get(msg.id)
        this.pending.delete(msg.id)
        clearTimeout(timer)
        if (msg.error) reject(new Error(JSON.stringify(msg.error)))
        else resolve(msg.result)
      }
    }
  }

  request(method, params, opts) {
    if (this.closed || !this.child) return Promise.reject(new Error('MCP server not running'))
    const id = this.nextId++
    const payload = JSON.stringify({ jsonrpc: '2.0', id, method, params })
    return new Promise((resolve, reject) => {
      let timer = null
      const cancel = (why) => {
        this.pending.delete(id)
        clearTimeout(timer)
        reject(new Error(why))
      }
      if (opts && opts.signal) {
        const onAbort = () => cancel('tool call aborted')
        if (opts.signal.aborted) {
          cancel('tool call aborted')
          return
        }
        opts.signal.addEventListener('abort', onAbort, { once: true })
      }
      if (opts && opts.timeoutMs) {
        timer = setTimeout(() => cancel(`tool call timed out after ${opts.timeoutMs}ms`), opts.timeoutMs)
      }
      this.pending.set(id, { resolve, reject, timer })
      try {
        this.child.stdin.write(payload + '\n')
      } catch (error) {
        this.pending.delete(id)
        clearTimeout(timer)
        reject(error)
      }
    })
  }

  notify(method, params) {
    try {
      if (this.child) this.child.stdin.write(JSON.stringify({ jsonrpc: '2.0', method, params }) + '\n')
    } catch { /* ignore */ }
  }

  kill() {
    this.closed = true
    for (const { reject, timer } of this.pending.values()) {
      clearTimeout(timer)
      reject(new Error('MCP server shutting down'))
    }
    this.pending.clear()
    try {
      this.notify('notifications/exit', {})
    } catch { /* ignore */ }
    const child = this.child
    if (child) {
      setTimeout(() => {
        try {
          child.kill()
        } catch { /* ignore */ }
      }, 300)
    }
  }
}

/** Derive the model-facing tool name: mcp__<server>__<raw>, deterministic. */
export function publicName(serverName, rawName) {
  const base = NAME_PREFIX + serverName + '__' + rawName
  const clean = base.replace(/[^A-Za-z0-9_-]/g, '_')
  return clean.length <= NAME_LIMIT && clean === base ? clean : clean.slice(0, NAME_LIMIT)
}

/** Connect and fetch the server's tool list. */
export async function connectSync(client, timeoutMs) {
  const init = await client.request('initialize', {
    protocolVersion: '2025-03-26',
    capabilities: {},
    clientInfo: { name: 'harmonyos-dev-mcp-for-dsh', version: '0.1.0' },
  }, { timeoutMs })
  client.notify('notifications/initialized', {})
  const list = await client.request('tools/list', {}, { timeoutMs })
  return { serverInfo: init.serverInfo, tools: list.tools || [] }
}

/** Call one server tool and normalize the raw MCP result. */
export async function callServerTool(client, rawName, args, opts) {
  const result = await client.request('tools/call', { name: rawName, arguments: args }, opts)
  const blocks = result.content || []
  const text = blocks
    .filter((block) => block.type === 'text')
    .map((block) => block.text || '')
    .join('\n')
  return {
    text,
    structured: result.structuredContent || null,
    isError: result.isError === true,
  }
}

/** Human-readable startup failure guidance for the model/user. */
function failureSection(cfg, message, hints) {
  return [`HarmonyOS MCP tools (${publicName(cfg.serverName, '...')}) are NOT available: ${message}`, ...hints].join('\n')
}

/**
 * Sanitize an MCP tool inputSchema into the harness-supported JSON schema
 * subset (type/oneOf/properties/required/additionalProperties/items/enum/const
 * + title/description). FastMCP schemas carry vocabulary ($schema, anyOf,
 * format, numeric bounds, defaults...) that ctx.tools.register rejects, so we
 * strip unsupported keywords and fall back to a permissive object when a node
 * cannot be represented. Parameter validation stays permissive; the Python
 * server re-validates arguments and returns structured errors.
 */
export function sanitizeParameters(schema) {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema)) {
    return { type: 'object', additionalProperties: true }
  }
  const out = {}
  if (typeof schema.type === 'string') out.type = schema.type
  else if (Array.isArray(schema.type)) {
    const concrete = schema.type.filter((t) => t !== 'null')
    out.type = concrete.length === 1 ? concrete[0] : 'object'
  }
  if (Array.isArray(schema.oneOf) && schema.oneOf.length > 0) {
    out.oneOf = schema.oneOf.map((node) => sanitizeParameters(node))
  }
  // anyOf/allOf (e.g. Optional[str] -> [string, null], Union[str, int]) are not
  // in the harness subset, but they carry real type information:
  //   - one non-null branch   -> adopt its full sanitized shape (keeps items/enum)
  //   - several distinct types -> advertise oneOf of the sanitized branches
  // otherwise the fallback below would advertise an over-broad object.
  if (!out.type && !out.oneOf) {
    const branches = Array.isArray(schema.anyOf) && schema.anyOf.length > 0
      ? schema.anyOf
      : Array.isArray(schema.allOf) && schema.allOf.length > 0
        ? schema.allOf
        : null
    if (branches) {
      const concrete = branches.filter((b) => b && typeof b === 'object' && b.type !== 'null')
      const types = []
      for (const branch of concrete) {
        if (typeof branch.type === 'string') types.push(branch.type)
        else if (Array.isArray(branch.type)) {
          for (const t of branch.type) if (t !== 'null') types.push(t)
        }
      }
      const unique = [...new Set(types)]
      if (unique.length === 1 && concrete.length === 1) {
        Object.assign(out, sanitizeParameters(concrete[0]))
      } else if (unique.length === 1) {
        out.type = unique[0]
      } else if (concrete.length > 0) {
        out.oneOf = concrete.map((branch) => sanitizeParameters(branch))
      }
    }
  }
  if (schema.properties && typeof schema.properties === 'object' && !Array.isArray(schema.properties)) {
    out.properties = {}
    for (const key of Object.keys(schema.properties)) {
      out.properties[key] = sanitizeParameters(schema.properties[key])
    }
  }
  if (Array.isArray(schema.required)) {
    const names = schema.required.filter((name) => typeof name === 'string')
    if (names.length > 0) out.required = names
  }
  if (schema.items && typeof schema.items === 'object' && !Array.isArray(schema.items)) {
    out.items = sanitizeParameters(schema.items)
  }
  if (Array.isArray(schema.enum)) out.enum = schema.enum
  if (Object.hasOwn(schema, 'const')) out.const = schema.const
  if (typeof schema.title === 'string') out.title = schema.title
  if (typeof schema.description === 'string') out.description = schema.description

  if (!out.type && !out.oneOf) {
    out.type = out.items ? 'array' : 'object'
  }
  if (out.type === 'object' && !('additionalProperties' in out)) {
    out.additionalProperties = true
  }
  return out
}

/**
 * Register the server's tools on ctx.tools. `getClient` returns the current
 * live client so executions always talk to the latest supervised server.
 */
function registerTools(ctx, cfg, tools, getClient) {
  const disposers = []
  for (const tool of tools) {
    const name = publicName(cfg.serverName, tool.name)
    if (!tool.name || /[^A-Za-z0-9_-]/.test(tool.name)) {
      ctx.logger?.warn?.(`[harmonyos-dev-mcp] skipping tool with invalid name: ${String(tool.name)}`)
      continue
    }
    const parameters = sanitizeParameters(tool.inputSchema)
    const description = tool.description
      ? `${name} — ${tool.description}`
      : name
    try {
      const disposer = ctx.tools.register({
        name,
        description,
        parameters,
        output: {
          schema: { type: 'object', additionalProperties: true },
          render: (_args, value) => {
            const text = value && value.isError
              ? `${name}: ${value.text || 'error'}`
              : `${name}: ${(value && value.text) || 'ok'}`
            return [{ type: 'text', text }]
          },
        },
        isConcurrencySafe: () => true,
        timeoutMs: cfg.toolCallTimeoutMs,
        execute: async (args, exec) => {
          const client = getClient()
          if (!client) throw new Error(`${name}: MCP server not running`)
          const value = await callServerTool(client, tool.name, args || {}, {
            signal: exec.signal,
            timeoutMs: cfg.toolCallTimeoutMs,
          })
          if (value.isError) {
            const error = new Error(`${name}: ${value.text || 'tool call failed'}`)
            error.code = 'MCP_TOOL_ERROR'
            throw error
          }
          return value
        },
      })
      disposers.push(() => disposer())
    } catch (error) {
      ctx.logger?.error?.(`[harmonyos-dev-mcp] failed to register tool ${name}: ${error && error.message || error}`)
    }
  }
  return disposers
}

export function apply(ctx, rawConfig) {
  const cfg = normConfig(rawConfig)

  // Supervisor layout: shared by every server generation; disposal is wired
  // through ctx.effect so stop/reload cleans the child process and tools.
  const layout = { client: null, disposers: [], stopped: false, restartAttempts: 0, restartTimer: null }
  const layoutCleanup = () => {
    layout.stopped = true
    if (layout.restartTimer) {
      clearTimeout(layout.restartTimer)
      layout.restartTimer = null
    }
    for (const dispose of layout.disposers) {
      try {
        dispose()
      } catch { /* ignore */ }
    }
    layout.disposers = []
    if (layout.client) {
      try {
        layout.client.kill()
      } catch { /* ignore */ }
      layout.client = null
    }
  }
  ctx.effect(() => {
    return () => layoutCleanup()
  }, 'harmonyos-dev-mcp')

  ctx.logger?.info?.('[harmonyos-dev-mcp] activating (serverName=%s)', cfg.serverName)

  // Everything below is best-effort: the outer try/catch guarantees that no
  // async failure can ever reject apply() and break profile boot.
  const boot = async () => {
    let spec
    try {
      spec = resolvePythonSpec(cfg)
    } catch (error) {
      failModule(ctx, cfg, `python runtime resolution failed: ${error && error.message || error}`, [
        'Fix: install uv (https://docs.astral.sh/uv/) or set `pythonPath` in the harmonyos-dev-mcp plugin config.',
      ])
      return
    }
    if (!spec) {
      failModule(ctx, cfg, 'no usable python runtime found', [
        'Fix: install uv and restart the profile; uv will provision the bundled server automatically.',
      ])
      return
    }

    ctx.logger?.info?.('[harmonyos-dev-mcp] starting server (kind=%s command=%s)', spec.kind, spec.command)

    const startServer = () => {
      const client = new McpStdioClient(spec.command, spec.mcpArgs, { cwd: spec.cwd, env: spec.env })
      client.onLog = (text) => ctx.logger?.debug?.('[harmonyos-dev-mcp] server: %s', text.trim().split('\n')[0] || '')
      client.onExit = () => {
        if (layout.stopped) return
        ctx.logger?.warn?.('[harmonyos-dev-mcp] server exited unexpectedly, supervising restart')
        scheduleRestart()
      }
      layout.client = client
      client.spawnProcess()
      return client
    }

    const scheduleRestart = () => {
      if (layout.stopped) return
      if (layout.restartAttempts >= RESTART_MAX_ATTEMPTS) {
        ctx.logger?.error?.('[harmonyos-dev-mcp] giving up after %d restart attempts; run bin/check.js to diagnose', layout.restartAttempts)
        layoutCleanup()
        return
      }
      const delay = Math.min(RESTART_INITIAL_DELAY_MS * 2 ** layout.restartAttempts, RESTART_MAX_DELAY_MS)
      layout.restartAttempts += 1
      ctx.logger?.info?.('[harmonyos-dev-mcp] restart attempt %d in %dms', layout.restartAttempts, delay)
      layout.restartTimer = setTimeout(async () => {
        layout.restartTimer = null
        if (layout.stopped) return
        try {
          await layoutConnect()
        } catch (error) {
          ctx.logger?.error?.('[harmonyos-dev-mcp] restart %d failed: %s', layout.restartAttempts, error && error.message || error)
          scheduleRestart()
        }
      }, delay)
    }

    const layoutConnect = async () => {
      const client = startServer()
      const { serverInfo, tools } = await connectSync(client, cfg.connectTimeoutMs)
      ctx.logger?.info?.('[harmonyos-dev-mcp] connected to %s (%s): %d tools', serverInfo.name || 'server', spec.kind, tools.length)
      const newDisposers = registerTools(ctx, cfg, tools, () => layout.client)
      for (const dispose of layout.disposers) {
        try {
          dispose()
        } catch { /* ignore */ }
      }
      layout.disposers = newDisposers
      layout.restartAttempts = 0
      ctx.logger?.info?.('[harmonyos-dev-mcp] %d tools exposed as %s*', tools.length, publicName(cfg.serverName, ''))
    }

    try {
      await layoutConnect()
    } catch (error) {
      ctx.logger?.error?.('[harmonyos-dev-mcp] initial connect failed: %s', error && error.message || error)
      if (layout.client && layout.client.stderrTail) {
        ctx.logger?.error?.('[harmonyos-dev-mcp] server stderr tail: %s', layout.client.stderrTail.slice(-1200))
      }
      failModule(ctx, cfg, `server start failed: ${error && error.message || error}`, [
        'Fix: run `uv sync --frozen` in the plugin package directory, verify `hdc`/DevEco are installed, or set a working pythonPath; then restart the profile. Diagnostics: run `node bin/check.js` in the plugin package.',
      ])
      return
    }

    try {
      ctx.systemPrompt?.section?.({
        name: 'tool:harmonyos-dev-mcp',
        order: 95,
        text:
          `HarmonyOS device tools are available as ${publicName(cfg.serverName, '')}* (list_devices, build_app, install_app, ` +
          'run_app, uninstall_app, screenshot, click, input_text, press_key, find_elements, get_ui_tree, list_windows, ' +
          'wait_for_element, logs_query, query_package, swipe, drag, long_press). Target a real device via device_id ' +
          '(hdc list targets) or the HARMONYOS_HDC_SERVER wireless endpoint.',
      })
    } catch { /* teardown may deactivate the context; section is best-effort */ }
  }

  return (async () => {
    try {
      await boot()
    } catch (error) {
      const detail = error && error.message || error
      console.error(`[harmonyos-dev-mcp] unexpected activation error: ${detail}`)
      try {
        ctx.logger?.error?.(`[harmonyos-dev-mcp] unexpected activation error: ${detail}`)
      } catch { /* ignore */ }
    }
  })()
}

function failModule(ctx, cfg, message, hints) {
  // Never let diagnostics escape: at teardown, section()/logger on a
  // deactivating context throw, and that must not turn into a load failure.
  try {
    ctx.logger?.error?.(`[harmonyos-dev-mcp] ${message}`)
  } catch { /* ignore */ }
  try {
    ctx.systemPrompt?.section?.({
      name: 'tool:harmonyos-dev-mcp',
      order: 95,
      text: failureSection(cfg, message, hints),
    })
  } catch (error) {
    console.error(`[harmonyos-dev-mcp] ${message}`)
    const detail = error && error.message || error
    if (detail !== message) console.error(`[harmonyos-dev-mcp] (diagnostics also failed: ${detail})`)
  }
}