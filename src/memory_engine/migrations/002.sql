CREATE TABLE IF NOT EXISTS operation_outputs (
 tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, operation_id TEXT NOT NULL,
 memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 PRIMARY KEY(tenant_id,user_id,operation_id,memory_id),
 FOREIGN KEY(tenant_id,user_id,operation_id) REFERENCES operations(tenant_id,user_id,operation_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS operation_output_lookup ON operation_outputs(memory_id);
INSERT OR IGNORE INTO operation_outputs(tenant_id,user_id,operation_id,memory_id)
 SELECT o.tenant_id,o.user_id,o.operation_id,m.id FROM operations o
 JOIN json_each(CASE WHEN json_valid(o.result) THEN o.result ELSE '[]' END) output
 JOIN memories m ON m.id=output.value AND m.tenant_id=o.tenant_id AND m.user_id=o.user_id;
PRAGMA user_version = 2;
