"""Development replay. Scores gold only after predictions; no live recommendations."""
from __future__ import annotations
import json
import importlib.metadata
from pathlib import Path
import sys
import time

from choice_reader import bounds, exact_catalog_matches, normalize_name, read_choice
from ocr_baseline import ROOT, build_engine, verify_replay_inputs, PACKAGES, ENGINE_PARAMS
from snapshot_stats import stage_stat

def run():
    import cv2
    import numpy as np
    from PIL import Image
    sys.stdout.reconfigure(encoding="utf-8")
    here = Path(__file__).resolve().parent
    work = ROOT / "work" / "ocr-public-samples"
    baseline = json.loads((work / "baseline.json").read_text(encoding="utf-8"))
    manifest = json.loads((here / "public-samples.json").read_text(encoding="utf-8"))
    # Predictions are obtained without supplying the manifest/gold to the parser or OCR.
    predictions = [read_choice(x["records"], x["size"]) for x in baseline["images"]]
    engine, models = build_engine()
    current_versions = {p: importlib.metadata.version(p) for p in PACKAGES}
    verify_replay_inputs(baseline, current_versions, models)
    outputs = []
    catalog = json.loads((ROOT / "work/dataj-p0/catalog.json").read_text(encoding="utf-8"))["data"]["hex"]
    for raw, prediction in zip(baseline["images"], predictions):
        with Image.open(raw["image"]) as image:
            image = image.convert("RGB")
            replay = []
            start = time.perf_counter()
            for card in prediction["cards"]:
                x1, y1, x2, y2 = bounds(card)
                roi = (max(0, int(x1)-4), max(0, int(y1)-3), min(image.width, int(x2)+5), min(image.height, int(y2)+4))
                pixels = cv2.cvtColor(np.asarray(image.crop(roi)), cv2.COLOR_RGB2BGR)
                result = engine(pixels, use_det=False, use_cls=False)
                replay.append({"text": result.txts[0] if result.txts else None,
                               "score": float(result.scores[0]) if result.txts else None, "roi": roi})
            replay_ms = (time.perf_counter()-start)*1000
        matches = [{"text": card["raw_text"], "catalog_matches": exact_catalog_matches(card["raw_text"], catalog)} for card in prediction["cards"]]
        outputs.append({"image": raw["image"], "image_sha256": raw["image_sha256"], "size": raw["size"],
                        "full_ocr_ms": raw["elapsed_ms"], "prediction": prediction,
                        "crop_replay_ms": round(replay_ms, 2), "crop_replay": replay,
                        "catalog_comparison_only": matches})
    # Evaluation phase: labels never go into inference above.
    gold_by_file = {Path(x["image"]).name: x for x in manifest["samples"]}
    for output in outputs:
        gold = gold_by_file[Path(output["image"]).name]
        names = [normalize_name(x) for x in gold["expected_names"]]
        output["id"] = gold["id"]
        output["expected"] = {"round": gold["expected_round"], "names": gold["expected_names"]}
        output["full_correct_names"] = sum(a["normalized_text"] == b for a, b in zip(output["prediction"]["cards"], names))
        output["crop_correct_names"] = sum(normalize_name(a["text"] or "") == b for a, b in zip(output["crop_replay"], names))
        output["round_correct"] = output["prediction"]["round"] == gold["expected_round"]
    negatives = json.loads((work / "negative-baseline.json").read_text(encoding="utf-8"))
    verify_replay_inputs(negatives, current_versions, models)
    negative_results = [{"image": x["image"], **read_choice(x["records"], x["size"])} for x in negatives["images"]]
    global_rows = json.loads((ROOT / "work/dataj-p0/global-hex.json").read_text(encoding="utf-8"))["data"]
    comp_rows = json.loads((ROOT / "work/dataj-p0/comp112-hex.json").read_text(encoding="utf-8"))["data"]["hexes"]
    demo = []
    for output in outputs:
        for candidate in output["catalog_comparison_only"]:
            if len(candidate["catalog_matches"]) != 1:
                continue
            entity = candidate["catalog_matches"][0]
            stage = output["prediction"]["round"]
            demo.append({"sample": output["id"], "entity": entity, "stage": stage,
                         "global": stage_stat(global_rows, entity["id"], stage),
                         "comp112": stage_stat(comp_rows, entity["id"], stage)})
    payload = {"purpose": "historical/season-unverified layout fixtures; excluded from S18 acceptance",
               "versions": baseline["versions"], "models": models,
               "crop_versions": current_versions, "engine_params": ENGINE_PARAMS, "positives": outputs,
               "negatives": negative_results,
               "offline_query_demo": {"warning": "Explicitly comparing names to a selected historical DataJ snapshot; not recommendations for these screenshots.",
                                      "set_id":18,"version":"18.2a","snapshot_date":"2026-09-25",
                                      "screenshot_version_verified":False,"rows":demo},
               "s18_verified_images": 0,
               "summary": {"images": len(outputs), "rounds_correct": sum(x["round_correct"] for x in outputs),
                           "full_correct_names": sum(x["full_correct_names"] for x in outputs),
                           "names_total": sum(len(x["expected"]["names"]) for x in outputs),
                           "crop_correct_names": sum(x["crop_correct_names"] for x in outputs),
                           "negative_rejections": sum(x["scene"] == "unknown" for x in negative_results)}}
    (work / "evaluation.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    for item in outputs:
        print(json.dumps({"id":item["id"], "crop_replay_ms":item["crop_replay_ms"], "crop_texts":[x["text"] for x in item["crop_replay"]], "matches":item["catalog_comparison_only"]},ensure_ascii=False))

if __name__ == "__main__":
    run()
