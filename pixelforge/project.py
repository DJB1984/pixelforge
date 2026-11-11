"""Setting up and upgrading a game's pixelforge folder.

`init` copies a few files into the game. Only the Claude guide is *managed*: pixelforge.json
records its file name and a hash of what was written, so `upgrade` can tell an untouched guide
(safe to replace) from one someone edited (new version written alongside instead).
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .model import ASSETS, DEFAULT_CLASSES, DEFAULT_RESOLUTION, MARKER, VIEWS

GUIDE_HEADING = "# Sprites for this game (pixelforge)"  # first line of assets/CLAUDE.md


def _sha(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _guide_text() -> str:
    return (ASSETS / "CLAUDE.md").read_text(encoding="utf-8")


def _load(target: Path) -> dict:
    return json.loads((target / MARKER).read_text(encoding="utf-8"))


def _save(target: Path, cfg: dict) -> None:
    (target / MARKER).write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


@dataclass
class Report:
    changes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _scaffold(target: Path, cfg: dict, report: Report, dry_run: bool = False) -> None:
    """Create whatever standard pieces are missing. Never overwrites game-owned files."""
    for sub in ("sprites", "export"):
        if not (target / sub).is_dir():
            report.changes.append(f"+ {sub}/")
            if not dry_run:
                (target / sub).mkdir()
    pal = target / "palettes" / "game.json"
    if not pal.exists():
        report.changes.append("+ palettes/game.json")
        if not dry_run:
            pal.parent.mkdir(exist_ok=True)
            shutil.copyfile(ASSETS / "game.json", pal)
    if "classes" not in cfg:
        report.changes.append("+ size classes in pixelforge.json")
        cfg["classes"] = DEFAULT_CLASSES
    if "view" not in cfg:
        report.changes.append("+ \"view\": \"side\" in pixelforge.json (set \"topdown\" or \"overhead\" if that's "
                              "your camera)")
        cfg["view"] = "side"
    if "resolution" not in cfg:
        report.changes.append(f"+ \"resolution\": {list(DEFAULT_RESOLUTION)} in pixelforge.json (your game's base "
                              f"screen size, before scaling)")
        cfg["resolution"] = list(DEFAULT_RESOLUTION)
    gi = target / ".gitignore"
    if "previews/" not in (gi.read_text(encoding="utf-8") if gi.exists() else ""):
        report.changes.append("+ .gitignore (previews/)")
        if not dry_run:
            with gi.open("a", encoding="utf-8") as f:
                f.write("previews/\n")


def init_project(target: Path, name: str | None = None, view: str = "side",
                 resolution: tuple[int, int] = DEFAULT_RESOLUTION) -> Report:
    if view not in VIEWS:
        raise ValueError(f"view {view!r} must be one of {', '.join(VIEWS)}")
    target.mkdir(parents=True, exist_ok=True)
    if (target / MARKER).exists():
        raise FileExistsError(f"{target / MARKER} already exists; this folder is already a pixelforge project "
                              f"(use `pixelforge upgrade` to bring it up to date)")
    report = Report()
    cfg = {"name": name or target.name, "view": view, "resolution": list(resolution), "classes": DEFAULT_CLASSES}
    report.changes.append(f"+ {MARKER}")
    _scaffold(target, cfg, report)
    guide = "CLAUDE.md" if not (target / "CLAUDE.md").exists() else "PIXELFORGE.md"
    text = _guide_text()
    (target / guide).write_text(text, encoding="utf-8")
    report.changes.append(f"+ {guide}")
    if guide == "PIXELFORGE.md":
        report.notes.append("CLAUDE.md already existed: add a line to it such as "
                            "`See PIXELFORGE.md for making sprites.`")
    cfg["pixelforge"] = {"version": __version__, "guide": guide, "guide_sha256": _sha(text)}
    _save(target, cfg)
    return report


def _find_legacy_guide(target: Path) -> str | None:
    """Projects made before upgrade existed have no record of their guide; recognise it by heading."""
    for name in ("CLAUDE.md", "PIXELFORGE.md"):
        p = target / name
        if p.is_file() and p.read_text(encoding="utf-8").lstrip().startswith(GUIDE_HEADING):
            return name
    return None


def upgrade_project(target: Path, dry_run: bool = False) -> tuple[Report, str | None]:
    """Bring a game folder up to the installed pixelforge. Returns (report, previous version)."""
    if not (target / MARKER).exists():
        raise FileNotFoundError(f"no {MARKER} in {target}; run `pixelforge init` there first")
    cfg = _load(target)
    meta = dict(cfg.get("pixelforge", {}))
    previous = meta.get("version")
    report = Report()
    _scaffold(target, cfg, report, dry_run)

    text = _guide_text()
    if "guide" in meta and meta["guide"] is None:
        report.notes.append("guide: not managed here (pixelforge.json sets \"guide\": null)")
    else:
        guide = meta.get("guide") or _find_legacy_guide(target)
        path = target / guide if guide else None
        if guide is None:
            report.notes.append("guide: none found; leaving CLAUDE.md alone. Run `pixelforge init` in a fresh "
                                "folder to see the current guide")
        elif not path.exists():
            report.changes.append(f"+ {guide} (was missing)")
            if not dry_run:
                path.write_text(text, encoding="utf-8")
                meta.update(guide=guide, guide_sha256=_sha(text))
        else:
            current = path.read_text(encoding="utf-8")
            recorded = meta.get("guide_sha256")
            if _sha(current) == _sha(text):
                report.notes.append(f"guide: {guide} already current")
                meta.update(guide=guide, guide_sha256=_sha(text))
            elif recorded is None:
                # made before upgrade tracked edits: keep a backup, then replace
                report.changes.append(f"~ {guide} replaced with the current guide (old copy: {guide}.bak)")
                if not dry_run:
                    shutil.copyfile(path, target / f"{guide}.bak")
                    path.write_text(text, encoding="utf-8")
                    meta.update(guide=guide, guide_sha256=_sha(text))
            elif _sha(current) == recorded:
                report.changes.append(f"~ {guide} updated to the current guide (it had not been edited)")
                if not dry_run:
                    path.write_text(text, encoding="utf-8")
                    meta.update(guide_sha256=_sha(text))
            else:
                side = Path(guide).stem + ".pixelforge-new.md"
                report.changes.append(f"+ {side} (your {guide} has edits, so it was left alone)")
                report.notes.append(f"merge {side} into {guide} by hand (or ask Claude to), then delete it")
                if not dry_run:
                    (target / side).write_text(text, encoding="utf-8")

    if previous != __version__:
        report.changes.append(f"~ recorded pixelforge version {previous or 'unknown'} -> {__version__}")
    meta["version"] = __version__
    if not dry_run:
        cfg["pixelforge"] = meta
        _save(target, cfg)
    return report, previous
