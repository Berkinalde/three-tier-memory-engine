CREATE TABLE IF NOT EXISTS memories (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, user_id TEXT NOT NULL,
 tier TEXT NOT NULL, status TEXT NOT NULL, expires_at TEXT,
 session_id TEXT, task_id TEXT, fact_key TEXT, importance REAL NOT NULL,
 verification_status TEXT NOT NULL, created_at TEXT NOT NULL,
 payload TEXT NOT NULL, size_bytes INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS scope_lookup ON memories(tenant_id,user_id,status,tier,expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS active_fact ON memories(tenant_id,user_id,fact_key)
 WHERE tier='semantic' AND status='active';
CREATE TABLE IF NOT EXISTS versions (
 memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 version INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(memory_id,version)
);
CREATE TABLE IF NOT EXISTS idempotency (
 tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, key TEXT NOT NULL, payload_hash TEXT NOT NULL,
 memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 PRIMARY KEY(tenant_id,user_id,key)
);
CREATE TABLE IF NOT EXISTS dependencies (
 derived_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 source_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 PRIMARY KEY(derived_id,source_id)
);
CREATE INDEX IF NOT EXISTS dependent_lookup ON dependencies(source_id);
CREATE TABLE IF NOT EXISTS embeddings (
 memory_id TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
 model_id TEXT NOT NULL, model_version TEXT NOT NULL, dimension INTEGER NOT NULL,
 content_hash TEXT NOT NULL, vector TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operations (
 tenant_id TEXT NOT NULL,user_id TEXT NOT NULL,operation_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL, result TEXT NOT NULL,
 PRIMARY KEY(tenant_id,user_id,operation_id)
);
CREATE TABLE IF NOT EXISTS operation_sources (
 tenant_id TEXT NOT NULL,user_id TEXT NOT NULL,operation_id TEXT NOT NULL,
 source_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 PRIMARY KEY(tenant_id,user_id,operation_id,source_id),
 FOREIGN KEY(tenant_id,user_id,operation_id) REFERENCES operations(tenant_id,user_id,operation_id) ON DELETE CASCADE
);
PRAGMA user_version = 1;
