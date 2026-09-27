"""Explicit offline DataJ snapshot lookup; never substitutes overall for stage."""
from __future__ import annotations
import math

STAGES = {"2-1": 0, "3-2": 1, "4-2": 2}

def stage_stat(rows, hex_id, stage):
    if stage not in STAGES:
        return {"status": "unsupported_stage", "avg_placement": None}
    matches = [r for r in rows if str(r.get("hexId")) == str(hex_id)]
    if len(matches) != 1:
        return {"status": "missing_or_ambiguous_entity", "avg_placement": None}
    parts = [r for r in matches[0].get("roundStats", [])
             if r.get("roundLabel") == stage and r.get("round") == STAGES[stage]]
    if len(parts) != 1:
        return {"status": "no_stage_data", "avg_placement": None}
    part = parts[0]
    avg, count = part.get("avgPlacement"), part.get("sampleCount")
    if (isinstance(avg, bool) or not isinstance(avg, (int, float)) or not math.isfinite(avg)
            or not 1 <= avg <= 8 or isinstance(count, bool) or not isinstance(count, int) or count <= 0):
        return {"status": "invalid_stat", "avg_placement": None}
    return {"status": "ok", "avg_placement": avg, "sample_count": count, "stage": stage}
