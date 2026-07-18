from pathlib import Path

import pytest

from app.services.deletions import purge_uploads, restore_uploads, stage_uploads, upload_paths


def test_stage_and_restore_uploads(tmp_path: Path):
    upload_root = tmp_path / "imports"
    upload_root.mkdir()
    upload = upload_root / "import.csv"
    upload.write_text("Date,Amount\n2026-07-01,5.00\n")

    staged = stage_uploads([str(upload)], upload_root)

    assert not upload.exists()
    assert staged.entries[0][1].exists()

    restore_uploads(staged)

    assert upload.exists()
    assert upload.read_text() == "Date,Amount\n2026-07-01,5.00\n"


def test_stage_and_purge_uploads(tmp_path: Path):
    upload_root = tmp_path / "imports"
    upload_root.mkdir()
    upload = upload_root / "import.csv"
    upload.write_text("Date,Amount\n2026-07-01,5.00\n")

    staged = stage_uploads([str(upload)], upload_root)

    assert purge_uploads(staged) == 1
    assert not upload.exists()
    assert staged.directory is not None
    assert not staged.directory.exists()


def test_upload_paths_reject_files_outside_storage(tmp_path: Path):
    upload_root = tmp_path / "imports"
    upload_root.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("Date,Amount\n")

    with pytest.raises(ValueError, match="outside the configured storage directory"):
        upload_paths([str(outside)], upload_root)
