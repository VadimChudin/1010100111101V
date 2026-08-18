"""Constrained file operations rooted at a configured workspace."""
from pathlib import Path

class FileTool:
    def __init__(self, root: str = ".") -> None:
        self.root = Path(root).resolve()

    def _safe(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if self.root not in path.parents and path != self.root:
            raise ValueError("Path escapes workspace")
        return path

    def read(self, relative: str) -> str:
        return self._safe(relative).read_text(encoding="utf-8")

    def write(self, relative: str, content: str) -> None:
        path = self._safe(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def list(self, relative: str = ".") -> list[str]:
        return [str(item.relative_to(self.root)) for item in self._safe(relative).iterdir()]
