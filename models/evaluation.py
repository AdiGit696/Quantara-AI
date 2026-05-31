import json
import time
from pathlib import Path


EVAL_DIR = Path(__file__).resolve().parent.parent / ".quantara" / "evaluation"
EVAL_DIR.mkdir(parents=True, exist_ok=True)
EVAL_FILE = EVAL_DIR / "model_results.jsonl"


def record_prediction(ticker, decision, entry, target, stop_loss, score, horizon_days=30):
    payload = {
        "created_at": time.time(),
        "ticker": ticker,
        "decision": decision,
        "entry": float(entry or 0),
        "target": float(target or 0),
        "stop_loss": float(stop_loss or 0),
        "score": float(score or 0),
        "horizon_days": int(horizon_days),
        "outcome": None,
    }
    with EVAL_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    return payload


def load_predictions():
    if not EVAL_FILE.exists():
        return []
    rows = []
    for line in EVAL_FILE.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def evaluate_predictions(rows=None):
    rows = rows if rows is not None else load_predictions()
    completed = [row for row in rows if row.get("outcome")]
    if not completed:
        return {
            "prediction_accuracy": None,
            "target_hit_rate": None,
            "stoploss_hit_rate": None,
            "decision_accuracy": None,
            "buy_vs_avoid_success_rate": None,
            "sample_size": 0,
        }

    target_hits = sum(1 for row in completed if row["outcome"].get("target_hit"))
    stop_hits = sum(1 for row in completed if row["outcome"].get("stoploss_hit"))
    correct = sum(1 for row in completed if row["outcome"].get("correct_decision"))
    buy_avoid = [
        row for row in completed
        if row.get("decision") in {"STRONG BUY", "BUY", "AVOID"}
    ]
    buy_avoid_success = sum(1 for row in buy_avoid if row["outcome"].get("correct_decision"))
    total = len(completed)
    return {
        "prediction_accuracy": round(correct / total * 100, 2),
        "target_hit_rate": round(target_hits / total * 100, 2),
        "stoploss_hit_rate": round(stop_hits / total * 100, 2),
        "decision_accuracy": round(correct / total * 100, 2),
        "buy_vs_avoid_success_rate": round(buy_avoid_success / len(buy_avoid) * 100, 2) if buy_avoid else None,
        "sample_size": total,
    }

