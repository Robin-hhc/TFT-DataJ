"""Offline public-image OCR baseline. Does not read gold labels during inference."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ("rapidocr", "onnxruntime", "numpy", "opencv-python")
ENGINE_PARAMS = {"Global.log_level": "warning", "Global.use_cls": False,
                 "EngineConfig.onnxruntime.intra_op_num_threads": 2,
                 "EngineConfig.onnxruntime.inter_op_num_threads": 1}

def verify_replay_inputs(baseline, versions, models):
    if baseline.get("versions") != versions or baseline.get("models") != models or baseline.get("engine_params") != ENGINE_PARAMS:
        raise ValueError("OCR environment/model/config changed; rerun the full baseline")
    for image in baseline["images"]:
        actual = hashlib.sha256(Path(image["image"]).read_bytes()).hexdigest()
        if actual != image["image_sha256"]:
            raise ValueError("Image changed; rerun the full baseline: "+image["image"])

def build_engine():
    import rapidocr
    from rapidocr import RapidOCR
    models = Path(rapidocr.__file__).resolve().parent / "models"
    names = {"Det": "PP-OCRv6_det_small.onnx", "Cls": "ch_ppocr_mobile_v2.0_cls_mobile.onnx", "Rec": "PP-OCRv6_rec_small.onnx"}
    params = dict(ENGINE_PARAMS)
    fingerprints = []
    for component, filename in names.items():
        path = models / filename
        if not path.is_file():
            raise FileNotFoundError(f"Bundled model missing: {filename}; no automatic download")
        params[f"{component}.model_path"] = str(path)
        fingerprints.append({"file": filename, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return RapidOCR(params=params), fingerprints

def recognize(engine, image_path):
    from PIL import Image
    with Image.open(image_path) as image:
        size = list(image.size)
    start = time.perf_counter()
    result = engine(str(image_path))
    elapsed = (time.perf_counter()-start)*1000
    records = []
    if result.txts is not None:
        for text, score, box in zip(result.txts, result.scores, result.boxes):
            records.append({"text": text, "score": float(score), "box": box.tolist()})
    return {"image": str(image_path), "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
            "size": size, "elapsed_ms": round(elapsed, 2), "records": records}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    start = time.perf_counter()
    engine, models = build_engine()
    payload = {"model_init_ms": round((time.perf_counter()-start)*1000, 2), "models": models,
               "versions": {p: importlib.metadata.version(p) for p in PACKAGES}, "engine_params": ENGINE_PARAMS,
               "images": []}
    for path in args.images:
        result = recognize(engine, path.resolve())
        payload["images"].append(result)
        print(json.dumps({"image": path.name, "elapsed_ms": result["elapsed_ms"], "texts": [r["text"] for r in result["records"]]}, ensure_ascii=False), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
