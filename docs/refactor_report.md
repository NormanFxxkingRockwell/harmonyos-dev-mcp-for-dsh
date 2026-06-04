# Refactor Report

Baseline:
- Start commit: `bc8a8a0` (`refactor: flatten package layout`)
- End code commit: `82a56c6` (`refactor: register tools explicitly`)
- PyPI published: no

Directory changes:
- Added `src/harmonyos_dev_mcp/build/` for artifact finding, toolchain discovery, signing, packaging, and target handlers.
- Added `src/harmonyos_dev_mcp/device/hdc/` for HDC adapter code.
- Added `src/harmonyos_dev_mcp/logs/` for log parsing and history internals.
- Added `src/harmonyos_dev_mcp/ui/` for UI operations, tree parsing, selectors, and normalizers.
- Added `src/harmonyos_dev_mcp/runtime/` for server factory and explicit tool registration.
- Mirrored unit tests by domain under `tests/unit/build`, `tests/unit/common`, `tests/unit/device`, `tests/unit/runtime`, and `tests/unit/tools`.

Completed steps:
1. Saved executable refactor plan.
   - Commit: `76701fb`
   - Acceptance: plan saved at `docs/refactor_plan.md`.
2. Cache and ignore cleanup.
   - Commit: `e901b2c`
   - Acceptance: no source/test pycache, no pytest/ruff cache, no dist, tests passed, tool count 18.
3. Mirrored unit test layout by domain.
   - Commit: `8bed6d0`
   - Acceptance: 218 tests collected and passed; pytest config adjusted for `tests/unit/build`.
4. Moved log internals to `logs`.
   - Commit: `8a0074e`
   - Acceptance: wheel includes `harmonyos_dev_mcp/logs`; old tool entrypoint preserved; tool count 18.
5. Moved HDC adapter to `device/hdc`.
   - Commit: `96d5293`
   - Acceptance: no stale `utils.hdc` imports; wheel includes `device/hdc`; tool count 18.
6. Moved UI internals to `ui`.
   - Commit: `b74a7fe`
   - Acceptance: no stale UI utility imports; wheel includes `ui`; lazy exports avoid circular import; tool count 18.
7. Extracted Hvigor artifact finder.
   - Commit: `70f95a5`
   - Acceptance: artifact finder tests added; wheel includes `build/artifact_finder.py`; tool count 18.
8. Extracted Hvigor toolchain discovery.
   - Commit: `ef5ca5e`
   - Acceptance: Windows, macOS, and Linux layout tests added; wheel includes `build/toolchain_discovery.py`; tool count 18.
9. Extracted signing and packaging helpers.
   - Commit: `0fb0e56`
   - Acceptance: helper tests added; HNP/HSP tests passed; `security_tool` normal HAP build returned signed HAP; tool count 18.
10. Split build target handlers.
    - Commit: `d5405df`
    - Acceptance: HAP/HAR/HSP/APP/HNP unit coverage passed; `security_tool target=hap` passed; tool count 18.
11. Introduced runtime server factory.
    - Commit: `7ceb653`
    - Acceptance: `create_app()` returns isolated servers; CLI `main()` creates app at runtime; wheel smoke passed; tool count 18.
12. Registered tools explicitly.
    - Commit: `82a56c6`
    - Acceptance: explicit tool list matches public tool surface; repeated server creation keeps 18 tools; FastMCP schema tests passed.

Validation:
- `ruff check src tests --no-cache`: passed.
- `.venv\Scripts\python.exe -B -m pytest tests\unit -q -p no:cacheprovider`: 233 passed.
- `uv build --out-dir dist --clear`: passed.
- Wheel smoke: version `0.8.0`; explicit tool count 18; registry tool count 18; server tool count 18.
- `security_tool` real-device flow: passed.
  - Device: `3QC0124C11000711`, observed `OpenHarmony-6.1.1.115`, API `24`.
  - `list_devices`: ok, 1 device.
  - `build_app`: ok, signed HAP at `C:\Users\mu\Desktop\code\security_tool\hapsigner\signApp.hap`.
  - `install_app`: ok.
  - `query_package info_type=main_ability`: ok, `EntryAbility`, module `entry`.
  - `run_app`: ok, window found.
  - `list_windows`: ok, 1 matching `com.huawei.securitytool` window.
  - `get_ui_tree`: ok, 527 nodes.
  - `find_element`: ok, found text `安全管理中心`.
  - `logs_query`: ok via hdc hilog fallback path.

Compatibility:
- MCP tool count: unchanged at 18.
- Tool names changed: no.
- Tool parameters changed: no public `build_app`, device, UI, E2E, or log tool parameters changed.
- Tool result shape changed: no intentional public result-shape change.
- CLI changed: entrypoint still runs; server creation is now routed through runtime factory.
- PyPI package version changed: no; this refactor stays on source `0.8.0`.

Remaining debt:
- `HvigorWrapper` is much smaller but still owns some compatibility delegates and validation.
- Tool decorators and global registry remain for backward compatibility; server registration now uses the explicit runtime list.
- Container singleton remains global; future work can introduce a full app/container factory.
- Some parsing helpers are still intentionally lightweight JSON5 scanners rather than a formal JSON5 parser.
