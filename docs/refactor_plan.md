# HarmonyOS Dev MCP Refactor Plan

This plan tracks the post-0.8.0 technical debt cleanup. Do not change MCP tool
count, tool names, public parameters, or result shape unless a later release
explicitly plans that compatibility break.

## Guardrails

- Keep the MCP tool count at 18.
- Keep existing tool names and capabilities unchanged.
- Keep one focused commit per step.
- Run the acceptance checks for a step before moving to the next step.
- Stop on any failed acceptance check and fix that step before continuing.
- Produce a final refactor report after the planned steps are complete.

## Step 0: Baseline

Goal: verify the flattened repository layout is a clean starting point.

Work:

- Confirm `main` is synchronized with `origin/main`.
- Confirm the working tree has no uncommitted changes.
- Run the baseline checks.

Acceptance:

- `git status -sb` shows `## main...origin/main`.
- `ruff check src tests` passes.
- `pytest tests/unit -q` passes.
- `uv build --out-dir dist --clear` passes.
- A temporary wheel install reports version `0.8.0` and 18 registered tools.

Commit:

- No commit required if this step only verifies the baseline.

## Step 1: Cache And Ignore Cleanup

Goal: remove generated local noise before structural moves.

Work:

- Remove `src/**/__pycache__`.
- Remove `tests/**/__pycache__`.
- Remove `.pytest_cache`.
- Remove `.ruff_cache`.
- Remove old `dist`.
- Ensure `.gitignore` covers these generated paths.

Acceptance:

- No `__pycache__` directories or `*.pyc` files remain under `src` or `tests`.
- `.pytest_cache`, `.ruff_cache`, and `dist` do not exist.
- `pytest tests/unit -q` passes.
- The only tracked change should be ignore/documentation if needed.

Commit:

- `chore: clean generated cache artifacts`

## Step 2: Mirror Unit Test Layout By Domain

Goal: organize tests first so source moves have a clear destination.

Work:

- Move build tests under `tests/unit/build/`.
- Move HDC/device tests under `tests/unit/device/`.
- Move UI and E2E tests under `tests/unit/ui/` or `tests/unit/tools/`.
- Prefer renames only; do not rewrite test behavior unless imports require it.

Acceptance:

- Pytest still collects the same number of tests as the baseline.
- `pytest tests/unit -q` passes.
- `ruff check tests` passes.
- The diff is mostly file renames.

Commit:

- `test: mirror unit test layout by domain`

## Step 3: Move Log Internals To A Logs Package

Goal: keep MCP tool entrypoints in `tools/` and move log domain logic into
`logs/`.

Work:

- Create `src/harmonyos_dev_mcp/logs/`.
- Move `tools/log/parser.py` to `logs/parser.py`.
- Move `tools/log/historian.py` to `logs/historian.py`.
- Move `tools/log/crash_parser.py` to `logs/crash_parser.py`.
- Move `tools/log/time_utils.py` to `logs/time_utils.py`.
- Keep `tools/log/query.py` as the MCP entrypoint for now.
- Update imports.

Acceptance:

- `logs_query` remains exported from the same MCP tool entrypoint.
- No stale imports reference moved log internals.
- `pytest tests/unit -q` passes.
- `ruff check src tests` passes.
- A temporary wheel install still reports 18 registered tools.

Commit:

- `refactor: move log internals to logs package`

## Step 4: Move HDC Adapter To Device Package

Goal: make HDC a device adapter rather than a generic utility.

Work:

- Create `src/harmonyos_dev_mcp/device/hdc/`.
- Move `utils/hdc/*` to `device/hdc/`.
- Update imports.
- Add a temporary compatibility shim only if a single-step import update is too
  risky.

Acceptance:

- No stale imports reference `utils.hdc`, except a deliberate compatibility shim
  if used.
- Device, package, screenshot, and UI tree tests pass.
- `pytest tests/unit -q` passes.
- `ruff check src tests` passes.
- A temporary wheel install still reports 18 registered tools.

Commit:

- `refactor: move hdc adapter to device package`

## Step 5: Move UI Internals To UI Package

Goal: place UI operations, tree parsing, selectors, and normalizers behind a
clear UI boundary.

Work:

- Create `src/harmonyos_dev_mcp/ui/`.
- Move `utils/wrappers/ui_operations.py` to `ui/operations.py`.
- Move `utils/uitree_parser.py` to `ui/tree_parser.py`.
- Move `utils/ui_common.py` to `ui/common.py`.
- Move `utils/normalizers/*` to `ui/normalizers/`.
- Move `utils/selectors/*` to `ui/selectors/`.
- Update imports in tool and HDC code.

Acceptance:

- No stale imports reference old UI utility paths.
- UI, E2E, and element handle tests pass.
- `pytest tests/unit -q` passes.
- `ruff check src tests` passes.
- A temporary wheel install still reports 18 registered tools.

Commit:

- `refactor: move ui internals to ui package`

## Step 6: Extract Hvigor Artifact Finder

Goal: remove artifact detection and output scoring from `HvigorWrapper`.

Work:

- Create `src/harmonyos_dev_mcp/build/artifact_finder.py`.
- Move output freshness, log path extraction, metadata lookup, output scanning,
  scoring, test-artifact filtering, and resolution guidance into the new module.
- Keep public `build_app` behavior unchanged.

Acceptance:

- Artifact finder tests exist under `tests/unit/build/`.
- Build tests pass.
- `pytest tests/unit -q` passes.
- `ruff check src tests` passes.
- `uv build --out-dir dist --clear` passes.

Commit:

- `refactor: extract hvigor artifact finder`

## Step 7: Extract Hvigor Toolchain Discovery

Goal: separate DevEco, Node, Hvigor, SDK, and Java discovery from the build
wrapper.

Work:

- Create `src/harmonyos_dev_mcp/build/toolchain_discovery.py`.
- Move DevEco, Node, Hvigor, SDK, Java, and writable-home discovery logic.
- Make `HvigorWrapper` consume a discovery result instead of owning discovery.

Acceptance:

- Discovery tests live under `tests/unit/build/`.
- Windows, macOS, and Linux layout tests pass.
- `pytest tests/unit/build -q` passes.
- `pytest tests/unit -q` passes.
- `ruff check src tests` passes.

Commit:

- `refactor: extract hvigor toolchain discovery`

## Step 8: Extract Signing And Packaging Helpers

Goal: move SDK signing, HNP repackaging, and HSP integration out of
`HvigorWrapper`.

Work:

- Create `src/harmonyos_dev_mcp/build/signing.py`.
- Create `src/harmonyos_dev_mcp/build/packaging_hnp.py`.
- Create `src/harmonyos_dev_mcp/build/packaging_hsp.py`.
- Move signing config parsing, SDK jar calls, HNP injection, HSP injection, and
  `pack.info` merge logic.
- Preserve all current result fields.

Acceptance:

- HNP and HSP tests pass.
- `security_tool` normal HAP build still returns a signed HAP path.
- `pytest tests/unit/build -q` passes.
- `pytest tests/unit -q` passes.
- `ruff check src tests` passes.

Commit:

- `refactor: extract signing and packaging helpers`

## Step 9: Split Build Target Handlers

Goal: stop growing a single target branch inside the build wrapper.

Work:

- Create `src/harmonyos_dev_mcp/build/targets/`.
- Add target handlers for `hap`, `hsp`, `hnp`, `har`, and `app`.
- Route `build_app` through a coordinator or target dispatcher.
- Keep external `build_app` parameters and result shape unchanged.

Acceptance:

- `target=hap`, `target=hsp`, `target=hnp`, `target=har`, and `target=app`
  coverage still passes.
- `pytest tests/unit/build -q` passes.
- `pytest tests/unit -q` passes.
- `security_tool` `build_app target=hap` passes.

Commit:

- `refactor: split build target handlers`

## Step 10: Introduce Runtime Server Factory

Goal: reduce import-time server side effects and prepare for isolated server
tests.

Work:

- Create `src/harmonyos_dev_mcp/runtime/`.
- Move runtime config, container, and server creation there, or add wrappers that
  preserve compatibility.
- Introduce `create_app()` or `create_server()`.
- Ensure CLI startup creates the server at runtime.

Acceptance:

- CLI entrypoint still starts.
- Runtime/server tests pass.
- Repeated server creation does not share unexpected mutable state.
- `pytest tests/unit -q` passes.
- A temporary wheel install still reports 18 registered tools.

Commit:

- `refactor: introduce runtime server factory`

## Step 11: Register Tools Explicitly

Goal: remove global registry and import side-effect reliance.

Work:

- Add explicit `register_tools(server)`.
- Have each tool module register its tool functions directly or through a
  central registrar.
- Update server creation to call the registrar.
- Keep tool names and count unchanged.

Acceptance:

- The registered tool count remains 18.
- Tool names are unchanged.
- FastMCP schema tests pass.
- Creating more than one server does not duplicate registrations.
- `pytest tests/unit -q` passes.
- `ruff check src tests` passes.

Commit:

- `refactor: register tools explicitly`

## Step 12: Final Integration Report

Goal: report exactly what changed and prove compatibility.

Work:

- Run final static checks, unit tests, build, and wheel smoke.
- Run the `security_tool` real-device core flow.
- Write a final report.

Acceptance:

- `ruff check src tests` passes.
- `pytest tests/unit -q` passes.
- `uv build --out-dir dist --clear` passes.
- Wheel smoke reports version `0.8.0` and 18 registered tools.
- `security_tool` core flow passes:
  - `list_devices`
  - `build_app`
  - `install_app`
  - `query_package main_ability`
  - `run_app`
  - `list_windows`
  - `get_ui_tree`
  - `find_element`
  - `logs_query`

Report format:

```text
Refactor Report

Baseline:
- Start commit:
- End commit:
- PyPI published: no

Directory changes:
- ...

Completed steps:
1. ...
   commit:
   acceptance:

Validation:
- ruff:
- pytest:
- uv build:
- wheel smoke:
- security_tool:

Compatibility:
- MCP tool count:
- Tool names changed:
- Tool parameters changed:
- CLI changed:

Remaining debt:
- ...
```
