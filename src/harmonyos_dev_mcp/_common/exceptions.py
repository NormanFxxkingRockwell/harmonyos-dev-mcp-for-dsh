"""Custom exceptions for HarmonyOS MCP services."""


class MCPError(Exception):
    """Base exception carrying a stable MCP error code."""

    def __init__(self, message: str, code: str = "MCP_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code
