from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from .runtime import git_inventory

MAX_OUTPUT_CHARS = 24_000
MAX_FILE_BYTES = 1_000_000
PROTECTED_NAMES = {".env", ".git", ".ssh", "id_rsa", "secrets", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"}
ALLOWED_TEST_BINARIES = {"python", "python3", "pytest", "pnpm", "npm", "yarn", "node", "go", "cargo", "mvn", "gradle", "./gradlew", "./mvnw"}
FORBIDDEN_TEST_ARGUMENTS = {"-c", "--command", "--eval", "-e", "exec", "run-script"}


class WorkspaceBoundaryError(PermissionError):
    pass


def _bounded_text(value: str) -> dict[str, Any]:
    if len(value) <= MAX_OUTPUT_CHARS:
        return {"text": value, "truncated": False}
    return {"text": value[:MAX_OUTPUT_CHARS], "truncated": True, "total_characters": len(value)}


class LocalWorkspaceExecutor:
    """Scoped local workspace operations. Never invokes a shell and never accepts an arbitrary command."""

    def __init__(self, workspace_root: str | Path) -> None:
        self.root = Path(workspace_root).resolve()
        if not self.root.is_dir():
            raise WorkspaceBoundaryError("Configured workspace root does not exist")

    def _resolve(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceBoundaryError("Path escapes the registered workspace") from exc
        if any(part in PROTECTED_NAMES or part.startswith(".env") for part in Path(relative_path).parts):
            raise WorkspaceBoundaryError("Protected paths are never available to workspace operations")
        return candidate

    def _run(self, arguments: list[str], *, timeout: int = 60, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(arguments, cwd=self.root, input=stdin, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"Local operation failed to start or timed out: {exc}") from exc

    def _git_files(self) -> list[str]:
        result = self._run(["git", "ls-files", "-z"], timeout=120)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "git ls-files failed")
        return [path for path in result.stdout.split("\0") if path and not any(part in PROTECTED_NAMES or part.startswith(".env") for part in Path(path).parts)]

    def refresh_index(self) -> dict[str, Any]:
        inventory = git_inventory(self.root)
        files = self._git_files()
        languages: dict[str, int] = {}
        for relative in files:
            suffix = Path(relative).suffix.lower() or "[none]"
            languages[suffix] = languages.get(suffix, 0) + 1
        return {"inventory": inventory, "tracked_files": len(files), "suffix_counts": dict(sorted(languages.items())[:100]), "content_uploaded": False}

    def list_files(self, prefix: str = "", limit: int = 500) -> dict[str, Any]:
        files = [path for path in self._git_files() if path.startswith(prefix)]
        page = files[:limit]
        return {"prefix": prefix, "files": page, "returned": len(page), "total_matching": len(files), "truncated": len(files) > len(page)}

    def search_text(self, query: str, prefix: str = "", limit: int = 50) -> dict[str, Any]:
        arguments = ["git", "-c", "color.ui=false", "grep", "-n", "--fixed-strings", "--", query]
        result = self._run(arguments, timeout=120)
        if result.returncode not in {0, 1}:
            raise RuntimeError(result.stderr.strip() or "git grep failed")
        matches = []
        for line in result.stdout.splitlines():
            path = line.split(":", 1)[0]
            if prefix and not path.startswith(prefix):
                continue
            if any(part in PROTECTED_NAMES or part.startswith(".env") for part in Path(path).parts):
                continue
            matches.append(line)
            if len(matches) >= limit:
                break
        return {"query": query, "matches": matches, "truncated": len(matches) >= limit}

    def read_file_range(self, relative_path: str, start_line: int, end_line: int) -> dict[str, Any]:
        path = self._resolve(relative_path)
        if not path.is_file():
            raise FileNotFoundError("Requested file does not exist")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise WorkspaceBoundaryError("Requested file exceeds the read size limit")
        raw = path.read_bytes()
        if b"\0" in raw:
            raise WorkspaceBoundaryError("Binary file contents are not exposed")
        lines = raw.decode("utf-8", errors="replace").splitlines()
        selected = lines[start_line - 1:end_line]
        return {"path": relative_path, "start_line": start_line, "end_line": min(end_line, len(lines)), "lines": selected, "total_lines": len(lines)}

    def _patch_paths(self, patch: str) -> list[str]:
        paths = []
        for line in patch.splitlines():
            if line.startswith("+++ b/") or line.startswith("--- a/"):
                candidate = line[6:].split("\t", 1)[0]
                if candidate != "/dev/null":
                    self._resolve(candidate)
                    paths.append(candidate)
        if not paths:
            raise WorkspaceBoundaryError("Patch does not contain a workspace file path")
        return sorted(set(paths))

    def apply_unified_patch(self, patch: str) -> dict[str, Any]:
        paths = self._patch_paths(patch)
        check = self._run(["git", "apply", "--check", "--whitespace=nowarn", "-"], timeout=60, stdin=patch)
        if check.returncode != 0:
            raise RuntimeError(check.stderr.strip() or "Patch validation failed")
        applied = self._run(["git", "apply", "--whitespace=nowarn", "-"], timeout=60, stdin=patch)
        if applied.returncode != 0:
            raise RuntimeError(applied.stderr.strip() or "Patch could not be applied")
        return {"applied": True, "paths": paths, "git_diff": _bounded_text(self._run(["git", "diff", "--", *paths], timeout=60).stdout)}

    def _test_profile(self, name: str) -> tuple[list[str], int]:
        config_path = self.root / "agent-room.toml"
        if not config_path.is_file():
            raise WorkspaceBoundaryError("agent-room.toml with an approved [tests.<profile>] command is required")
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
        profile = dict(payload.get("tests", {})).get(name)
        if not isinstance(profile, dict):
            raise WorkspaceBoundaryError("Requested test profile is not declared in agent-room.toml")
        command = profile.get("command")
        timeout = profile.get("timeout_seconds", 600)
        if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
            raise WorkspaceBoundaryError("Test profile command must be a non-empty argument list")
        if command[0] not in ALLOWED_TEST_BINARIES or any(part in FORBIDDEN_TEST_ARGUMENTS for part in command[1:]):
            raise WorkspaceBoundaryError("Test profile is outside the approved command policy")
        if not isinstance(timeout, int) or not 1 <= timeout <= 900:
            raise WorkspaceBoundaryError("Test profile timeout must be from 1 to 900 seconds")
        return command, timeout

    def run_test_profile(self, profile: str) -> dict[str, Any]:
        command, timeout = self._test_profile(profile)
        result = self._run(command, timeout=timeout)
        return {"profile": profile, "command": command, "exit_code": result.returncode, "stdout": _bounded_text(result.stdout), "stderr": _bounded_text(result.stderr)}

    def git_status(self) -> dict[str, Any]:
        result = self._run(["git", "status", "--short", "--branch"], timeout=60)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "git status failed")
        return _bounded_text(result.stdout)

    def git_diff(self, relative_path: str | None = None) -> dict[str, Any]:
        arguments = ["git", "diff", "--"]
        if relative_path:
            self._resolve(relative_path)
            arguments.append(relative_path)
        result = self._run(arguments, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "git diff failed")
        return _bounded_text(result.stdout)

    def git_commit(self, message: str) -> dict[str, Any]:
        staged = self._run(["git", "add", "-u"], timeout=60)
        if staged.returncode != 0:
            raise RuntimeError(staged.stderr.strip() or "git add failed")
        committed = self._run(["git", "commit", "-m", message], timeout=120)
        if committed.returncode != 0:
            raise RuntimeError(committed.stderr.strip() or "git commit failed")
        return {"committed": True, "output": _bounded_text(committed.stdout)}

    def git_push(self, remote: str, branch: str | None = None) -> dict[str, Any]:
        arguments = ["git", "push", remote]
        if branch:
            arguments.append(branch)
        pushed = self._run(arguments, timeout=180)
        if pushed.returncode != 0:
            raise RuntimeError(pushed.stderr.strip() or "git push failed")
        return {"pushed": True, "output": _bounded_text(pushed.stdout + pushed.stderr)}
