from __future__ import annotations
import asyncio
from src.config import get_settings

async def execute_shell(command: str, cwd: str | None = None, timeout_s: int = 30) -> dict:
    settings = get_settings()
    if not command or len(command) > 2000:
        return {"exit_code": -1, "stdout": "", "stderr": "invalid command"}
    try:
        proc = await asyncio.create_subprocess_shell(command, cwd=cwd or settings.workspace_root, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        return {"exit_code": proc.returncode, "stdout": stdout.decode(errors="replace")[:settings.max_tool_output_chars], "stderr": stderr.decode(errors="replace")[:settings.max_tool_output_chars]}
    except asyncio.TimeoutError:
        proc.kill()
        return {"exit_code": -1, "stdout": "", "stderr": "command timed out"}
