"""Run with PYTHONPATH=src:../dynamic-context-assembler/src python examples/two_sessions.py."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from memory_engine import MemoryService, Repository, Scope
from memory_engine.adapters.context_assembler import assemble_memories
from memory_engine.models import encode


def main():
    with tempfile.TemporaryDirectory() as directory:
        db = str(Path(directory) / "demo.db")
        prefix = [sys.executable, "-m", "memory_engine", "--db", db, "--tenant", "demo", "--user", "learner"]
        records = [
            {
                "tier": "working",
                "content": "AWS IAM: üç alıştırmadan ikisi tamamlandı",
                "session_id": "A",
                "task_id": "aws",
            },
            {
                "tier": "episodic",
                "content": "AWS IAM policy evaluation çalışıldı; explicit deny tekrar edilecek",
                "source_refs": ["event:session-A"],
            },
            {
                "tier": "semantic",
                "content": "AWS açıklamalarında Türkçe ve somut örnekler tercih ediliyor",
                "fact_key": "language",
                "source_refs": ["event:preference"],
            },
        ]
        ids = []
        for record in records:
            output = subprocess.run(
                prefix + ["create"],
                input=json.dumps(record),
                text=True,
                capture_output=True,
                check=True,
                env=os.environ,
            )
            ids.append(json.loads(output.stdout)["id"])
        # These child writers have exited; session B opens persisted SQLite state.
        engine = MemoryService(Repository(db))
        scope = Scope("demo", "learner")
        results = engine.retrieve(scope, "AWS", session_id="B", task_id="aws")
        assert ids[0] not in {r.id for r in results}
        assert {r.id for r in results} == set(ids[1:])
        output = assemble_memories(
            results, query="AWS konusundan devam edelim", budget={"context_window": 135}
        )
        assert output["assembly"]["report"]["used_input_tokens"] <= 135
        assert output["selected"] and output["dropped"]
        engine.delete_memory(scope, ids[1])
        assert ids[1] not in {r.id for r in engine.retrieve(scope, "AWS")}
        print(
            encode(
                {
                    "session_B": output,
                    "restart_verified": True,
                    "working_isolated": True,
                    "delete_verified": True,
                }
            )
        )


if __name__ == "__main__":
    main()
