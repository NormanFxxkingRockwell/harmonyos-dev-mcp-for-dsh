# HarmonyOS Dev MCP 0.7.6 to 0.8.1 Update Notes

This document summarizes the changes from `harmonyos-dev-mcp` `0.7.6` to the current `0.8.1` release.

## Version Timeline

| Version | Date | Commit | PyPI |
|---|---:|---|---|
| `0.7.6` | 2026-05-21 | `2fe0242` | [0.7.6](https://pypi.org/project/harmonyos-dev-mcp/0.7.6/) |
| `0.7.7` | 2026-05-27 | `7c28dfa` | [0.7.7](https://pypi.org/project/harmonyos-dev-mcp/0.7.7/) |
| `0.8.0` | 2026-06-04 | `f482780` | [0.8.0](https://pypi.org/project/harmonyos-dev-mcp/0.8.0/) |
| `0.8.1` | 2026-06-04 | `cbaf74f` | [0.8.1](https://pypi.org/project/harmonyos-dev-mcp/0.8.1/) |

## Executive Summary

`0.8.1` keeps the public MCP tool surface stable while consolidating the project into one package and expanding build support.

- MCP tool count remains `18`.
- Public tool names are unchanged.
- Public response envelope is unchanged.
- `build_app` now supports HSP integration into HAP builds, including multiple HSP modules.
- HNP direct packaging remains supported without relying on project-local `.bat`, `.ps1`, or `.sh` scripts.
- The old separate common package line is now bundled into `harmonyos_dev_mcp._common`.
- The old `services/harmonyos_compile_mcp` line has been removed.
- Repository layout is flattened to the root package structure under `src/harmonyos_dev_mcp`.

## What Changed By Version

### 0.7.7

Build feature release focused on HSP support.

- Added HSP integration for HAP builds.
- Added support for multiple HSP modules.
- Added `hsp_output_paths` to HAP build results when HSP integration is enabled.
- Simplified HSP module selection to use `hsp_module_names` as the list parameter.

Relevant `build_app` additions since `0.7.6`:

| Parameter | Type | Notes |
|---|---|---|
| `include_hsp` | `bool` | Enables HSP build and integration when `target="hap"`. |
| `hsp_module_names` | `list[str]` | Optional list of shared module names. If omitted or empty, shared modules are auto-discovered. |

### 0.8.0

Packaging and project-line consolidation release.

- Merged the shared common infrastructure into `harmonyos-dev-mcp` as `harmonyos_dev_mcp._common`.
- Removed the separate `packages/common` source line from this repository.
- Removed `services/harmonyos_compile_mcp`, because the compile-only service is no longer published or maintained in this line.
- Kept HAP/HAR/HSP/APP/HNP build support in the main `build_app` tool.
- Kept HNP packaging inside the main package instead of delegating to external project-local scripts.
- Updated package metadata and release flow toward the single `harmonyos-dev-mcp` package.

### 0.8.1

Documentation, layout, and maintainability release.

- Flattened repository layout from `services/harmonyos_dev_mcp/...` into root-level `src/`, `tests/`, and `docs/`.
- Split internal domains into clearer packages:
  - `build/` for Hvigor discovery, artifact finding, signing, HNP packaging, HSP packaging, and build target handlers.
  - `device/hdc/` for HDC device, app, package, file, screenshot, and UI adapters.
  - `logs/` for log parsing, history, crash parsing, and time handling.
  - `ui/` for UI operations, tree parsing, selectors, and normalizers.
  - `runtime/` for server factory and explicit MCP tool registration.
  - `_common/` for bundled shared infrastructure.
- Added explicit runtime tool registration while preserving the same 18 MCP tools.
- Updated README with:
  - PyPI link.
  - 18-tool parameter overview.
  - Current directory structure.
  - HAP, HSP, and HNP build examples.
- Added package project links in PyPI metadata:
  - Homepage.
  - Repository.
  - Documentation.
  - Issues.
- Removed temporary refactor planning and report documents from the repository and release artifacts.

## Public Tool Compatibility

The public MCP tools are unchanged from `0.7.6` to `0.8.1`.

General tools:

- `list_devices`
- `query_package`
- `logs_query`

Build tools:

- `build_app`
- `install_app`
- `run_app`
- `uninstall_app`

UI tools:

- `screenshot`
- `click_element`
- `long_press_element`
- `input_text`
- `swipe`
- `drag`
- `press_key`
- `find_element`

E2E tools:

- `get_ui_tree`
- `list_windows`
- `wait_element`

Compatibility notes:

- Existing users calling MCP tools by name do not need to rename tools.
- Existing `build_app` calls for HAP/HAR/HSP/APP/HNP still work.
- `module_name` is still required for direct `target="har"` and `target="hsp"` builds.
- `include_hsp` and `hsp_module_names` are additive parameters for HAP builds.
- Internal imports from old repository paths such as `services/harmonyos_dev_mcp`, `packages/common`, or `services/harmonyos_compile_mcp` are not supported.

## Current `build_app` Scope

`build_app` supports:

| Target | Description |
|---|---|
| `hap` | Builds a HAP artifact. Can also integrate HSP modules when `include_hsp=true`. |
| `har` | Builds a HAR for a specified module. |
| `hsp` | Builds a shared HSP module. |
| `app` | Builds an APP artifact. |
| `hnp` | Builds a base HAP, injects HNP payloads, and signs the final HAP. |

HSP-in-HAP example:

```python
await build_app(
    r"C:\path\to\project",
    target="hap",
    build_mode="debug",
    product="default",
    include_hsp=True,
    hsp_module_names=["library_one", "library_two"],
)
```

HNP example:

```python
await build_app(
    r"C:\path\to\project",
    target="hnp",
    build_mode="debug",
    product="default",
)
```

## Upgrade Guide

Install or upgrade from PyPI:

```bash
pip install -U harmonyos-dev-mcp==0.8.1
```

Run the MCP server:

```bash
harmonyos-dev-mcp
```

For local development:

```bash
uv sync
uv run harmonyos-dev-mcp
```

## Migration Notes

For normal MCP clients:

- Keep using the same MCP server command and tool names.
- Increase MCP `tools/call` timeout for `build_app` to at least `60s`; `120s` is safer for cold builds.
- Use `include_hsp=true` only when the HAP needs HSP shared module integration.
- Pass multiple HSP modules through `hsp_module_names`.

For repository or internal-code users:

- Update old source paths under `services/harmonyos_dev_mcp` to `src/harmonyos_dev_mcp`.
- Remove direct usage of `packages/common`; use the bundled `harmonyos_dev_mcp._common` only if internal access is unavoidable.
- Remove usage of `services/harmonyos_compile_mcp`; that line is intentionally removed.
- Do not rely on temporary refactor documents; the maintained docs are:
  - `docs/tool_reference.md`
  - `docs/logs_query.md`
  - this update document

## Validation

Validation completed before the `0.8.1` release:

- `pytest tests/unit`: `233 passed`.
- `uv run --no-sync ruff check src tests --no-cache`: passed.
- `uv build --out-dir dist --clear`: passed.
- Wheel smoke: version `0.8.1`, registered tool count `18`.
- Wheel and sdist do not include temporary refactor planning or report documents.
- Real-device validation passed on device `3QC0124C11000711`:
  - `C:\Users\mu\Desktop\code\security_tool`: build, install, launch, UI tree, element find, and log query passed.
  - `C:\Users\mu\Desktop\demo`: build, install, launch, UI tree, element find, and log query passed.

## Current Release Artifacts

PyPI:

- [harmonyos-dev-mcp 0.8.1](https://pypi.org/project/harmonyos-dev-mcp/0.8.1/)

Local build artifacts:

- `dist/harmonyos_dev_mcp-0.8.1-py3-none-any.whl`
- `dist/harmonyos_dev_mcp-0.8.1.tar.gz`
