"""Resolve historical locations without rewriting historical manifests."""
import json
from pathlib import Path


def archive_root(project_root: Path) -> Path:
    return project_root.parent / "project_archive" / project_root.name


def _relocations(project_root: Path) -> list[tuple[Path, Path]]:
    """Read version-specific moves from configuration, not shared logic."""
    config = project_root / "configs" / "historical_path_mappings.json"
    if not config.exists():
        return []
    payload = json.loads(config.read_text(encoding="utf-8"))
    return [
        (Path(item["source"]), (project_root / item["target"]).resolve())
        for item in payload["relocations"]
    ]


def historical_path(project_root: Path, relative: str | Path) -> Path:
    relative = Path(relative)
    candidate = project_root / relative
    if candidate.exists():
        return candidate
    for source, destination in _relocations(project_root):
        if relative.is_relative_to(source):
            return destination / relative.relative_to(source)
    mapping = {"old data": "historical_runs", "migration_backups": "migration_backups"}
    if relative.parts and relative.parts[0] in mapping:
        return archive_root(project_root) / mapping[relative.parts[0]] / Path(*relative.parts[1:])
    return candidate


def logical_relative(project_root: Path, path: Path) -> Path:
    """Keep historical manifest keys stable after relocating their files."""
    path = path.resolve()
    for source, destination in _relocations(project_root):
        if path.is_relative_to(destination):
            return source / path.relative_to(destination)
    try:
        return path.relative_to(project_root.resolve())
    except ValueError:
        relative = path.relative_to(archive_root(project_root).resolve())
        mapping = {"historical_runs": "old data", "migration_backups": "migration_backups"}
        return Path(mapping.get(relative.parts[0], relative.parts[0]), *relative.parts[1:])
