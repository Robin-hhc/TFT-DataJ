"""Conservative development parser for OCR boxes. No gold labels or network calls."""
from __future__ import annotations
import itertools
import re
import unicodedata

def normalize_name(text):
    # Equivalent Unicode Roman numerals normalize; digits and + tiers stay distinct.
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))

def bounds(row):
    xs, ys = zip(*row["box"])
    return min(xs), min(ys), max(xs), max(ys)

def read_choice(records, size):
    width, height = size
    prompts = []
    for row in records:
        x1, y1, x2, y2 = bounds(row)
        text=normalize_name(row['text'])
        full_header='选择一个强化符文' in text
        partial_header=bool(re.fullmatch(r'请选择一个强化[\u3400-\u9fff]{2}',text))
        if (full_header or partial_header) and row["score"] >= .9 and y2 < .3*height:
            prompts.append(row)
    headerless=len(prompts)==0
    refresh=[]
    if headerless:
        for row in records:
            x1,y1,x2,y2=bounds(row)
            if normalize_name(row['text']) not in ('C','C0','C1') or row['score']<.9 or not .55<(y1+y2)/2/height<.85:
                continue
            if normalize_name(row['text'])=='C':
                counters=[r for r in records if normalize_name(r['text']) in ('0','1') and r['score']>=.9
                          and -.35*min(x2-x1,bounds(r)[2]-bounds(r)[0])<=bounds(r)[0]-x2<.04*width
                          and (bounds(r)[0]+bounds(r)[2])/2>(x1+x2)/2
                          and abs((bounds(r)[1]+bounds(r)[3]-y1-y2)/2)<.015*height]
                if len(counters)!=1:continue
            refresh.append(row)
        refresh.sort(key=lambda r:bounds(r)[0])
        if len(refresh)==3:
            centers=[(bounds(r)[0]+bounds(r)[2])/2/width for r in refresh]
            ys=[(bounds(r)[1]+bounds(r)[3])/2/height for r in refresh]
            if not (.15<centers[0]<.4 and .42<centers[1]<.62 and .65<centers[2]<.87 and max(ys)-min(ys)<.02):refresh=[]
    if len(prompts)>1 or (headerless and len(refresh)!=3):
        return {"scene": "unknown", "reason": "missing_or_ambiguous_choice_header", "round": None, "cards": []}
    prompt_bottom = bounds(prompts[0])[3] if prompts else height*.2
    rounds = []
    for row in records:
        x1, y1, x2, y2 = bounds(row)
        if .2*width < (x1+x2)/2 < .65*width and y2 < .09*height and row["score"] >= .85:
            for value in re.findall(r"(?<!\d)([1-9]-[1-9])(?!\d)", normalize_name(row["text"])):
                rounds.append((value, row))
    round_value = rounds[0][0] if len(rounds) == 1 else None
    if headerless and round_value not in ('2-1','3-2','4-2'):
        return {'scene':'unknown','reason':'headerless_stage_unconfirmed','round':round_value,'cards':[]}
    columns = [[], [], []]
    for row in records:
        text = normalize_name(row["text"])
        x1, y1, x2, y2 = bounds(row)
        cx, cy = (x1+x2)/2/width, (y1+y2)/2/height
        if not (2 <= len(text) <= 18 and re.fullmatch(r"[\u3400-\u9fffA-Za-z0-9+:!,]+", text)):
            continue
        if not re.search(r'[\u3400-\u9fff]',text):
            continue
        # Detection proposes a crop; the independent name reader still needs
        # high-confidence season-local agreement before assigning any ID.
        if row["score"] < .80 or y1 <= prompt_bottom or not .2 < cy < .72:
            continue
        if headerless and not .25<cy<.55:continue
        column = 0 if .1 < cx < .42 else 1 if .42 <= cx < .63 else 2 if .63 <= cx < .91 else None
        if column is not None:
            columns[column].append(row)
    triples = []
    for rows in itertools.product(*columns):
        rects = [bounds(r) for r in rows]
        ys = [(r[1]+r[3])/2 for r in rects]
        hs = [r[3]-r[1] for r in rects]
        xs = [(r[0]+r[2])/2 for r in rects]
        if min(hs) <= 0 or max(ys)-min(ys) > .55*min(hs) or max(hs)/min(hs) > 1.5:
            continue
        gaps = (xs[1]-xs[0], xs[2]-xs[1])
        if min(gaps) < .13*width or max(gaps)/min(gaps) > 1.35:
            continue
        if headerless and any(abs(xs[i]-(bounds(refresh[i])[0]+bounds(refresh[i])[2])/2)>.05*width for i in range(3)):
            continue
        score = sum(hs)/3 * min(r["score"] for r in rows)
        triples.append((score, rows))
    triples.sort(key=lambda item: item[0], reverse=True)
    if not triples or (len(triples)>1 and triples[1][0] >= .92*triples[0][0]):
        return {"scene": "choice_unresolved", "reason": "ambiguous_title_layout", "round": round_value, "cards": []}
    cards = []
    for index, row in enumerate(triples[0][1]):
        name = normalize_name(row["text"])
        cards.append({"slot": index, "raw_text": row["text"], "normalized_text": name,
                      "score": row["score"], "box": row["box"],
                      "needs_tier_review": bool(re.search(r"[1l]$", name))})
    return {"scene": "choice_candidates", "round": round_value,
            "header_box": prompts[0]['box'] if prompts else None,
            "layout_method": 'three_refresh_controls' if headerless else 'choice_header',
            "header_exact": bool(prompts) and '选择一个强化符文' in normalize_name(prompts[0]['text']),
            "round_box": rounds[0][1]["box"] if len(rounds)==1 else None,
            "round_score": rounds[0][1]["score"] if len(rounds)==1 else None,
            "cards": cards, "recommendation_allowed": False,
            "reason": "public_image_game_mode_and_version_unverified"}

def exact_catalog_matches(text, catalog):
    key = normalize_name(text)
    return [{"id": str(row["id"]), "name": row["name"]}
            for row in catalog if normalize_name(row["name"]) == key]
