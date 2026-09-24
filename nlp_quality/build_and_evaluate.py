"""Build validated phrase artifacts and evaluate them through production scoring."""

from __future__ import annotations

import argparse
import copy
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app
import nlp_helpers
try:
    from .utterance_spec import GENERALIZERS, HARD_NEGATIVES, UTTERANCES
except ImportError:  # Direct script execution.
    from utterance_spec import GENERALIZERS, HARD_NEGATIVES, UTTERANCES


ALWAYS = ["greeting", "thanks", "help"]
SUBJECTS = ["biology", "chemistry", "computer science", "english", "hindi",
            "mathematics", "math", "maths", "physics", "science", "social studies"]


def role_groups():
    groups = {role: list(intents) + ALWAYS for role, intents in app.ROLE_PERSONAL_INTENTS.items()}
    groups["vice_principal"] = list(app.ROLE_PERSONAL_INTENTS["hod"]) + app.VP_ONLY_INTENTS + ALWAYS
    return groups


def role_for_intent(intent, groups):
    preferred = ["student", "teacher", "hod", "principal", "vice_principal"]
    return next(role for role in preferred if intent in groups[role])


def set_cache(phrases):
    nlp_helpers._phrase_cache["data"] = {name: list(values) for name, values in phrases.items()}
    nlp_helpers._phrase_cache["loaded_at"] = float("inf")


def rank(question, role, groups):
    ranked = nlp_helpers.rank_intents(question, groups[role], top_n=len(groups[role]))
    original = app._known_subject_names
    try:
        app._known_subject_names = lambda: SUBJECTS
        ranked = app._apply_subject_scoring_adjustment(ranked, question)
    finally:
        app._known_subject_names = original
    return ranked


def outcome(question, expected, role, groups):
    start = time.perf_counter()
    ranked = rank(question, role, groups)
    elapsed = (time.perf_counter() - start) * 1000
    if not ranked or ranked[0][1] < app.NLP_SCORE_FLOOR:
        return "NO_MATCH", None, 0, 0, 0, ranked, elapsed
    top_name, top_score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    margin = top_score - second
    if len(ranked) > 1 and margin < app.NLP_MARGIN_THRESHOLD:
        label = "TIE" if expected in {ranked[0][0], ranked[1][0]} else "WRONG"
    else:
        label = "CORRECT" if top_name == expected else "WRONG"
    return label, top_name, top_score, second, margin, ranked, elapsed


def near_duplicate(phrase, existing):
    normalized = nlp_helpers.clean_question(phrase)
    best = (0.0, None)
    for old in existing:
        old_normalized = nlp_helpers.clean_question(old)
        ratio = SequenceMatcher(None, normalized, old_normalized).ratio()
        if ratio > best[0]:
            best = (ratio, old)
    return best


def synthesize(records):
    transforms = [
        lambda text: text.upper(),
        lambda text: text.capitalize() + "?",
        lambda text: "please " + text,
        lambda text: "can you " + text,
        lambda text: "  " + text.replace(" ", "   ") + "  ",
        lambda text: text.replace("'", ""),
        lambda text: text.replace("timetable", "time table").replace("mathematics", "maths"),
        lambda text: text.replace("teacher", "techer", 1).replace("attendance", "attendence", 1),
    ]
    result = []
    seen = set()
    index = 0
    while len(result) < 1000:
        source = records[index % len(records)]
        transform = transforms[(index // len(records)) % len(transforms)]
        text = transform(source["text"])
        key = (source["role"], source["intent"], text)
        if key not in seen:
            seen.add(key)
            result.append({**source, "text": text, "category": "synthetic_unseen"})
        index += 1
        if index > len(records) * len(transforms) * 3:
            raise RuntimeError("Could not produce 1,000 unique synthetic queries")
    return result


def evaluate(records, phrases, groups):
    set_cache(phrases)
    counts = Counter()
    per_intent = defaultdict(Counter)
    confusion = Counter()
    latencies = []
    details = []
    for record in records:
        result = outcome(record["text"], record["intent"], record["role"], groups)
        label, predicted, top, second, margin, ranked, elapsed = result
        counts[label] += 1
        per_intent[record["intent"]][label] += 1
        if label == "WRONG":
            confusion[(record["intent"], predicted or "NO_MATCH")] += 1
        latencies.append(elapsed)
        details.append({**record, "outcome": label, "predicted": predicted,
                        "top_score": top, "second_score": second, "margin": margin,
                        "ranked": ranked[:3], "latency_ms": elapsed})
    total = len(records)
    ordered = sorted(latencies)
    return {
        "total": total,
        "accuracy": counts["CORRECT"] / total,
        "tie_rate": counts["TIE"] / total,
        "clarification_rate": counts["TIE"] / total,
        "no_match_rate": counts["NO_MATCH"] / total,
        "wrong_intent_rate": counts["WRONG"] / total,
        "counts": dict(counts),
        "per_intent": {name: dict(values) for name, values in sorted(per_intent.items())},
        "confusion": [{"expected": pair[0], "predicted": pair[1], "count": count}
                      for pair, count in confusion.most_common()],
        "latency_ms": {"average": statistics.mean(latencies),
                       "p95": ordered[max(0, int(total * .95) - 1)], "maximum": max(latencies)},
        "details": details,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("nlp_quality"))
    args = parser.parse_args()
    args.output_dir.mkdir(exist_ok=True)
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    base = defaultdict(list)
    for row in snapshot["rows"]:
        base[row["intent_name"]].append(row["phrase"])
    missing_db_intents = sorted(set(nlp_helpers.INTENT_DATA) - set(base))
    groups = role_groups()

    candidates = []
    accepted = defaultdict(list)
    for intent, values in UTTERANCES.items():
        role = role_for_intent(intent, groups)
        training_phrases = values["candidate"] + [value.strip() for value in GENERALIZERS[intent].split("|")]
        for phrase in training_phrases:
            duplicate_ratio, duplicate_phrase = near_duplicate(phrase, base[intent] + accepted[intent])
            trial = {name: list(items) for name, items in base.items()}
            for name, items in accepted.items():
                trial.setdefault(name, []).extend(items)
            trial.setdefault(intent, []).append(phrase)
            set_cache(trial)
            label, predicted, top, second, margin, ranked, _ = outcome(phrase, intent, role, groups)
            role_sets = [set(group) for group in groups.values() if intent in group]
            status, safety_reason = nlp_helpers.check_phrase_safety(
                phrase, intent,
                same_role_intents=set().union(*role_sets) if role_sets else {intent},
                role_groups=role_sets,
            )
            if duplicate_ratio == 1.0:
                classification = "REJECT"
                reason = f"near duplicate ({duplicate_ratio:.3f}) of {duplicate_phrase!r}"
            elif status != "safe" or label == "WRONG":
                classification = "REJECT"
                reason = safety_reason or f"predicted {predicted!r}"
            elif label == "TIE" or margin < app.NLP_MARGIN_THRESHOLD:
                classification = "AMBIGUOUS"
                reason = f"margin {margin}; ranked {ranked[:3]}"
            elif label == "CORRECT":
                classification = "SAFE"
                reason = safety_reason
                accepted[intent].append(phrase)
            else:
                classification = "REJECT"
                reason = label
            candidates.append({"intent": intent, "role": role, "phrase": phrase,
                               "category": "generated_candidate", "classification": classification,
                               "predicted": predicted, "top_score": top, "second_score": second,
                               "margin": margin, "near_duplicate_ratio": duplicate_ratio,
                               "reason": reason})

    # Seed phrases for code intents absent from the DB are validated through the
    # same cumulative router before promotion.
    for intent in missing_db_intents:
        role = role_for_intent(intent, groups)
        for phrase in nlp_helpers.INTENT_DATA[intent]["phrases"]:
            trial = {name: list(items) for name, items in base.items()}
            for name, items in accepted.items():
                trial.setdefault(name, []).extend(items)
            trial.setdefault(intent, []).append(phrase)
            set_cache(trial)
            label, predicted, top, second, margin, ranked, _ = outcome(phrase, intent, role, groups)
            classification = "SAFE" if label == "CORRECT" and margin >= app.NLP_MARGIN_THRESHOLD else "AMBIGUOUS"
            if classification == "SAFE":
                accepted[intent].append(phrase)
            candidates.append({"intent": intent, "role": role, "phrase": phrase,
                               "category": "missing_db_seed", "classification": classification,
                               "predicted": predicted, "top_score": top, "second_score": second,
                               "margin": margin, "near_duplicate_ratio": 0, "reason": "restore code seed to DB"})

    final_phrases = {name: list(items) for name, items in base.items()}
    for name, items in accepted.items():
        final_phrases.setdefault(name, []).extend(items)

    held_out = [{"intent": intent, "role": role_for_intent(intent, groups), "text": text,
                 "category": "held_out"}
                for intent, values in UTTERANCES.items() for text in values["held_out"]]
    hard_negatives = [{"role": role, "intent": intent, "text": text, "category": "hard_negative"}
                      for role, intent, text in HARD_NEGATIVES]

    # Permanent golden set: stable, high-margin production phrases plus the
    # explicit hard-negative boundaries.  No generated candidate is eligible.
    golden = []
    set_cache(base)
    for intent, phrases in sorted(base.items()):
        role = role_for_intent(intent, groups)
        for phrase in phrases:
            label, _, _, _, margin, _, _ = outcome(phrase, intent, role, groups)
            if label == "CORRECT" and margin >= app.NLP_MARGIN_THRESHOLD:
                golden.append({"role": role, "intent": intent, "text": phrase, "category": "production_golden"})
                if sum(item["intent"] == intent for item in golden) >= 10:
                    break
    golden.extend(hard_negatives)

    source_for_synthetic = held_out + hard_negatives + golden
    synthetic = synthesize(source_for_synthetic)
    report = {
        "candidate_counts": dict(Counter(item["classification"] for item in candidates)),
        "candidate_total": len(candidates),
        "approved_total": sum(len(items) for items in accepted.values()),
        "held_out_before": evaluate(held_out, base, groups),
        "held_out_after": evaluate(held_out, final_phrases, groups),
        "hard_negatives_before": evaluate(hard_negatives, base, groups),
        "hard_negatives_after": evaluate(hard_negatives, final_phrases, groups),
        "golden_before": evaluate(golden, base, groups),
        "golden_after": evaluate(golden, final_phrases, groups),
        "synthetic_after": evaluate(synthetic, final_phrases, groups),
        "phrase_counts_before": {name: len(items) for name, items in sorted(base.items())},
        "phrase_counts_after": {name: len(items) for name, items in sorted(final_phrases.items())},
    }
    approved = [{"intent": name, "phrase": phrase, "source": "manual",
                 "added_by": "nlp-quality-2026-09-25"}
                for name, items in sorted(accepted.items()) for phrase in items]
    report_artifact = copy.deepcopy(report)
    for section in ("held_out_before", "held_out_after", "hard_negatives_before",
                    "hard_negatives_after", "golden_before", "golden_after", "synthetic_after"):
        details = report_artifact[section].pop("details")
        report_artifact[section]["failures"] = [row for row in details if row["outcome"] != "CORRECT"]

    for name, payload in (("candidates.json", candidates), ("approved_phrases.json", approved),
                          ("held_out.json", held_out), ("golden_set.json", golden),
                          ("synthetic_1000.json", synthetic), ("evaluation_report.json", report_artifact)):
        (args.output_dir / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    concise = {key: report[key] for key in ("candidate_counts", "candidate_total", "approved_total")}
    for key in ("held_out_before", "held_out_after", "hard_negatives_before", "hard_negatives_after",
                "golden_before", "golden_after", "synthetic_after"):
        concise[key] = {metric: report[key][metric] for metric in
                        ("total", "accuracy", "tie_rate", "no_match_rate", "wrong_intent_rate", "latency_ms")}
    print(json.dumps(concise, indent=2))


if __name__ == "__main__":
    main()
