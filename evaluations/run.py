"""Reproducible synthetic retrieval/assembly/extraction evaluation; no network calls."""

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import platform
import statistics
import tempfile
import time
from memory_engine import MemoryInput, MemoryService, Repository, Scope, MemoryError
from memory_engine.adapters.context_assembler import assemble_memories
from memory_engine.adapters.embeddings import EmbeddingIndex, HashEmbedder
from memory_engine.adapters.extraction import ExtractionService
from memory_engine.models import encode


def evaluate():
    corpus = json.loads(Path(__file__).with_name("corpus-v1.json").read_text())
    with tempfile.TemporaryDirectory() as directory:
        clock = [datetime(2026, 10, 19, tzinfo=timezone.utc)]
        service = MemoryService(Repository(Path(directory) / "eval.db"), clock=lambda: clock[0])
        scope = Scope("eval", "learner")
        labels, id_labels = {}, {}
        for row in corpus["records"]:
            clock[0] += timedelta(milliseconds=1)
            data = {
                k: row[k]
                for k in ("tier", "content", "fact_key", "importance", "session_id", "task_id")
                if k in row
            }
            data["source_refs"] = ["fixture:" + row["label"]]
            if "age_days" in row:
                data["occurred_at"] = clock[0] - timedelta(days=row["age_days"])
            if row.get("expire"):
                data["expires_at"] = clock[0] + timedelta(seconds=1)
            if row.get("verified"):
                data["verification_status"] = "verified"
            own = Scope(row.get("tenant_id", "eval"), row.get("user_id", "learner"))
            record = service.create(
                own, MemoryInput(**data), authority="user" if row.get("verified") else "untrusted"
            )
            labels[row["label"]], id_labels[record.id] = record.id, row["label"]
            if row.get("delete"):
                service.delete_memory(own, record.id)
        clock[0] += timedelta(seconds=2)
        filters = {"session_id": "B", "task_id": "aws"}
        index = EmbeddingIndex(service, HashEmbedder())
        index.index_scope(scope, **filters)
        methods = {
            "lexical": lambda query: service.retrieve(scope, query, top_k=3, **filters),
            "hybrid_fake": lambda query: index.retrieve(scope, query, top_k=3, **filters),
        }
        result = {
            "dataset": corpus["version"],
            "record_count": len(corpus["records"]),
            "query_count": len(corpus["queries"]),
            "k": 3,
            "seed": 42,
            "environment": {"python": platform.python_version(), "platform": platform.platform()},
            "method": "50 repeats/query, perf_counter, warm local SQLite; p95 nearest-rank; precision denominator k=3; recall positive queries only",
            "methods": {},
            "live_provider_tested": False,
        }
        forbidden = {
            "other-user",
            "other-tenant",
            "expired",
            "deleted",
            "old-level",
            "language-conflict",
            "working-A",
        }
        for name in ["lexical", "hybrid_fake", "newest_first"]:
            details, times, precisions, recalls = [], [], [], []
            false_recall, unrelated, isolation, lifecycle = 0, 0, 0, 0
            for query in corpus["queries"]:
                expected = set(query["expected"])
                for _ in range(50):
                    start = time.perf_counter()
                    if name == "newest_first":
                        rows = sorted(
                            service.candidates(scope, **filters),
                            key=lambda r: (-r.created_at.timestamp(), r.id),
                        )[:3]
                    else:
                        rows = methods[name](query["query"])
                    times.append((time.perf_counter() - start) * 1000)
                names = [id_labels[r.id] for r in rows]
                hits = len(set(names) & expected)
                precisions.append(hits / 3)
                if expected:
                    recalls.append(hits / len(expected))
                else:
                    unrelated += 1
                    false_recall += bool(names)
                isolation += sum(n in {"other-user", "other-tenant", "working-A"} for n in names)
                lifecycle += sum(n in forbidden - {"other-user", "other-tenant", "working-A"} for n in names)
                details.append({"query": query["query"], "expected": sorted(expected), "returned": names})
            result["methods"][name] = {
                "precision_at_3": statistics.mean(precisions),
                "recall_at_3_positive_queries": statistics.mean(recalls),
                "unrelated_false_recall_rate": false_recall / unrelated,
                "isolation_violations": isolation,
                "lifecycle_violations": lifecycle,
                "p50_ms": statistics.median(times),
                "p95_ms": sorted(times)[int(0.95 * len(times)) - 1],
                "timed_calls": len(times),
                "queries": details,
            }
        rows = service.retrieve(scope, "AWS IAM policy", top_k=3, **filters)
        assembly = assemble_memories(rows, query="AWS IAM konusundan devam", budget={"context_window": 135})
        result["assembly"] = {
            "selected": [id_labels[i] for i in assembly["selected"]],
            "dropped": [{"label": id_labels[d["id"]], "reason": d["reason"]} for d in assembly["dropped"]],
            "used_tokens": assembly["assembly"]["report"]["used_input_tokens"],
            "budget": 135,
            "counter": assembly["assembly"]["report"]["counter"],
        }
        # Synthetic output oracle, not live-model/human quality measurement.
        source = service.get(scope, labels["language"])

        class Mock:
            model_id = "evaluation-mock-v1"

            def __init__(self, text):
                self.text = text

            async def extract(self, request, *, max_output_tokens):
                return json.dumps({"summary": {"content": self.text, "source_ids": [source.id]}, "facts": []})

        accepted = rejected = 0
        for i, text in enumerate([source.content, "Kullanıcı Japonca tercih ediyor"]):
            try:
                asyncio.run(
                    ExtractionService(service, Mock(text), enabled=True).process(
                        scope, source_ids=[source.id], operation_id=f"eval-{i}"
                    )
                )
                accepted += 1
            except MemoryError:
                rejected += 1
        result["extraction"] = {
            "oracle": "exact-source synthetic labels; no independent human/live evaluation",
            "supported_outputs_accepted": accepted,
            "fabricated_outputs_rejected": rejected,
            "supported_acceptance_rate": accepted / 1,
            "fabrication_acceptance_rate": (1 - rejected) / 1,
            "supported_omission_rate": (1 - accepted) / 1,
            "cases": 2,
        }
        assert all(
            m["isolation_violations"] == m["lifecycle_violations"] == 0 for m in result["methods"].values()
        )
        assert result["assembly"]["used_tokens"] <= 135
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evaluations/results-v1.json")
    args = parser.parse_args()
    result = evaluate()
    Path(args.output).write_text(encode(result) + "\n")
    print(
        json.dumps(
            {
                name: {k: v for k, v in data.items() if k != "queries"}
                for name, data in result["methods"].items()
            },
            indent=2,
        )
    )
