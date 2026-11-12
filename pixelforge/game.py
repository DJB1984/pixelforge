"""`pixelforge game`: a Phaser + Vite game scaffolded around the art folder.

The files come from assets/game/ (plus a generated package.json). They're the game's own code from then
on: `upgrade` never touches them, and re-running `game` skips any that exist unless `force` is set.
Everything shared (the loader, the player, levels, the HUD, the playtest hook) lives in export/pixelforge.js,
which `export`/`upgrade` refresh, so a game picks up runtime fixes without re-scaffolding.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .model import ASSETS, MARKER
from .project import Report

TEMPLATE = ASSETS / "game"
PHASER = "3.90.0"
VITE = "8.3.5"   # pinned, released 2026-10-21
GITIGNORE = ["node_modules/", "dist/"]


def package_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "game"


def package_json(name: str) -> str:
    pkg = {
        "name": package_name(name),
        "private": True,
        "version": "0.1.0",
        "type": "module",
        "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
        "dependencies": {"phaser": PHASER},
        "devDependencies": {"vite": VITE},
    }
    return json.dumps(pkg, indent=2) + "\n"


def files(name: str) -> dict[str, str]:
    """Every starter file, path (relative to the project root) -> text."""
    out = {"package.json": package_json(name)}
    for src in sorted(TEMPLATE.rglob("*")):
        if src.is_file() and "__pycache__" not in src.parts:
            text = src.read_text(encoding="utf-8")
            out[src.relative_to(TEMPLATE).as_posix()] = text.replace("__TITLE__", name)
    return out


def scaffold_game(target: Path, force: bool = False) -> Report:
    if not (target / MARKER).exists():
        raise FileNotFoundError(f"no {MARKER} in {target}; run `pixelforge init` there first")
    cfg = json.loads((target / MARKER).read_text(encoding="utf-8"))
    report = Report()
    for rel, text in files(cfg.get("name") or target.name).items():
        path = target / rel
        if path.exists() and not force:
            report.changes.append(f"= {rel} (exists, kept; --force replaces it)")
            continue
        report.changes.append(f"{'~' if path.exists() else '+'} {rel}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    gi = target / ".gitignore"
    old = gi.read_text(encoding="utf-8") if gi.exists() else ""
    missing = [line for line in GITIGNORE if line not in old.split()]
    if missing:
        report.changes.append(f"+ .gitignore ({', '.join(missing)})")
        sep = "\n" if old and not old.endswith("\n") else ""
        gi.write_text(old + sep + "".join(f"{line}\n" for line in missing), encoding="utf-8")
    if not list(target.glob("levels/*.json")):
        report.notes.append("no levels yet: `pixelforge new-level start`, then `pixelforge export --all`")
    elif not (target / "export" / "index.json").exists():
        report.notes.append("export/ has no index.json yet: run `pixelforge export --all` before `npm run dev`")
    return report
