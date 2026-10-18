import re
import unicodedata
from .models import RetrievalResult


def tokens(text):
    # Turkish dotted I + Unicode NFC. No stemming, synonyms or semantic claim.
    return set(
        re.findall(r"\w+", unicodedata.normalize("NFC", text).replace("İ", "i").replace("I", "ı").casefold())
    )


def lexical(query, content):
    q = tokens(query)
    return len(q & tokens(content)) / len(q) if q else 0.0


def scored(record, relevance, now, policy, reason="lexical_match"):
    when = (
        record.updated_at
        if record.tier == "working"
        else (
            (record.occurred_at or record.created_at)
            if record.tier == "episodic"
            else (record.verified_at or record.created_at)
        )
    )
    age = max(0.0, (now - when).total_seconds() / 86400)
    recency = 2 ** (-age / policy.half_life_days[record.tier])
    score = 0.6 * relevance + 0.25 * recency + 0.15 * record.importance
    return RetrievalResult(
        record.id,
        record.tier,
        record.content,
        record.source_refs,
        relevance,
        recency,
        record.importance,
        score,
        reason,
    )
