from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4
from .models import Memory, MemoryInput, MemoryError, TIERS, encode, require, text_ok, timestamp, utf8
from .policies import Policy
from .retrieval import lexical, scored


class MemoryService:
    def __init__(self, repo, *, clock=None, policy=None):
        self.repo = repo
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.policy = policy or Policy()

    def now(self):
        return timestamp(self.clock())

    def get(self, scope, identifier):
        require(text_ok(identifier), "invalid_identifier")
        with self.repo.connection() as db:
            return self.repo.get(db, scope, identifier)

    def create(self, scope, data, *, idempotency_key=None, authority="untrusted"):
        with self.repo.connection(write=True) as db:
            return self._create(db, scope, data, idempotency_key=idempotency_key, authority=authority)

    def _create(self, db, scope, data, *, idempotency_key=None, authority="untrusted", enforce_quota=True):
        require(isinstance(data, MemoryInput), "invalid_input")
        require(authority in ("user", "untrusted"), "invalid_authority")
        now = self.now()
        # Validate original input, hash before resolving TTL so retries survive clock changes.
        data.validate(now)
        require(idempotency_key is None or text_ok(idempotency_key), "invalid_idempotency_key")
        fingerprint = sha256(encode({"data": asdict(data), "authority": authority}).encode()).hexdigest()
        if idempotency_key:
            row = db.execute(
                "SELECT payload_hash,memory_id FROM idempotency WHERE tenant_id=? AND user_id=? AND key=?",
                (scope.tenant_id, scope.user_id, idempotency_key),
            ).fetchone()
            if row:
                require(row["payload_hash"] == fingerprint, "idempotency_conflict")
                return self.repo.get(db, scope, row["memory_id"])
        if data.verification_status == "verified":
            require(authority == "user", "authority_required")
        old = None
        status = data.status
        if data.tier == "semantic":
            row = db.execute(
                "SELECT payload FROM memories WHERE tenant_id=? AND user_id=? AND tier='semantic' AND fact_key=? AND status='active' AND (expires_at IS NULL OR expires_at>?)",
                (scope.tenant_id, scope.user_id, data.fact_key, now.isoformat()),
            ).fetchone()
            if row:
                old = Memory.from_json(row["payload"])
                if authority != "user" or status == "candidate":
                    status = "candidate"
                else:
                    self.repo.save(
                        db, replace(old, status="superseded", version=old.version + 1, updated_at=now)
                    )
        self._expire(db, scope, now)
        ttl = self.policy.ttl_seconds[data.tier]
        expires = timestamp(data.expires_at) or (now + timedelta(seconds=ttl) if ttl else None)
        record = Memory(
            id=str(uuid4()),
            tenant_id=scope.tenant_id,
            user_id=scope.user_id,
            **{
                **asdict(data),
                "status": status,
                "occurred_at": timestamp(data.occurred_at),
                "expires_at": expires,
            },
            created_at=now,
            updated_at=now,
            version=1,
            supersedes_id=old.id if old and status == "active" else None,
            verified_at=now if data.verification_status == "verified" else None,
        )
        self.repo.save(db, record, new=True)
        self._link_sources(db, scope, record, now)
        if enforce_quota:
            self._quota(db, scope, record.tier, record.id)
        if idempotency_key:
            db.execute(
                "INSERT INTO idempotency VALUES (?,?,?,?,?)",
                (scope.tenant_id, scope.user_id, idempotency_key, fingerprint, record.id),
            )
        return record

    def _link_sources(self, db, scope, record, now):
        for ref in record.source_refs:
            if ref.startswith("memory:"):
                identifier = ref[7:]
                require(identifier != record.id, "source_cycle")
                source = self.repo.get(db, scope, identifier)
                require(
                    source.status == "active" and (source.expires_at is None or source.expires_at > now),
                    "source_unavailable",
                )
                require(self._sources_valid(db, scope, source, now, set()), "source_unavailable")
                require(record.id not in self._ancestors(db, identifier), "source_cycle")
                db.execute("INSERT OR IGNORE INTO dependencies VALUES (?,?)", (record.id, identifier))

    def _ancestors(self, db, identifier):
        # Transitive sources of `identifier`: everything it depends on. A record may not
        # depend on one of its own descendants.
        return {
            row[0]
            for row in db.execute(
                "WITH RECURSIVE parents(id) AS (SELECT source_id FROM dependencies WHERE derived_id=? "
                "UNION SELECT d.source_id FROM dependencies d JOIN parents p ON d.derived_id=p.id) "
                "SELECT id FROM parents",
                (identifier,),
            )
        }

    def update(self, scope, identifier, *, expected_version, changes, authority="untrusted"):
        require(type(expected_version) is int and expected_version > 0, "invalid_version")
        require(type(changes) is dict and bool(changes), "invalid_changes")
        allowed = {
            "content",
            "importance",
            "confidence",
            "metadata",
            "expires_at",
            "source_refs",
            "verification_status",
        }
        require(set(changes) <= allowed, "immutable_field")
        require(authority in ("user", "untrusted"), "invalid_authority")
        with self.repo.connection(write=True) as db:
            old = self.repo.get(db, scope, identifier)
            require(old.version == expected_version, "version_conflict")
            require(old.status != "superseded", "record_superseded")
            if old.verification_status == "verified" or changes.get("verification_status") == "verified":
                require(authority == "user", "authority_required")
            now = self.now()
            require(old.expires_at is None or old.expires_at > now, "record_expired")
            payload = {k: getattr(old, k) for k in MemoryInput.__dataclass_fields__}
            payload.update(changes)
            data = MemoryInput(**payload)
            data.validate(now)
            record = replace(
                old,
                **{**changes, "expires_at": timestamp(data.expires_at)},
                version=old.version + 1,
                updated_at=now,
                verified_at=(
                    now if data.verification_status == "verified" and authority == "user" else old.verified_at
                ),
            )
            # Derivatives of changed content must not survive as stale summaries.
            if old.content != record.content or old.source_refs != record.source_refs:
                for ref in record.source_refs:
                    if ref.startswith("memory:"):
                        # Reject a cycle before deleting descendants, otherwise the source is
                        # gone by relink time and the caller sees a confusing not_found.
                        require(identifier not in self._ancestors(db, ref[7:]), "source_cycle")
                descendants = [
                    r[0]
                    for r in db.execute(
                        "SELECT derived_id FROM dependencies WHERE source_id=?", (identifier,)
                    )
                ]
                self.repo.delete_ids(db, scope, descendants)
                db.execute(
                    "DELETE FROM operations WHERE tenant_id=? AND user_id=? AND operation_id IN (SELECT operation_id FROM operation_sources WHERE source_id=?)",
                    (scope.tenant_id, scope.user_id, identifier),
                )
            db.execute("DELETE FROM dependencies WHERE derived_id=?", (identifier,))
            self.repo.save(db, record)
            self._link_sources(db, scope, record, now)
            if old.content != record.content:
                db.execute("DELETE FROM embeddings WHERE memory_id=?", (identifier,))
            self._expire(db, scope, now)
            self._quota(db, scope, record.tier, record.id)
            return record

    def _quota(self, db, scope, tier, protected):
        protected = {protected} if isinstance(protected, str) else set(protected)
        args = (scope.tenant_id, scope.user_id, tier)

        def over():
            row = db.execute(
                "SELECT count(*),coalesce(sum(size_bytes),0) FROM memories WHERE tenant_id=? AND user_id=? AND tier=?",
                args,
            ).fetchone()
            history = db.execute(
                "SELECT coalesce(sum(length(CAST(v.payload AS BLOB))),0) FROM versions v JOIN memories m ON m.id=v.memory_id WHERE m.tenant_id=? AND m.user_id=? AND m.tier=?",
                args,
            ).fetchone()[0]
            return (
                row[0] > self.policy.max_records_per_tier
                or max(row[1], history) > self.policy.max_bytes_per_tier
            )

        if not over():
            return
        if self.policy.allow_eviction:
            self._prune_history(db, scope, tier)
            if not over():
                return
            victims = db.execute(
                "SELECT id FROM memories WHERE tenant_id=? AND user_id=? AND tier=? AND verification_status!='verified' AND importance<? AND id NOT IN ("
                + ",".join("?" for _ in protected)
                + ") ORDER BY importance,created_at,id",
                (*args, self.policy.eviction_importance, *sorted(protected)),
            ).fetchall()
            for victim in victims:
                # Never evict an ancestor of the new record or verified derivatives.
                descendants = db.execute(
                    "WITH RECURSIVE children(id) AS (SELECT derived_id FROM dependencies WHERE source_id=? UNION SELECT d.derived_id FROM dependencies d JOIN children c ON d.source_id=c.id) SELECT m.id,m.verification_status FROM memories m JOIN children c ON m.id=c.id",
                    (victim[0],),
                ).fetchall()
                if any(r[0] in protected or r[1] == "verified" for r in descendants):
                    continue
                self.repo.delete_ids(db, scope, [victim[0]])
                if not over():
                    return
        raise MemoryError("quota_exceeded")

    def _prune_history(self, db, scope, tier):
        # Version payloads are redundant history: the live record stays in memories.payload,
        # so reclaiming them never drops current data. Oldest rows go first. Without this a
        # single frequently-updated record eventually exceeds the byte quota on its own
        # superseded versions and can never be updated again, even with eviction enabled.
        args = (scope.tenant_id, scope.user_id, tier)
        total = (
            "SELECT coalesce(sum(length(CAST(v.payload AS BLOB))),0) FROM versions v "
            "JOIN memories m ON m.id=v.memory_id WHERE m.tenant_id=? AND m.user_id=? AND m.tier=?"
        )
        while db.execute(total, args).fetchone()[0] > self.policy.max_bytes_per_tier:
            removed = db.execute(
                "DELETE FROM versions WHERE rowid IN (SELECT v.rowid FROM versions v "
                "JOIN memories m ON m.id=v.memory_id WHERE m.tenant_id=? AND m.user_id=? AND m.tier=? "
                "ORDER BY v.rowid LIMIT 100)",
                args,
            ).rowcount
            if not removed:
                return

    def _sources_valid(self, db, scope, record, now, seen):
        if record.id in seen:
            return False
        seen = seen | {record.id}
        for row in db.execute("SELECT source_id FROM dependencies WHERE derived_id=?", (record.id,)):
            try:
                source = self.repo.get(db, scope, row[0])
            except MemoryError:
                return False
            if source.status != "active" or (source.expires_at and source.expires_at <= now):
                return False
            if not self._sources_valid(db, scope, source, now, seen):
                return False
        return True

    def candidates(self, scope, *, session_id=None, task_id=None, tier_filters=None, db=None):
        if db is None:
            with self.repo.connection() as conn:
                return self.candidates(
                    scope, session_id=session_id, task_id=task_id, tier_filters=tier_filters, db=conn
                )
        tiers = list(TIERS) if tier_filters is None else tier_filters
        require(
            type(tiers) is list and len(tiers) <= 3 and all(t in TIERS for t in tiers), "invalid_tier_filters"
        )
        for value in (session_id, task_id):
            require(value is None or text_ok(value), "invalid_identifier")
        if not tiers:
            return []
        now = self.now()
        sql = (
            "SELECT payload FROM memories WHERE tenant_id=? AND user_id=? AND status='active' AND (expires_at IS NULL OR expires_at>?) AND tier IN ("
            + ",".join("?" for _ in tiers)
            + ") AND (tier!='working' OR (session_id=? AND task_id=?)) ORDER BY id LIMIT ?"
        )
        rows = db.execute(
            sql,
            (
                scope.tenant_id,
                scope.user_id,
                now.isoformat(),
                *tiers,
                session_id,
                task_id,
                self.policy.max_candidates + 1,
            ),
        ).fetchall()
        # Bound scanned candidates by truncation rather than failing the whole search; a full
        # scope must stay searchable (order stays deterministic by id).
        records = [Memory.from_json(r[0]) for r in rows[: self.policy.max_candidates]]
        return [r for r in records if self._sources_valid(db, scope, r, now, set())]

    def validate_query(self, query, top_k):
        require(type(query) is str and len(utf8(query)) <= self.policy.max_query_bytes, "invalid_query")
        require(type(top_k) is int and 1 <= top_k <= self.policy.max_top_k, "invalid_top_k")

    def retrieve(self, scope, query, *, session_id=None, task_id=None, top_k=10, tier_filters=None):
        self.validate_query(query, top_k)
        if not query.strip() and not (tier_filters == ["working"] and session_id and task_id):
            return []
        records = self.candidates(scope, session_id=session_id, task_id=task_id, tier_filters=tier_filters)
        results = []
        now = self.now()
        for record in records:
            relevance = lexical(query, record.content) if query.strip() else 1.0
            if relevance >= self.policy.min_relevance:
                results.append(
                    scored(
                        record,
                        relevance,
                        now,
                        self.policy,
                        "lexical_match" if query.strip() else "explicit_working_state",
                    )
                )
        return sorted(results, key=lambda r: (-r.final_score, r.id))[:top_k]

    def _expire(self, db, scope, now):
        ids = [
            r[0]
            for r in db.execute(
                "SELECT id FROM memories WHERE tenant_id=? AND user_id=? AND expires_at<=?",
                (scope.tenant_id, scope.user_id, now.isoformat()),
            )
        ]
        return self.repo.delete_ids(db, scope, ids)

    def expire(self, scope):
        with self.repo.connection(write=True) as db:
            return self._expire(db, scope, self.now())

    def delete_memory(self, scope, identifier):
        with self.repo.connection(write=True) as db:
            self.repo.get(db, scope, identifier)
            return self.repo.delete_ids(db, scope, [identifier])

    def delete_user_data(self, scope):
        with self.repo.connection(write=True) as db:
            ids = [
                r[0]
                for r in db.execute(
                    "SELECT id FROM memories WHERE tenant_id=? AND user_id=?",
                    (scope.tenant_id, scope.user_id),
                )
            ]
            count = self.repo.delete_ids(db, scope, ids)
            db.execute(
                "DELETE FROM operations WHERE tenant_id=? AND user_id=?", (scope.tenant_id, scope.user_id)
            )
            return count
