"""Capture reproducible, read-only metrics for an intent phrase snapshot."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app
import nlp_helpers


ALWAYS = ["greeting", "thanks", "help"]


def _role_groups():
    groups = {role: list(intents) + ALWAYS for role, intents in app.ROLE_PERSONAL_INTENTS.items()}
    groups["vice_principal"] = list(app.ROLE_PERSONAL_INTENTS["hod"]) + app.VP_ONLY_INTENTS + ALWAYS
    return groups


def capture(snapshot_path: Path) -> dict:
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    rows = snapshot["rows"]
    phrases = defaultdict(list)
    for row in rows:
        phrases[row["intent_name"]].append(row["phrase"])

    nlp_helpers._phrase_cache["data"] = dict(phrases)
    nlp_helpers._phrase_cache["loaded_at"] = float("inf")

    groups = _role_groups()
    roles_for = defaultdict(list)
    for role, intents in groups.items():
        for intent in intents:
            roles_for[intent].append(role)

    outcomes = Counter()
    competing = Counter()
    failures = []
    latencies = []
    for row in rows:
        intended = row["intent_name"]
        role = roles_for[intended][0]
        start = time.perf_counter()
        ranked = nlp_helpers.rank_intents(row["phrase"], groups[role], top_n=len(groups[role]))
        latencies.append((time.perf_counter() - start) * 1000)
        if not ranked:
            outcomes["no_match"] += 1
            failures.append({"intent": intended, "phrase": row["phrase"], "outcome": "no_match"})
            continue
        margin = ranked[0][1] - (ranked[1][1] if len(ranked) > 1 else 0)
        if len(ranked) > 1 and margin < app.NLP_MARGIN_THRESHOLD:
            outcomes["near_tie"] += 1
            competing[tuple(sorted((ranked[0][0], ranked[1][0])))] += 1
        if ranked[0][0] == intended:
            outcomes["correct"] += 1
        else:
            outcomes["wrong"] += 1
            failures.append({
                "intent": intended,
                "phrase": row["phrase"],
                "outcome": "wrong",
                "ranked": ranked[:3],
            })

    normalized = Counter(nlp_helpers.clean_question(row["phrase"]) for row in rows)
    duplicates = {phrase: count for phrase, count in normalized.items() if count > 1}
    total = len(rows)
    ordered_latency = sorted(latencies)
    return {
        "snapshot": str(snapshot_path),
        "intent_count_in_db": len(phrases),
        "intent_count_in_code": len(nlp_helpers.INTENT_DATA),
        "missing_db_intents": sorted(set(nlp_helpers.INTENT_DATA) - set(phrases)),
        "total_phrases": total,
        "phrases_per_intent": dict(sorted((name, len(values)) for name, values in phrases.items())),
        "normalized_duplicate_groups": duplicates,
        "self_route": {
            **outcomes,
            "accuracy": outcomes["correct"] / total,
            "tie_rate": outcomes["near_tie"] / total,
            "no_match_rate": outcomes["no_match"] / total,
            "wrong_rate": outcomes["wrong"] / total,
        },
        "most_frequent_competing_pairs": [
            {"intents": list(pair), "count": count} for pair, count in competing.most_common(20)
        ],
        "routing_latency_ms": {
            "average": statistics.mean(latencies),
            "p95": ordered_latency[max(0, int(len(ordered_latency) * 0.95) - 1)],
            "maximum": max(latencies),
        },
        "failures": failures,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = capture(args.snapshot)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "intent_count_in_db", "intent_count_in_code", "missing_db_intents",
        "total_phrases", "self_route", "routing_latency_ms",
    )}, indent=2))


if __name__ == "__main__":
    main()
