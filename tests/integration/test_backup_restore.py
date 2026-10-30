import os
import shutil

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from services.notifications.models import User
from services.operations.backup import BackupFailure, backup_and_verify, libpq_environment


def test_libpq_credentials_are_in_environment_not_connection_arguments():
    env = libpq_environment(
        "postgresql+psycopg://u:private-password@database.example.test/app?sslmode=require&channel_binding=require"
    )
    assert env["PGPASSWORD"] == "private-password"
    assert env["PGSSLMODE"] == "require" and env["PGCHANNELBINDING"] == "require"
    assert env["PGDATABASE"] == "app"
    with pytest.raises(BackupFailure):
        libpq_environment("postgresql+psycopg://u:p@database.example.test/app?sslmode=disable")


def test_encrypted_backup_restores_to_an_isolated_database_and_preserves_source(client, tmp_path):
    engine = client.app.state.engine
    if engine.dialect.name != "postgresql":
        pytest.skip("Real pg_dump/age/pg_restore acceptance runs on PostgreSQL CI")
    for tool in ("age", "pg_dump", "pg_restore"):
        assert shutil.which(tool), "CI must install backup verification tools"
    sessions = sessionmaker(engine)
    with sessions.begin() as db:
        db.add(
            User(
                id="backup-owner",
                email="backup@example.test",
                password="",
                role="viewer",
                enabled=True,
            )
        )
    result = backup_and_verify(engine.url, tmp_path / "private-backups")
    assert result["status"] == "PASSED" and result["snapshot_row_counts_match"]
    assert result["temporary_restore_database_removed"]
    assert not result["source_database_restored_over"]
    assert result["encrypted_backup"].endswith(".age")
    assert os.stat(result["private_key_file"]).st_mode & 0o077 == 0
    with sessions() as db:
        assert db.scalar(select(User.id).where(User.id == "backup-owner")) == "backup-owner"
