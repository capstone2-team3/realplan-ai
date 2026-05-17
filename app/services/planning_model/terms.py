"""응답에 포함할 term payload 생성."""

from __future__ import annotations


def _term(term: str, key: str, weight: float, reliability: float, contribution: float) -> dict:
    return {
        "term": term,
        "key": key,
        "weight": weight,
        "reliability": reliability,
        "contribution": contribution,
    }


def _updated_term(
    term: str,
    key: str,
    old_weight: float,
    new_weight: float,
    update_method: str,
    reliability: float | None = None,
    **extra: float,
) -> dict:
    out = {
        "term": term,
        "key": key,
        "oldWeight": old_weight,
        "newWeight": new_weight,
        "delta": new_weight - old_weight,
        "updateMethod": update_method,
    }
    if reliability is not None:
        out["reliability"] = reliability
    out.update(extra)
    return out
