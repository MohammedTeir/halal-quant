"""Encrypted pg_dump plus isolated restore verification; never restores over source."""

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from packages.config.settings import get_settings


class BackupFailure(RuntimeError):
    pass


def libpq_environment(url, database=None):
    url = make_url(url)
    if not url.drivername.startswith("postgresql"):
        raise BackupFailure("PostgreSQL is required")
    env = os.environ.copy()
    for key in ("PGSERVICE", "PGSERVICEFILE", "PGOPTIONS", "PGHOSTADDR"):
        env.pop(key, None)
    values = {
        "PGHOST": url.host or "localhost",
        "PGPORT": str(url.port or 5432),
        "PGDATABASE": database or url.database or "",
        "PGUSER": url.username or "",
        "PGPASSWORD": url.password or "",
        "PGCONNECT_TIMEOUT": "20",
        "PGSSLMODE": str(url.query.get("sslmode", "prefer")),
        "PGCHANNELBINDING": str(url.query.get("channel_binding", "prefer")),
    }
    for query, key in [
        ("sslrootcert", "PGSSLROOTCERT"),
        ("sslcert", "PGSSLCERT"),
        ("sslkey", "PGSSLKEY"),
    ]:
        if query in url.query:
            values[key] = str(url.query[query])
    if values["PGHOST"] not in ("localhost", "127.0.0.1", "::1") and values["PGSSLMODE"] not in (
        "require",
        "verify-ca",
        "verify-full",
    ):
        raise BackupFailure("Remote backups require TLS in DATABASE_URL")
    env.update(values)
    return env


def command(args, env, phase):
    try:
        result = subprocess.run(args, env=env, capture_output=True, text=True, check=False)
    except OSError:
        raise BackupFailure("Required program unavailable: " + phase) from None
    if result.returncode:
        # stderr may contain connection details; never echo it to a shared report.
        server = re.search(r"server version:\s*(\d+)", result.stderr)
        if phase == "pg_dump" and server and "pg_dump version" in result.stderr:
            raise BackupFailure(
                "Install PostgreSQL client " + server.group(1) + " or newer for this server"
            )
        raise BackupFailure("Backup operation failed at " + phase)
    return result.stdout


def row_counts(connection):
    names = connection.execute(
        text("""SELECT n.nspname, c.relname FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind IN ('r','p') AND n.nspname NOT LIKE 'pg_%'
        AND n.nspname <> 'information_schema' ORDER BY 1,2""")
    ).all()
    quote = connection.dialect.identifier_preparer.quote
    return {
        f"{schema}.{table}": connection.scalar(
            text("SELECT count(*) FROM " + quote(schema) + "." + quote(table))
        )
        for schema, table in names
    }


def backup_and_verify(url, output_dir):
    for tool in ("age", "age-keygen", "pg_dump", "pg_restore"):
        if shutil.which(tool) is None:
            raise BackupFailure("Install age and PostgreSQL client tools first")
    url = make_url(url)
    env = libpq_environment(url)
    folder = Path(output_dir).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    folder.chmod(0o700)
    key = folder / "backup-key.txt"
    if key.is_symlink():
        raise BackupFailure("Backup key must not be a symlink")
    if not key.exists():
        command(["age-keygen", "-o", str(key)], env, "key generation")
    key.chmod(0o600)
    recipient = command(["age-keygen", "-y", str(key)], env, "read encryption recipient").strip()
    suffix = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
    archive = folder / ("halal-quant-" + suffix + ".dump.age")
    restore_name = "hq_restore_" + secrets.token_hex(12)
    source_name = url.database
    if not source_name or restore_name == source_name:
        raise BackupFailure("Unsafe restore target")
    engine = create_engine(url, pool_pre_ping=True)
    restore_engine = None
    created = False
    verified = False
    counts = {}
    try:
        with tempfile.TemporaryDirectory(prefix=".backup-verify-", dir=folder) as private:
            plain = Path(private) / "source.dump"
            decrypted = Path(private) / "verified.dump"
            with (
                engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection,
                connection.begin(),
            ):
                connection.execute(text("SET TRANSACTION READ ONLY"))
                server_major = int(connection.scalar(text("SHOW server_version_num"))) // 10000
                binaries = {}
                for program in ("pg_dump", "pg_restore"):
                    packaged = Path(f"/usr/lib/postgresql/{server_major}/bin") / program
                    binary = str(packaged) if packaged.is_file() else program
                    version = command([binary, "--version"], env, program + " version")
                    match = re.search(r"(\d+)\.", version)
                    if match is None or int(match.group(1)) != server_major:
                        raise BackupFailure(
                            f"Install postgresql-client-{server_major} to match this server for restore verification"
                        )
                    binaries[program] = binary
                snapshot = connection.scalar(text("SELECT pg_export_snapshot()"))
                counts = row_counts(connection)
                command(
                    [
                        binaries["pg_dump"],
                        "--format=custom",
                        "--no-owner",
                        "--no-acl",
                        "--snapshot",
                        snapshot,
                        "--file",
                        str(plain),
                    ],
                    env,
                    "pg_dump",
                )
            plain.chmod(0o600)
            command(
                ["age", "--encrypt", "-r", recipient, "-o", str(archive), str(plain)],
                env,
                "encryption",
            )
            archive.chmod(0o600)
            plain.unlink()
            command(
                ["age", "--decrypt", "-i", str(key), "-o", str(decrypted), str(archive)],
                env,
                "decryption verification",
            )
            decrypted.chmod(0o600)
            # Only a fresh, generated name can receive the restore. Never use DATABASE_URL as the target database.
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
                name = admin.dialect.identifier_preparer.quote(restore_name)
                admin.execute(text("CREATE DATABASE " + name + " TEMPLATE template0"))
                created = True
            restore_env = libpq_environment(url, database=restore_name)
            command(
                [
                    binaries["pg_restore"],
                    "--dbname",
                    restore_name,
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--no-acl",
                    "--exit-on-error",
                    "--single-transaction",
                    str(decrypted),
                ],
                restore_env,
                "isolated pg_restore",
            )
            restore_engine = create_engine(url.set(database=restore_name), pool_pre_ping=True)
            with restore_engine.connect() as restored:
                if row_counts(restored) != counts:
                    raise BackupFailure("Restored row counts differ from the exported snapshot")
                version = restored.scalar(text("SELECT version_num FROM alembic_version"))
                if version != "0007_access_delivery":
                    raise BackupFailure("Restored application migration differs")
            verified = True
    finally:
        if restore_engine is not None:
            restore_engine.dispose()
        try:
            if created:
                if not restore_name.startswith("hq_restore_") or restore_name == source_name:
                    raise BackupFailure("Refusing an unsafe database cleanup target")
                with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
                    admin.execute(
                        text(
                            "DROP DATABASE " + admin.dialect.identifier_preparer.quote(restore_name)
                        )
                    )
        finally:
            engine.dispose()
    with archive.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "status": "PASSED" if verified else "FAILED",
        "encrypted_backup": str(archive),
        "private_key_file": str(key),
        "encrypted_backup_sha256": checksum,
        "source_tables": len(counts),
        "postgresql_major": server_major,
        "snapshot_row_counts_match": verified,
        "temporary_restore_database_removed": created,
        "source_database_restored_over": False,
        "off_device_copy_confirmed": False,
        "note": "Copy the encrypted archive off-device; store its private key separately and privately. Never share key contents.",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Encrypted PostgreSQL backup with isolated restore verification"
    )
    parser.add_argument("--output-dir", default=str(Path.home() / "halal-backups"))
    parser.add_argument(
        "--run",
        action="store_true",
        help="Allow snapshot backup and creation/removal of a generated isolated restore database",
    )
    args = parser.parse_args()
    if not args.run:
        parser.error(
            "Use --run to create an encrypted backup and an isolated temporary restore database"
        )
    try:
        result = backup_and_verify(get_settings().database_url, args.output_dir)
        print(json.dumps(result))
    except BackupFailure as error:
        parser.exit(1, str(error) + "\n")
    except (SQLAlchemyError, OSError, ValueError):
        parser.exit(
            1,
            "Backup/restore verification did not complete; check connectivity, client/server versions and CREATE DATABASE permission. Source was never used as a restore target.\n",
        )


if __name__ == "__main__":
    main()
