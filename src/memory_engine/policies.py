from dataclasses import dataclass, field
from .models import TIERS, require
import math


@dataclass(frozen=True)
class Policy:
    ttl_seconds: dict = field(
        default_factory=lambda: {"working": 86400, "episodic": 7776000, "semantic": None}
    )
    half_life_days: dict = field(
        default_factory=lambda: {"working": 1.0, "episodic": 30.0, "semantic": 180.0}
    )
    min_relevance: float = 0.05
    max_records_per_tier: int = 1000
    max_bytes_per_tier: int = 4_194_304
    max_candidates: int = 3000
    max_top_k: int = 100
    max_query_bytes: int = 4096
    allow_eviction: bool = False
    eviction_importance: float = 0.3

    def __post_init__(self):
        for v in (
            self.max_records_per_tier,
            self.max_bytes_per_tier,
            self.max_candidates,
            self.max_top_k,
            self.max_query_bytes,
        ):
            require(type(v) is int and v > 0, "invalid_policy")
        require(
            set(self.ttl_seconds) == set(TIERS) and set(self.half_life_days) == set(TIERS), "invalid_policy"
        )
        for v in self.half_life_days.values():
            require(type(v) in (int, float) and math.isfinite(v) and v > 0, "invalid_policy")
        for v in self.ttl_seconds.values():
            require(v is None or type(v) is int and 0 < v <= 315360000, "invalid_policy")
        for v in (self.min_relevance, self.eviction_importance):
            require(type(v) in (int, float) and math.isfinite(v) and 0 < v <= 1, "invalid_policy")
