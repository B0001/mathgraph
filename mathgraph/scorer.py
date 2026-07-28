#!/usr/bin/env python3
"""Score a predictions file against tasks.jsonl. Stdlib only.

usage: python scorer.py tasks.jsonl predictions.jsonl
predictions rows: {"id": <task id>, "prediction": <declaration name or null>}
"""
import json, sys

def main(tasks_path, preds_path):
    tasks = {t["id"]: t for t in map(json.loads, open(tasks_path, encoding="utf-8"))}
    preds = {}
    for row in map(json.loads, open(preds_path, encoding="utf-8")):
        preds[row["id"]] = row.get("prediction")

    tp = fp = abstain_pos = 0          # present arm
    neg_ok = neg_bad = 0               # absent arm
    missing = 0
    for tid, t in tasks.items():
        p = preds.get(tid, None)
        if tid not in preds:
            missing += 1
        if t["arm"] == "present":
            if p is None:
                abstain_pos += 1
            elif p in t["gold"]:
                tp += 1
            else:
                fp += 1
        else:
            if p is None:
                neg_ok += 1
            else:
                neg_bad += 1

    answered = tp + fp + neg_bad
    out = {
        "n_present": tp + fp + abstain_pos,
        "n_absent": neg_ok + neg_bad,
        "precision": round(tp / answered, 4) if answered else None,
        "recall": round(tp / max(1, tp + fp + abstain_pos), 4),
        "answer_rate_present": round((tp + fp) / max(1, tp + fp + abstain_pos), 4),
        "false_match_rate_absent": round(neg_bad / max(1, neg_ok + neg_bad), 4),
        "missing_predictions": missing,
    }
    print(json.dumps(out, indent=2))
    return out

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
