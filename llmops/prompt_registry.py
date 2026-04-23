import yaml, hashlib, time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class PromptVersion:
    version: str
    content: str
    is_active: bool
    created_at: float
    sha256: str

    @classmethod
    def from_file(cls, path: Path, version: str, is_active: bool = False):
        content = path.read_text(encoding="utf-8")
        return cls(
            version=version,
            content=content,
            is_active=is_active,
            created_at=time.time(),
            sha256=hashlib.sha256(content.encode()).hexdigest()
        )


class PromptRegistry:
    """
    Responsibilities:
      - Load versioned prompts from disk (or DB for live updates)
      - Support A/B/n testing via traffic_split config
      - Rollback: set_active(version) → immediate effect
      - Audit log: every prompt use is hashed + logged
    """
    def __init__(self, base_dir: str = "agent_file/prompt_library/versions"):
        self.base_dir = Path(base_dir)
        self._prompts: dict[str, PromptVersion] = {}
        self._active_version: str = ""
        self._load_all()

    def _load_all(self):
        for f in sorted(self.base_dir.glob("*.txt")):
            version = f.stem
            self._prompts[version] = PromptVersion.from_file(f, version)
        # Mark latest as active
        if self._prompts:
            latest = sorted(self._prompts.keys())[-1]
            self._prompts[latest].is_active = True
            self._active_version = latest

    def get_active(self) -> PromptVersion:
        return self._prompts[self._active_version]

    def set_active(self, version: str):
        """Instant rollback or promotion."""
        if version not in self._prompts:
            raise ValueError(f"Version {version} not found")
        for v in self._prompts.values():
            v.is_active = False
        self._prompts[version].is_active = True
        self._active_version = version

    def list_versions(self) -> list[dict]:
        return [
            {"version": v.version, "active": v.is_active,
             "sha256": v.sha256[:8], "created_at": v.created_at}
            for v in self._prompts.values()
        ]