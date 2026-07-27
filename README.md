# HarmonyOS Dev MCP

`harmonyos_dev_mcp` provides HarmonyOS MCP tools for device discovery, app build and deployment, UI automation, E2E inspection, and log validation.

[![Version](https://img.shields.io/badge/version-0.8.3-blue)](pyproject.toml)
[![PyPI](https://img.shields.io/pypi/v/harmonyos-dev-mcp.svg)](https://pypi.org/project/harmonyos-dev-mcp/)
[![Python](https://img.shields.io/badge/python-3.12+-blue)](https://www.python.org/)

## Links

- PyPI: [harmonyos-dev-mcp](https://pypi.org/project/harmonyos-dev-mcp/)
- Tool reference: [docs/tool_reference.md](docs/tool_reference.md)
- Logs query guide: [docs/logs_query.md](docs/logs_query.md)

## What It Provides

The package exposes 18 MCP tools:

Parameter notation:

- `name`: required
- `name?`: optional
- `name*`: conditionally required, depending on the selected mode or target

Device-targeted tools also accept `hdc_server?` for wireless debugging by IP. Pass the wireless HDC endpoint, for example `192.168.43.34:35215`, to route commands as `hdc -t 192.168.43.34:35215 ...`. If both a device SN and an IP endpoint are needed, pass `device_id` as the SN and `hdc_server` as the IP endpoint; commands are routed as `hdc -t <SN> -s <IP:port> ...`. You can also set `HARMONYOS_HDC_SERVER` as a default endpoint.

General tools:

| Tool | Parameters |
|---|---|
| `list_devices` | `hdc_server?` |
| `query_package` | `device_id?`, `hdc_server?`, `bundle_name*`, `keyword?`, `info_type?="list"` |
| `logs_query` | `device_id?`, `hdc_server?`, `logs?`, `input_file?`, `input_files?`, `lines?=100`, `level?`, `tag?`, `tag_search?`, `keyword?`, `domain?`, `pid?`, `package_name?`, `start_time?`, `end_time?`, `seconds?`, `save_path?`, `time_expr?`, `include_crash?=false`, `mode?="errors"`, `marker_keywords?`, `fallback_to_historical?=false`, `realtime_wait_ms?=1000`, `context_lines?=0` |

Build tools:

| Tool | Parameters |
|---|---|
| `build_app` | `project_path`, `build_mode?="debug"`, `target?="hap"`, `product?="default"`, `module_name*`, `is_clean?=false`, `include_hsp?=false`, `hsp_module_names?` |
| `install_app` | `hap_path`, `device_id?`, `hdc_server?` |
| `run_app` | `bundle_name`, `device_id?`, `hdc_server?`, `ability_name?`, `module_name?`, `auto_detect?=true` |
| `uninstall_app` | `bundle_name`, `device_id?`, `hdc_server?` |

UI tools:

| Tool | Parameters |
|---|---|
| `screenshot` | `device_id?`, `hdc_server?`, `local_path?`, `display_id?=0`, `left*`, `top*`, `right*`, `bottom*` |
| `click_element` | `device_id?`, `hdc_server?`, `x*`, `y*`, `element_handle*`, `text*`, `element_type*`, `element_id*`, `double_click?=false`, `bundle_name?` |
| `long_press_element` | `device_id?`, `hdc_server?`, `x*`, `y*`, `element_handle*`, `text*`, `element_type*`, `element_id*`, `bundle_name?` |
| `input_text` | `text`, `device_id?`, `hdc_server?`, `x*`, `y*`, `element_handle*`, `element_text*`, `element_type*`, `element_id*`, `bundle_name?`, `mode?="replace"` |
| `swipe` | `device_id?`, `hdc_server?`, `from_x*`, `from_y*`, `to_x*`, `to_y*`, `direction*`, `speed?=600` |
| `drag` | `device_id?`, `hdc_server?`, `from_x`, `from_y`, `to_x`, `to_y`, `speed?=600` |
| `press_key` | `key`, `modifiers?`, `device_id?`, `hdc_server?` |
| `find_element` | `device_id?`, `hdc_server?`, `text*`, `element_type*`, `element_id*`, `bundle_name?`, `window_id?` |

E2E tools:

| Tool | Parameters |
|---|---|
| `get_ui_tree` | `device_id?`, `hdc_server?`, `bundle_name?`, `window_id?` |
| `list_windows` | `device_id?`, `hdc_server?`, `bundle_name?` |
| `wait_element` | `device_id?`, `hdc_server?`, `bundle_name?`, `window_id?`, `text*`, `element_type*`, `element_id*`, `state?="found"`, `timeout_ms?=5000`, `interval_ms?=300` |

`build_app` supports HarmonyOS HAP, HAR, HSP, APP, and HNP build flows. HSP outputs can also be integrated into a HAP with `include_hsp=true`.

Detailed validation rules, result fields, errors, and examples are in the [tool reference](docs/tool_reference.md).

## Layout

```text
mcp_ho_dev/
|- src/harmonyos_dev_mcp/
|  |- build/                   # Hvigor build helpers, signing, packaging, and target handlers
|  |- device/hdc/              # HDC device, package, app, file, and UI adapters
|  |- logs/                    # Log query parsing and history support
|  |- runtime/                 # Server factory and explicit MCP tool registration
|  |- tools/                   # Public MCP tool entrypoints
|  |- ui/                      # UI tree parsing, selectors, actions, and normalization
|  |- utils/                   # Compatibility wrappers
|  `- _common/                 # Shared runtime infrastructure bundled in this package
|- tests/unit/                 # Unit tests grouped by domain
|- docs/                       # Public tool and log query documentation
|- scripts/                    # Release helpers
|- pyproject.toml              # Project metadata and build config
|- uv.lock
|- README.md
```

## Requirements

- Python 3.12+
- DevEco Studio 5.0+
- HarmonyOS SDK toolchains, including `hdc`
- `uv`

## Install

Install from PyPI:

```bash
pip install harmonyos-dev-mcp
```

Install from source for local development:

```bash
uv sync
```

## Run

```bash
uv run harmonyos-dev-mcp
```

Check connected devices:

```bash
hdc list targets
```

Use wireless debugging by IP:

```python
await list_devices(hdc_server="192.168.43.34:35215")
await install_app(r"C:\path\to\app.hap", hdc_server="192.168.43.34:35215")
```

Or set a default endpoint:

```bash
set HARMONYOS_HDC_SERVER=192.168.43.34:35215
```

## Documentation

- [Tool Reference](docs/tool_reference.md)
- [Logs Query Guide](docs/logs_query.md)

## Build Examples

Build a debug HAP:

```python
await build_app(r"C:\path\to\project", target="hap", build_mode="debug", product="default")
```

Build HSP modules and integrate them into a HAP:

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

Build an HNP-injected HAP:

```python
await build_app(r"C:\path\to\project", target="hnp", build_mode="debug", product="default")
```

## Development

Run unit tests:

```bash
uv run pytest tests/unit -v
```

Run with coverage:

```bash
uv run pytest tests/unit -v --cov=harmonyos_dev_mcp
```

Build package artifacts:

```bash
uv build --out-dir dist --clear
```

## Notes

- `build_app` is a long-running tool. Set MCP `tools/call timeout` to at least `60s`, and prefer `120s` for cold builds.
- `build_app target="hnp"` builds a base HAP, injects module HNP packages from `entry/hnp`, and signs the HAP through SDK packaging tools.
- `build_app target="hsp"` builds shared modules; `build_app target="hap" include_hsp=true` can integrate one or more HSP outputs into the HAP.
- `logs_query` supports `errors` and `markers` modes.
- The shared infrastructure that used to live in a separate common package is bundled in `harmonyos_dev_mcp._common`.

## License

Apache License 2.0
