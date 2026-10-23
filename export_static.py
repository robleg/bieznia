#!/usr/bin/env python3
"""Build the public static copy (GitHub Pages) of the treadmill tracker.

Usage: python3 -I export_static.py <page.html> <db_dir> <img_src_dir> <out_dir>
  page.html   : the artifact page as published (no doctype; <title>/<style> first)
  db_dir      : <db_dir>/products/*.json, <db_dir>/prices/*.json, <db_dir>/runs/*.json
                (from ArtifactData list with out_dir)
  img_src_dir : downloaded assets named <asset_id>.<ext> (from Artifact read path=<asset id>)
  out_dir     : docs/ folder of the repo; writes index.html and img/<asset_id>.jpg
Images are resized to max 640 px and re-encoded as JPEG q82 so the repo stays small.
Screenshots referenced by prices points (shot_asset) are copied the same way when present.
"""
import json, os, sys, glob, html

page_path, db_dir, img_src, out_dir = sys.argv[1:5]
os.makedirs(os.path.join(out_dir, "img"), exist_ok=True)

def load(sub):
    d = {}
    for f in sorted(glob.glob(os.path.join(db_dir, sub, "*.json"))):
        d[os.path.splitext(os.path.basename(f))[0]] = json.load(open(f, encoding="utf-8"))
    return d

products = load("products"); prices = load("prices"); runs = load("runs")
for pid, doc in products.items():
    doc.setdefault("id", pid)
runs_list = sorted(runs.values(), key=lambda r: str(r.get("ts", "")), reverse=True)[:30]
pins = []
state_pins = os.path.join(db_dir, "state", "pins.json")
if os.path.exists(state_pins):
    pins = json.load(open(state_pins, encoding="utf-8")).get("ids", [])

# images
wanted = set(p.get("image_asset") for p in products.values() if p.get("image_asset"))
for pr in prices.values():
    for pt in pr.get("points", []):
        if pt.get("shot_asset"):
            wanted.add(pt["shot_asset"])
try:
    from PIL import Image
except ImportError:
    Image = None
copied = 0; missing = []
for aid in sorted(wanted):
    src = next(iter(glob.glob(os.path.join(img_src, aid + ".*"))), None)
    dst = os.path.join(out_dir, "img", aid + ".jpg")
    if not src:
        if not os.path.exists(dst):
            missing.append(aid)
        continue
    if Image:
        im = Image.open(src).convert("RGB")
        im.thumbnail((640, 640))
        im.save(dst, "JPEG", quality=82, optimize=True)
    else:
        import shutil; shutil.copy(src, dst)
    copied += 1

# page
page = open(page_path, encoding="utf-8").read()
data = {"products": products, "prices": prices, "runs": runs_list, "pins": pins}
inline = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
head = ('<!doctype html><html lang="pl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<style>:root{color-scheme:light}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>'
        '</head><body>')
inject = ('<script>window.__IMG_BASE="img/";</script>'
          '<script id="inline-data" type="application/json">' + inline + '</script>')
out = head + inject + page + '</body></html>'
open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8").write(out)
open(os.path.join(out_dir, ".nojekyll"), "w").close()
print(json.dumps({"products": len(products), "prices": len(prices), "runs": len(runs_list), "images_written": copied,
                  "images_missing": len(missing), "missing_sample": missing[:5], "html_bytes": len(out)}, ensure_ascii=False))
