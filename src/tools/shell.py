"""Restricted shell execution tool."""
import asyncio
import shlex
from src.config import Settings, get_settings

async def run_command(command: str, settings: Settings | None = None) -> dict[str, object]:
    settings = settings or get_settings()
    parts = shlex.split(command)
    if not parts or parts[0] not in settings.allowed_commands:
        return {"ok": False, "error": "Command is not allowed"}
    try:
        process = await asyncio.create_subprocess_exec(*parts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=settings.shell_command_timeout)
        return {"ok": process.returncode == 0, "returncode": process.returncode, "stdout": stdout.decode(errors="replace"), "stderr": stderr.decode(errors="replace")}
    except asyncio.TimeoutError:
        process.kill()
        return {"ok": False, "error": "Command timed out"}
