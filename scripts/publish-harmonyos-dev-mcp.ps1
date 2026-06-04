$ErrorActionPreference = "Stop"

if (-not $env:UV_PUBLISH_TOKEN -and -not $env:UV_PUBLISH_PASSWORD) {
    throw "Set UV_PUBLISH_TOKEN or UV_PUBLISH_PASSWORD before publishing."
}

uv build --package harmonyos-dev-mcp --out-dir dist --clear
uv publish dist\harmonyos_dev_mcp-*.tar.gz dist\harmonyos_dev_mcp-*-py3-none-any.whl
