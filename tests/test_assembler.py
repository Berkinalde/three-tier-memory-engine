import pytest

pytest.importorskip(
    "context_assembler",
    reason="integration test needs the optional dynamic-context-assembler package",
)

from context_assembler.assembler import assemble
from context_assembler.counters import ApproximateCounter
from memory_engine.adapters.context_assembler import assemble_memories
from memory_engine.models import RetrievalResult


def results():
    return [
        RetrievalResult(
            str(i),
            "semantic",
            "Türkçe tercih " + ("uzun bilgi " * 40),
            ["event:" + str(i)],
            0.9,
            1,
            0.5,
            0.86,
            "lexical_match",
        )
        for i in range(4)
    ]


def test_actual_assembler_budget_and_provenance():
    rows = results()
    output = assemble_memories(rows, query="Tercihim ne?", budget={"context_window": 350}, assembler=assemble)
    request = output["assembly"]["assembled_request"]
    assert ApproximateCounter().count_request(request) <= 350
    assert 0 < len(output["selected"]) < 4
    assert len(output["dropped"]) > 0
    assert output["retrieved"] == ["0", "1", "2", "3"]
    for item in request["working_memory"]:
        assert item["required"] is False
        assert item["source_refs"] == output["source_mapping"][item["id"]]["source_refs"]
        assert item["tier"] == "semantic"
        assert item["importance"] == 0.86


def test_adapter_limits_and_reasons():
    out = assemble_memories(
        results(), query="q", budget={"context_window": 1000}, assembler=assemble, max_items=1, max_bytes=900
    )
    assert len(out["selected"]) == 1
    assert {r["reason"] for r in out["dropped"]} == {"adapter_item_limit"}
    out = assemble_memories(
        results(), query="q", budget={"context_window": 1000}, assembler=assemble, max_bytes=1
    )
    assert out["selected"] == []
    assert all(r["reason"] == "adapter_byte_limit" for r in out["dropped"])
