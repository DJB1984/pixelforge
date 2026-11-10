"""A single self-contained HTML page showing every sprite and animation (sheets embedded as data URIs)."""
from __future__ import annotations

import base64
import io
import json
from datetime import date

from .export import build_sheet, build_tileset
from .model import ASSETS, Sprite, list_sprites, project_config, root, to_hex


def _data_uri(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def gallery_data(names: list[str] | None = None) -> dict:
    sprites, tilesets = [], []
    for name in names or list_sprites():
        s = Sprite.load(name)
        if s.kind == "tileset":
            img, data = build_tileset(s, padding=1)
            tilesets.append({
                "name": s.name, "w": s.width, "h": s.height, "cols": data["columns"], "spacing": data["spacing"],
                "palette": [[k, to_hex(s.palette[k]), v] for k, v in s.palette_raw.items()],
                "tiles": [{"name": n, "props": p} for n, p in zip(data["pixelforge"]["names"],
                                                                   data["pixelforge"]["properties"])],
                "sample": data["pixelforge"]["sample"], "anims": data["pixelforge"]["animations"],
                "sheet": _data_uri(img),
            })
            continue
        img, data = build_sheet(s, padding=1)
        frames = list(data["frames"].values())
        anims = []
        for tag in data["meta"]["frameTags"]:
            info = data["meta"]["pixelforge"]["animations"][tag["name"]]
            anims.append({
                "name": info["anim"], "loop": info["loop"], "fps": info["fps"] if info["fps"] % 1 else int(info["fps"]),
                "frames": [{"x": f["frame"]["x"], "y": f["frame"]["y"], "d": f["duration"],
                            "hurt": f["pixelforge"]["hurt"], "hit": f["pixelforge"]["hit"]}
                           for f in frames[tag["from"]:tag["to"] + 1]],
            })
        sprites.append({
            "name": s.name, "w": s.width, "h": s.height, "origin": list(s.origin),
            "body": list(s.body_rect()), "class": s.size_class,
            "palette": [[k, to_hex(s.palette[k]), v] for k, v in s.palette_raw.items()],
            "sheet": _data_uri(img),
            "anims": anims,
        })
    game = project_config().get("name") or root().name
    return {"game": game, "generated": date.today().isoformat(), "sprites": sprites, "tilesets": tilesets}


def render_gallery(names: list[str] | None = None, fragment: bool = False) -> str:
    """fragment=True omits <!doctype>/<html>/<body> (for hosts that add their own skeleton)."""
    data = gallery_data(names)
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    page = (ASSETS / "gallery.html").read_text(encoding="utf-8")
    page = page.replace("__PF_TITLE__", f"{data['game']} Sprites").replace("/*__PF_DATA__*/null", payload)
    if fragment:
        return page
    head, body = page.split("</style>", 1)  # title, fonts and styles belong in <head>
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            + head + "</style>\n</head>\n<body>" + body + "\n</body>\n</html>\n")
