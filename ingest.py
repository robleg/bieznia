#!/usr/bin/env python3
"""Deterministic merge of one crawl result into ArtifactData documents.

Usage: python3 -I ingest.py <crawl.json> <existing_dir> <out_dir> [versions.json]
  crawl.json   : {"run": {...}, "products": [...]} as produced by the crawl step
  existing_dir : directory holding current db docs as <existing_dir>/products/<id>.json
                 and <existing_dir>/prices/<id>.json (from ArtifactData list with out_dir);
                 may be empty on the first run
  out_dir      : where to write products/<id>.json, prices/<id>.json, runs/<run_id>.json
                 and writes.json (the ArtifactData batch body, split into chunks of 50)
  versions.json: optional {"products/<id>": <version>, "prices/<id>": <version>} copied from
                 the ArtifactData list output; needed so existing docs get if_version pins
Prints a JSON summary with new_products, price_changes, and the list of written files.
Never guesses: a field the crawl left null keeps the previous non-null value.
"""
import json, os, sys, glob

crawl_path, existing_dir, out_dir = sys.argv[1:4]
versions = json.load(open(sys.argv[4], encoding="utf-8")) if len(sys.argv) > 4 else {}
crawl = json.load(open(crawl_path, encoding="utf-8"))
run = crawl["run"]; run_id = run["id"]; ts = run["ts"]

def load_dir(sub):
    d = {}
    for f in glob.glob(os.path.join(existing_dir, sub, "*.json")):
        doc = json.load(open(f, encoding="utf-8"))
        d[os.path.splitext(os.path.basename(f))[0]] = doc
    return d

old_products = load_dir("products"); old_prices = load_dir("prices")
for sub in ("products", "prices", "runs"):
    os.makedirs(os.path.join(out_dir, sub), exist_ok=True)

new_products = 0; price_changes = 0; written = []; seen = set()
for p in crawl["products"]:
    pid = p["id"]; seen.add(pid)
    prev = old_products.get(pid)
    doc = {k: v for k, v in p.items() if k != "version"}
    if p.get("price") is None and prev:
        doc["price"] = prev.get("price"); doc["delivery_pln"] = prev.get("delivery_pln")
    doc["specs"] = dict(p.get("specs") or {})
    if prev:
        for k, v in (prev.get("specs") or {}).items():
            if doc["specs"].get(k) is None and v is not None:
                doc["specs"][k] = v
        for k in ("image_url", "brand", "notes", "image_asset", "sku", "gtin13"):
            if not doc.get(k) and prev.get(k):
                doc[k] = prev[k]
        doc["first_seen"] = prev.get("first_seen", ts)
    else:
        new_products += 1; doc["first_seen"] = ts
    doc["last_seen"] = ts
    total = (p.get("price") or 0) + (p.get("delivery_pln") or 0)
    doc["total"] = round(total, 2)
    json.dump(doc, open(os.path.join(out_dir, "products", pid + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    written.append(f"products/{pid}")

    pr = old_prices.get(pid) or {"product_id": pid, "points": []}
    pts = [x for x in pr.get("points", []) if x.get("run_id") != run_id]
    last = pts[-1] if pts else None
    point = {"ts": ts, "run_id": run_id, "price": p.get("price"), "delivery": p.get("delivery_pln"),
             "total": round(total, 2), "available": p.get("available"), "url": p.get("url")}
    if p.get("shot_asset"):
        point["shot_asset"] = p["shot_asset"]
    if p.get("omnibus_30d") is not None:
        point["omnibus_30d"] = p["omnibus_30d"]
    doc.pop("shot_asset", None); doc.pop("omnibus_30d", None)
    if last and last.get("total") != point["total"]:
        price_changes += 1
    pts.append(point); pts.sort(key=lambda x: x["ts"])
    pr["points"] = pts[-120:]
    json.dump(pr, open(os.path.join(out_dir, "prices", pid + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    written.append(f"prices/{pid}")

missing = sorted(set(old_products) - seen)
run_doc = dict(run); run_doc.update({"new_products": new_products, "price_changes": price_changes,
                                     "products_seen": len(seen), "not_seen_this_run": missing})
json.dump(run_doc, open(os.path.join(out_dir, "runs", run_id + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
written.append(f"runs/{run_id}")

writes = []
for w in written:
    col, did = w.split("/", 1)
    entry = {"op": "set", "collection": col, "doc_id": did, "file_path": os.path.abspath(os.path.join(out_dir, col, did + ".json"))}
    if w in versions:
        entry["if_version"] = versions[w]
    writes.append(entry)
chunks = [writes[i:i + 50] for i in range(0, len(writes), 50)]
json.dump(chunks, open(os.path.join(out_dir, "writes.json"), "w", encoding="utf-8"), indent=1)
print(json.dumps({"new_products": new_products, "price_changes": price_changes, "not_seen": missing, "written": written}, ensure_ascii=False))
