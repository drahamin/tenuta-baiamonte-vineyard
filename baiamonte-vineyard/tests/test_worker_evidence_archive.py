from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from app.domains import worker_evidence_archive as archive


@contextmanager
def _transaction():
    yield None, MagicMock()


def test_worker_camera_frame_is_deduplicated_encrypted_and_recoverable():
    original = b"\xff\xd8camera evidence with visible scene details\xff\xd9"
    with TemporaryDirectory() as directory:
        root = Path(directory) / "evidence"
        key = Path(directory) / "evidence.key"
        with patch.object(archive, "ARCHIVE_ROOT", root), patch.object(archive, "KEY_PATH", key), \
             patch.object(archive, "transaction", _transaction), patch.object(archive, "estate_id", return_value="estate-1"):
            evidence_id = archive.archive_camera_frame(
                original, content_type="image/jpeg", camera_entity_id="camera.main_parking",
                observation_zone="main_parking", captured_at=None, source_kind="eufy_event",
            )
            encrypted_path = root / evidence_id[:2] / f"{evidence_id}.aes"
            assert encrypted_path.exists()
            assert original not in encrypted_path.read_bytes()
            assert key.stat().st_mode & 0o077 == 0

            row = {
                "id": evidence_id, "storage_path": str(Path(evidence_id[:2]) / f"{evidence_id}.aes"),
                "content_type": "image/jpeg", "camera_entity_id": "camera.main_parking",
            }
            with patch.object(archive, "fetch_one", return_value=row):
                recovered = archive.read_camera_evidence(evidence_id)
            assert recovered is not None
            assert recovered[1] == original


def test_camera_evidence_schema_keeps_encrypted_files_out_of_mariadb():
    migration = Path("db/migrations/134_worker_camera_evidence.sql").read_text(encoding="utf-8")
    assert "worker_camera_evidence" in migration
    assert "retention_until" in migration
    assert "legal_hold" in migration
    assert "evidence_id" in migration
    assert "BLOB" not in migration
