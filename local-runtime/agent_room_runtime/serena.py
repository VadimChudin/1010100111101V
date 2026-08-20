from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


READ_ONLY_TOOLS = frozenset({"get_symbols_overview", "find_symbol", "find_referencing_symbols"})
FORBIDDEN_TOOLS = frozenset({"execute_shell_command", "replace_content", "rename_symbol", "delete_memory", "write_memory"})


@dataclass(frozen=True, slots=True)
class SerenaLaunchSpec:
    workspace_root: str
    port: int = 9121

    def command(self) -> list[str]:
        """Run Serena only on loopback. Cloud never receives this endpoint."""
        root = Path(self.workspace_root).resolve()
        return [
            "serena",
            "start-mcp-server",
            "--transport",
            "streamable-http",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--project",
            str(root),
            "--open-web-dashboard",
            "false",
        ]


def validate_tool(tool_name: str) -> str:
    if tool_name in FORBIDDEN_TOOLS or tool_name not in READ_ONLY_TOOLS:
        raise PermissionError("Only approved read-only Serena tools are available through the local runtime")
    return tool_name
