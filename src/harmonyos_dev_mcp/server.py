"""HarmonyOS MCP server entry point."""

from .runtime.server_factory import create_app, run_app


mcp = create_app()


def main() -> None:
    run_app(create_app())


if __name__ == "__main__":
    main()
