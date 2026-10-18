"""One connection per operation, BEGIN IMMEDIATE serializes writers across processes."""

from contextlib import contextmanager, closing
from pathlib import Path
import sqlite3
from .models import Memory, encode, require


class Repository:
    def __init__(self, path):
        self.path = str(path)
        require(self.path != ":memory:", "persistent_path_required")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5, isolation_level=None)) as db:
            db.execute("PRAGMA journal_mode=WAL")
        with self.connection(write=True) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            require(version <= 2, "unsupported_schema")
            for number in range(version + 1, 3):
                migration = Path(__file__).with_name("migrations").joinpath(f"{number:03}.sql").read_text()
                # Bundled migrations contain simple statements, no triggers or quoted semicolons.
                for statement in migration.split(";"):
                    if statement.strip():
                        db.execute(statement)

    @contextmanager
    def connection(self, write=False):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA secure_delete=ON")
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, db, scope, identifier):
        row = db.execute(
            "SELECT payload FROM memories WHERE tenant_id=? AND user_id=? AND id=?",
            (scope.tenant_id, scope.user_id, identifier),
        ).fetchone()
        require(row is not None, "not_found")
        return Memory.from_json(row["payload"])

    def save(self, db, record, *, new=False):
        payload = encode(record)
        values = (
            record.tenant_id,
            record.user_id,
            record.tier,
            record.status,
            record.expires_at.isoformat() if record.expires_at else None,
            record.session_id,
            record.task_id,
            record.fact_key,
            record.importance,
            record.verification_status,
            record.created_at.isoformat(),
            payload,
            len(payload.encode()),
            record.id,
        )
        if new:
            db.execute(
                "INSERT INTO memories(tenant_id,user_id,tier,status,expires_at,session_id,task_id,fact_key,importance,verification_status,created_at,payload,size_bytes,id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                values,
            )
        else:
            db.execute(
                "UPDATE memories SET tenant_id=?,user_id=?,tier=?,status=?,expires_at=?,session_id=?,task_id=?,fact_key=?,importance=?,verification_status=?,created_at=?,payload=?,size_bytes=? WHERE id=?",
                values,
            )
        db.execute(
            "INSERT INTO versions(memory_id,version,payload) VALUES (?,?,?)",
            (record.id, record.version, payload),
        )

    def delete_ids(self, db, scope, identifiers):
        # Walk scoped descendants before deleting sources; no content-bearing audit remains.
        pending = set(identifiers)
        found = set()
        while pending:
            identifier = pending.pop()
            if identifier in found:
                continue
            row = db.execute(
                "SELECT id FROM memories WHERE id=? AND tenant_id=? AND user_id=?",
                (identifier, scope.tenant_id, scope.user_id),
            ).fetchone()
            if row is None:
                continue
            found.add(identifier)
            pending.update(
                r[0]
                for r in db.execute("SELECT derived_id FROM dependencies WHERE source_id=?", (identifier,))
            )
        for identifier in found:
            db.execute(
                "DELETE FROM operations WHERE tenant_id=? AND user_id=? AND operation_id IN (SELECT operation_id FROM operation_outputs WHERE tenant_id=? AND user_id=? AND memory_id=?)",
                (scope.tenant_id, scope.user_id, scope.tenant_id, scope.user_id, identifier),
            )
            db.execute(
                "DELETE FROM operations WHERE tenant_id=? AND user_id=? AND operation_id IN (SELECT operation_id FROM operation_sources WHERE tenant_id=? AND user_id=? AND source_id=?)",
                (scope.tenant_id, scope.user_id, scope.tenant_id, scope.user_id, identifier),
            )
            db.execute(
                "DELETE FROM memories WHERE id=? AND tenant_id=? AND user_id=?",
                (identifier, scope.tenant_id, scope.user_id),
            )
        return len(found)
