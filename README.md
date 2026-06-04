# HarmonyOS Dev MCP

`harmonyos_dev_mcp` is the main HarmonyOS MCP service for device automation, app deployment, UI interaction, E2E support, and log-based validation.

[![Version](https://img.shields.io/badge/version-0.8.0-blue)](pyproject.toml)
[![Python](https://img.shields.io/badge/python-3.12+-blue)](https://www.python.org/)

## What It Provides

This service exposes HarmonyOS automation capabilities as MCP tools:

- General: `list_devices`, `query_package`, `logs_query`
- Build: `build_app`, `install_app`, `run_app`, `uninstall_app`
- UI: `screenshot`, `click_element`, `long_press_element`, `input_text`, `swipe`, `drag`, `press_key`, `find_element`
- E2E: `get_ui_tree`, `list_windows`, `wait_element`

## Layout

```text
mcp_ho_dev/
|- src/harmonyos_dev_mcp/      # Package source
|- tests/                      # Unit tests
|- docs/                       # Tool and log query docs
|- scripts/                    # Release helpers
|- pyproject.toml              # Package config
|- uv.lock
|- README.md
```

## Requirements

- Python 3.12+
- DevEco Studio 5.0+
- `hdc`
- `uv`

## Run

```bash
uv sync
uv run harmonyos-dev-mcp
```

Check connected devices:

```bash
hdc list targets
```

## Documentation

- [Tool Reference](docs/tool_reference.md)
- [Logs Query Guide](docs/logs_query.md)

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
- Since `0.8.0`, the infrastructure previously published as `harmonyos-mcp-common` is bundled inside this package as `harmonyos_dev_mcp._common`.

## License

Apache License 2.0
