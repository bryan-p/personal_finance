from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass
class StagedUploads:
    entries: list[tuple[Path, Path]]
    directory: Path | None


def upload_paths(storage_paths: list[str], upload_root: Path) -> list[Path]:
    root = upload_root.resolve()
    paths: list[Path] = []
    seen: set[Path] = set()
    for value in storage_paths:
        if not value:
            continue
        path = Path(value).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Upload path is outside the configured storage directory: {path}")
        if path in seen or not path.exists():
            continue
        if not path.is_file():
            raise ValueError(f"Upload path is not a file: {path}")
        seen.add(path)
        paths.append(path)
    return paths


def stage_uploads(storage_paths: list[str], upload_root: Path) -> StagedUploads:
    paths = upload_paths(storage_paths, upload_root)
    if not paths:
        return StagedUploads(entries=[], directory=None)

    trash_root = upload_root.resolve() / ".trash"
    directory = trash_root / uuid4().hex
    directory.mkdir(parents=True)
    entries: list[tuple[Path, Path]] = []
    try:
        for index, original in enumerate(paths):
            staged = directory / f"{index}-{original.name}"
            original.replace(staged)
            entries.append((original, staged))
    except OSError:
        restore_uploads(StagedUploads(entries=entries, directory=directory))
        raise
    return StagedUploads(entries=entries, directory=directory)


def restore_uploads(staged_uploads: StagedUploads) -> None:
    for original, staged in reversed(staged_uploads.entries):
        if staged.exists():
            staged.replace(original)
    _remove_empty_directories(staged_uploads.directory)


def purge_uploads(staged_uploads: StagedUploads) -> int:
    deleted = 0
    for _, staged in staged_uploads.entries:
        if staged.exists():
            staged.unlink()
            deleted += 1
    _remove_empty_directories(staged_uploads.directory)
    return deleted


def _remove_empty_directories(directory: Path | None) -> None:
    if not directory:
        return
    try:
        directory.rmdir()
        directory.parent.rmdir()
    except OSError:
        pass
