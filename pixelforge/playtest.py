"""`pixelforge play LEVEL --script "..."`: Claude playtests a level.

A script of held keys runs the level in headless Chromium (Playwright) through `window.pixelforgePlay`
(`installPixelforgePlay` in pixelforge.js), frozen and stepped one 60 fps frame at a time, so a run is the
same every time. Out come screenshots every `--shot-every`, a contact sheet (the route drawn on the level,
then each shot with the time, the player's state and what happened), `log.json`, and notes: stuck,
fell, never landed, triggers fired, and the script's `expect` lines passed or failed.

Script: one action per line or `;`, `#` starts a comment.
    right 1.5s          hold keys (left right up down jump run attack, joined with +) for a time (s or ms)
    right+run 800ms
    jump                no time: a press. With jump in it, held until the top of the jump (a full jump);
    right+jump          otherwise held for one frame (attack). Then the keys are let go for a frame.
    wait 1s             no keys
    shot                a screenshot now (on top of the regular ones)
    expect onGround     a state field is truthy; `expect not onGround`
    expect x > 200      compare a field: x y vx vy onGround facing anim level (and the game's extra fields)
    expect anim == princess_run    (== != > < >= <=; `has` for lists: `expect inventory has key`)
    expect trigger door an event happened so far (trigger hit jump land attack fell dialog), optionally one
    expect no fell      whose name, type or target matches; `no`/`not` for never
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

FRAME_MS = 1000 / 60
KEYS = ("left", "right", "up", "down", "jump", "run", "attack")
EVENTS = ("trigger", "hit", "jump", "land", "attack", "fell", "dialog")
OPS = ("==", "!=", ">=", "<=", ">", "<", "=", "has")
CHUNK = 6                 # frames per step call: the trace's resolution (100 ms)
STUCK_FRAMES = 60         # held movement this long without moving 2px is "stuck"
JUMP_LIMIT = 90           # a press with jump in it holds at most this many frames
INSTALL_HINT = 'pip install -e "<pixelforge folder>[play]" && playwright install chromium'


class ScriptError(ValueError):
    pass


class PlayUnavailable(RuntimeError):
    pass


@dataclass
class Expect:
    text: str
    negate: bool = False
    field: str | None = None      # a state field...
    op: str | None = None         # ...compared, or just truthy when None
    value: object = None
    event: str | None = None      # or an event that happened so far
    match: str | None = None


@dataclass
class Action:
    kind: str                     # hold | press | wait | shot | expect
    text: str
    line: int
    where: str = ""               # "line 3", or "action 3" in a one-line script
    keys: tuple[str, ...] = ()
    frames: int = 0
    expect: Expect | None = None


def parse_duration(s: str) -> int:
    """'1.5s' / '800ms' -> whole 60 fps frames (at least one)."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(ms|s)", s.strip().lower())
    if not m:
        raise ScriptError(f"{s!r} isn't a time: give it with a unit, like 1.5s or 800ms")
    ms = float(m[1]) * (1000 if m[2] == "s" else 1)
    return max(1, round(ms / FRAME_MS))


def _value(s: str):
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none"):
        return None
    try:
        return float(s)
    except ValueError:
        return s.strip("'\"")


def parse_expect(text: str) -> Expect:
    words = text.split()
    e = Expect(text=text)
    if words and words[0].lower() in ("not", "no"):
        e.negate = True
        words = words[1:]
    if not words:
        raise ScriptError("`expect` needs something to check: expect onGround, expect x > 200, expect trigger door")
    if words[0] in EVENTS:
        e.event = words[0]
        e.match = " ".join(words[1:]) or None
        return e
    rest = " ".join(words)
    m = re.fullmatch(r"([A-Za-z_]\w*)\s*(==|!=|>=|<=|>|<|=|\shas\s)\s*(.+)", rest)
    if m:
        e.field, e.op, e.value = m[1], m[2].strip(), _value(m[3].strip())
        if e.op == "=":
            e.op = "=="
        if e.op in (">", "<", ">=", "<=") and not isinstance(e.value, float):
            raise ScriptError(f"`expect {text}`: {e.op} compares numbers, got {m[3]!r}")
        return e
    if len(words) == 1 and re.fullmatch(r"[A-Za-z_]\w*", words[0]):
        e.field = words[0]
        return e
    raise ScriptError(f"can't read `expect {text}`: use expect onGround, expect x > 200, expect anim == "
                      f"princess_run or expect trigger door")


def parse_script(text: str) -> list[Action]:
    actions = []
    for n, raw in enumerate(text.splitlines(), 1):
        for part in raw.split("#", 1)[0].split(";"):
            part = part.strip()
            if not part:
                continue
            words = part.split()
            head = words[0].lower()
            try:
                if head == "expect":
                    actions.append(Action("expect", part, n, expect=parse_expect(part[len(words[0]):].strip())))
                elif head == "shot":
                    if len(words) > 1:
                        raise ScriptError("`shot` takes nothing after it")
                    actions.append(Action("shot", part, n))
                elif head == "wait":
                    if len(words) != 2:
                        raise ScriptError("`wait` takes a time: wait 1s")
                    actions.append(Action("wait", part, n, frames=parse_duration(words[1])))
                else:
                    keys = tuple(k.lower() for k in words[0].split("+"))
                    bad = [k for k in keys if k not in KEYS]
                    if bad or not all(keys):
                        raise ScriptError(f"unknown key {bad[0] if bad else '+'!r}: keys are {', '.join(KEYS)} "
                                          f"(joined with +), and the other actions wait, shot, expect")
                    if len(words) > 2:
                        raise ScriptError(f"too many words: `{words[0]} 1s` holds keys for a time")
                    if len(words) == 2:
                        actions.append(Action("hold", part, n, keys=keys, frames=parse_duration(words[1])))
                    else:
                        actions.append(Action("press", part, n, keys=keys))
            except ScriptError as err:
                raise ScriptError(f"script line {n} (`{part}`): {err}") from None
    one_line = len({a.line for a in actions}) <= 1
    for i, a in enumerate(actions, 1):
        a.where = f"action {i}" if one_line else f"line {a.line}"
    return actions


def read_script(arg: str | None) -> str:
    """--script is a file if one exists at that path, else the script itself."""
    if not arg:
        return "wait 1s"
    p = Path(arg)
    if len(arg) < 260 and "\n" not in arg and ";" not in arg and p.is_file():
        return p.read_text(encoding="utf-8")
    return arg


# ---- checking ----------------------------------------------------------------------------------
def _event_matches(ev: dict, match: str | None) -> bool:
    if not match:
        return True
    return any(str(ev.get(k)) == match for k in ("name", "object", "to", "target"))


def check_expect(e: Expect, state: dict, events: list[dict]) -> tuple[bool, str]:
    """(passed, what was seen) for one expectation, against the state now and every event so far."""
    if e.event:
        hits = [ev for ev in events if ev.get("type") == e.event and _event_matches(ev, e.match)]
        seen = (f"{len(hits)} at " + ", ".join(f"{ev['t'] / 1000:.2f}s" for ev in hits[:5])) if hits else "none"
        return (not hits) if e.negate else bool(hits), seen
    if e.field not in state:
        return False, f"no field {e.field!r} (fields: {', '.join(k for k in state if k != 'events')})"
    got = state[e.field]
    if e.op is None:
        ok = bool(got)
    elif e.op == "has":
        ok = isinstance(got, (list, tuple)) and _text(e.value) in [_text(v) for v in got]
    elif e.op in (">", "<", ">=", "<="):
        if not isinstance(got, (int, float)) or isinstance(got, bool):
            return False, f"{e.field} = {got} (not a number)"
        g, w = float(got), e.value
        ok = {">": g > w, "<": g < w, ">=": g >= w, "<=": g <= w}[e.op]
    else:
        ok = (_text(got) == _text(e.value)) == (e.op == "==")
    return (not ok) if e.negate else ok, f"{e.field} = {_text(got)}"


def _text(v) -> str:
    """How a value reads in a script: true/false, null, 300 (not 300.0)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v).is_integer() else str(v)
    return str(v)


# ---- running -----------------------------------------------------------------------------------
@dataclass
class Run:
    level: str
    script: str
    view: str
    url: str = ""
    trace: list[dict] = field(default_factory=list)     # {t (ms), input, x, y, vx, vy, onGround, anim, level, ...}
    events: list[dict] = field(default_factory=list)    # {t (ms), type, ...}
    shots: list[dict] = field(default_factory=list)     # {n, file, t, why, state}
    expects: list[dict] = field(default_factory=list)   # {text, line, t, passed, seen}
    errors: list[str] = field(default_factory=list)     # the page's own errors

    def to_json(self) -> dict:
        return {"level": self.level, "view": self.view, "url": self.url, "script": self.script,
                "trace": self.trace, "events": self.events, "shots": self.shots, "expects": self.expects,
                "errors": self.errors}


def _ms(frames: int) -> int:
    return round(frames * FRAME_MS)


def run_script(actions: list[Action], driver, run: Run, shot_every: int | None, shots_dir: Path | None) -> Run:
    """Drive the game: `driver.step(frames, input) -> state` (state["events"]: events since the last call),
    `driver.state()`, `driver.shot(path)`. shot_every is in frames (None: only `shot` lines)."""
    now = 0
    next_shot = shot_every or 0
    state: dict = {}

    def record(st: dict, held: tuple[str, ...]) -> None:
        nonlocal state
        for ev in st.get("events") or []:
            ev = {**ev, "t": _ms(now)}   # the run's clock (the scene's own starts at load time)
            run.events.append(ev)
        state = {k: v for k, v in st.items() if k != "events"}
        run.trace.append({"t": _ms(now), "input": list(held), **state})

    def shot(why: str) -> None:
        n = len(run.shots)
        name = f"{n:02d}.png"
        if shots_dir is not None:
            driver.shot(shots_dir / name)
        run.shots.append({"n": n, "file": name, "t": _ms(now), "why": why, "state": dict(state)})

    def advance(frames: int, held: tuple[str, ...]) -> None:
        nonlocal now, next_shot
        inp = {k: True for k in held}
        while frames > 0:
            chunk = min(frames, CHUNK, (next_shot - now) if shot_every else CHUNK)
            st = driver.step(chunk, inp)
            now += chunk
            frames -= chunk
            record(st, held)
            if shot_every and now >= next_shot:
                shot("every")
                next_shot += shot_every

    record(driver.state(), ())
    if "x" not in state:
        raise RuntimeError(f"the level has no player to drive (state: {state}). Set \"player\" in "
                           f"levels/{run.level}.json, or put a spawn ('@') in objects.rows")
    shot("start")
    for a in actions:
        if a.kind in ("hold", "wait"):
            advance(a.frames, a.keys)
        elif a.kind == "press":
            if "jump" in a.keys:
                # a full jump: hold until it stops rising (or it never left the ground)
                for i in range(JUMP_LIMIT):
                    advance(1, a.keys)
                    if not state.get("onGround") and state.get("vy", 0) >= 0:
                        break
                    if i >= 3 and state.get("onGround") and not state.get("vy"):
                        break
            else:
                advance(1, a.keys)
            advance(1, tuple(k for k in a.keys if k not in ("jump", "attack")))   # let go, so it can be pressed again
        elif a.kind == "shot":
            shot("shot")
        elif a.kind == "expect":
            ok, seen = check_expect(a.expect, state, run.events)
            run.expects.append({"text": a.text, "line": a.line, "where": a.where, "t": _ms(now), "passed": ok, "seen": seen})
    if not run.shots or run.shots[-1]["t"] != _ms(now):
        shot("end")
    return run


# ---- what happened -----------------------------------------------------------------------------
def _moves(view: str) -> set[str]:
    return {"left", "right"} if view == "side" else {"left", "right", "up", "down"}


def notes(run: Run, level_size: tuple[int, int] | None = None) -> list[str]:
    """The summary, from the log alone: stuck, fell, never landed, triggers, hits, expectations."""
    out = []
    moves = _moves(run.view)
    # stuck: the same movement keys held 1s+ without moving 2px
    anchor = None
    reported = None
    for e in run.trace:
        held = tuple(sorted(set(e["input"]) & moves))
        if not held or e.get("dialogOpen"):   # a dialog box holds the player on purpose
            anchor = reported = None
            continue
        if anchor is None or anchor[0] != held or abs(e["x"] - anchor[1]["x"]) + abs(e["y"] - anchor[1]["y"]) >= 2:
            anchor, reported = (held, e), None
            continue
        if e["t"] - anchor[1]["t"] >= STUCK_FRAMES * FRAME_MS - 1 and reported is not anchor:
            reported = anchor
            a = anchor[1]
            out.append(f"stuck: holding {'+'.join(held)} from {a['t'] / 1000:.2f}s, but the player stayed at "
                       f"({a['x']:.0f}, {a['y']:.0f}) for 1s+ (a wall, a ledge it can't climb, the level's edge?)")
    for ev in run.events:
        if ev["type"] == "fell":
            where = _before(run, ev["t"])
            out.append(f"fell out of the world at {ev['t'] / 1000:.2f}s" + (f" near x={where['x']:.0f}" if where else "")
                       + " (and went back to the spawn)")
    if run.view == "side" and run.trace:
        if not any(e.get("onGround") for e in run.trace):
            out.append("never stood on the ground: the spawn may be in the air, or the ground doesn't collide")
        jumps = [ev for ev in run.events if ev["type"] == "jump"]
        if jumps:
            last = jumps[-1]["t"]
            if not any(ev["type"] == "land" and ev["t"] >= last for ev in run.events) and not run.trace[-1].get("onGround"):
                out.append(f"never landed after the jump at {last / 1000:.2f}s (still in the air at the end)")
    if level_size and run.trace:
        W, H = level_size
        far = [e for e in run.trace if e["x"] < -8 or e["x"] > W + 8 or e["y"] > H + 32 or e["y"] < -64]
        if far and not any(ev["type"] == "fell" for ev in run.events):
            e = far[0]
            out.append(f"left the level at {e['t'] / 1000:.2f}s: ({e['x']:.0f}, {e['y']:.0f}) is outside its "
                       f"{W}x{H} px")
    # the game's own health (opts.extra in installPixelforgePlay), when it reports one
    lost = [(a, b) for a, b in zip(run.trace, run.trace[1:])
            if isinstance(a.get("health"), (int, float)) and isinstance(b.get("health"), (int, float))
            and b["health"] < a["health"]]
    if lost:
        out.append("hurt: " + ", ".join(f"health {_text(a['health'])} -> {_text(b['health'])} at {b['t'] / 1000:.2f}s "
                                        f"near ({a['x']:.0f}, {a['y']:.0f})" for a, b in lost))
    trig = [ev for ev in run.events if ev["type"] == "trigger"]
    if trig:
        out.append("triggers: " + ", ".join(f"{_trigger(ev)} at {ev['t'] / 1000:.2f}s" for ev in trig))
    else:
        out.append("triggers: none fired")
    talks = [ev for ev in run.events if ev["type"] == "dialog"]
    if talks:
        out.append("dialogs: " + ", ".join(f"{ev.get('name') or '?'} at {ev['t'] / 1000:.2f}s "
                                           f"({((ev.get('text') or '').splitlines() or [''])[0][:40]!r})" for ev in talks))
    hits = [ev for ev in run.events if ev["type"] == "hit"]
    if hits:
        out.append("hits: " + ", ".join(f"{ev.get('target') or '?'} at {ev['t'] / 1000:.2f}s" for ev in hits))
    for x in run.expects:
        out.append(f"expect {x['text'][len('expect'):].strip()} ({x['where']}, at {x['t'] / 1000:.2f}s): "
                   f"{'passed' if x['passed'] else 'FAILED'}, {x['seen']}")
    for err in run.errors:
        out.append(f"page error: {err}")
    return out


def _trigger(ev: dict) -> str:
    name = ev.get("name") or ev.get("object") or "?"
    if ev.get("object") and ev["object"] != name:
        name += f" ({ev['object']})"
    return name + (f" -> {ev['to']}" if ev.get("to") else "")


def _before(run: Run, t: int) -> dict | None:
    """Where the player was just before time t: an event happened somewhere in the step that ended at t,
    after this (a fall's step ends back at the spawn)."""
    before = [e for e in run.trace if e["t"] < t]
    return before[-1] if before else (run.trace[0] if run.trace else None)


def failed(run: Run) -> bool:
    return bool(run.errors) or any(not x["passed"] for x in run.expects)


def describe(state: dict, view: str = "side") -> str:
    if "x" not in state:
        return "no player"
    bits = [f"({state['x']:.0f}, {state['y']:.0f})"]
    if state.get("anim"):
        bits.append(str(state["anim"]))
    if view == "side" and "onGround" in state:
        bits.append("ground" if state["onGround"] else f"air vy {state.get('vy', 0):.0f}")
    return "  ".join(bits)


# ---- the contact sheet -------------------------------------------------------------------------
PATH = (255, 214, 64, 255)
TELEPORT = 64             # px between two trace points (100 ms apart) that can only be a teleport
SHOT = (255, 255, 255, 255)
SHADOW = (24, 20, 37, 220)
EV_COLORS = {"jump": (99, 199, 77, 255), "land": (254, 174, 52, 255), "trigger": (44, 232, 245, 255),
             "hit": (240, 40, 60, 255), "fell": (240, 40, 60, 255), "attack": (181, 80, 136, 255)}
OK = (99, 199, 77, 255)
BAD = (240, 70, 80, 255)


def route_image(lv, run: Run, budget: int = 1400) -> Image.Image:
    """The level as the game draws it, with the player's path, the shot numbers and the events on it."""
    from .render import font, zoom
    from .screens import compose
    world = compose(lv).world()
    W, H = lv.pixel_size
    scale = max(1, min(4, budget // max(W, 1)))
    img = zoom(world, scale)
    d = ImageDraw.Draw(img)
    # the path, broken where the player jumped across the map (a respawn, a door, another level)
    paths, last = [], None
    for e in run.trace:
        if "x" not in e or e.get("level") not in (None, lv.name):
            last = None
            continue
        if last is None or abs(e["x"] - last["x"]) + abs(e["y"] - last["y"]) > TELEPORT:
            paths.append([])
        paths[-1].append((e["x"] * scale, e["y"] * scale))
        last = e
    for pts in paths:
        if len(pts) > 1:
            d.line(pts, fill=SHADOW, width=4)
            d.line(pts, fill=PATH, width=2)
    for ev in run.events:
        e = _before(run, ev["t"])
        if not e or e.get("level") not in (None, lv.name):
            continue
        x, y = e["x"] * scale, e["y"] * scale
        c = EV_COLORS.get(ev["type"], SHOT)
        d.rectangle([x - 3, y - 3, x + 3, y + 3], fill=c, outline=SHADOW)
    f = font(11)
    for o in lv.objects:   # doors and triggers: the areas a run is usually trying to reach
        if o.rect:
            x, y, w, h = (v * scale for v in o.rect)
            d.rectangle([x, y, x + w - 1, y + h - 1], outline=EV_COLORS["trigger"])
            d.text((x + w / 2, y - 2), o.name + (f" -> {o.to}" if o.to else ""), fill=EV_COLORS["trigger"], font=f,
                   anchor="md", stroke_width=2, stroke_fill=SHADOW)
    for s in run.shots:
        st = s["state"]
        if "x" in st and st.get("level") in (None, lv.name):
            d.text((st["x"] * scale, st["y"] * scale - 6), str(s["n"]), fill=SHOT, font=f, anchor="md",
                   stroke_width=2, stroke_fill=SHADOW)
    return img


def contact_sheet(run: Run, shots_dir: Path, lv=None, resolution: tuple[int, int] = (320, 180)) -> Image.Image:
    from .render import LABEL_BG, LABEL_FG, font, stack, zoom
    rw, rh = resolution
    scale = 2 if len(run.shots) <= 12 else 1
    cols = 3 if scale == 2 else 5
    tw, th = rw * scale, rh * scale
    f, small = font(13), font(11)
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    # under each shot: its number, time and state, then what happened since the last one, wrapped
    captions, prev_t = [], -1
    for s in run.shots:
        happened = [ev["type"] + (f" {ev.get('name') or ev.get('target') or ''}".rstrip()
                                  if ev["type"] in ("trigger", "hit") else "")
                    for ev in run.events if prev_t < ev["t"] <= s["t"]]
        pieces = [(", ".join(happened), LABEL_FG)] if happened else []
        pieces += [(("ok " if c["passed"] else "FAILED ") + c["text"], OK if c["passed"] else BAD)
                   for c in run.expects if prev_t < c["t"] <= s["t"]]
        lines, cx = [[]], 0
        for text, color in pieces:
            w = round(measure.textlength(text, font=small))
            if cx and cx + w > tw:
                lines.append([])
                cx = 0
            lines[-1].append((text, color, cx))
            cx += w + 12
        captions.append([ln for ln in lines if ln])
        prev_t = s["t"]
    row_h = [th + 26 + 14 * max(len(c) for c in captions[r:r + cols]) for r in range(0, len(run.shots), cols)]
    grid = Image.new("RGBA", (cols * (tw + 10) - 10, sum(h + 8 for h in row_h)), LABEL_BG)
    d = ImageDraw.Draw(grid)
    for i, s in enumerate(run.shots):
        x, y = (i % cols) * (tw + 10), sum(h + 8 for h in row_h[:i // cols])
        p = shots_dir / s["file"]
        if p.is_file():
            im = Image.open(p).convert("RGBA")
            if im.size != (rw, rh):
                im = im.resize((rw, rh), Image.NEAREST)
            grid.alpha_composite(zoom(im, scale), (x, y))
        d.text((x, y + th + 3), f"{s['n']:02d}  {s['t'] / 1000:.2f}s  {describe(s['state'], run.view)}", fill=LABEL_FG, font=f)
        for n, line in enumerate(captions[i]):
            for text, color, dx in line:
                d.text((x + dx, y + th + 22 + 14 * n), text, fill=color, font=small)
    passed = sum(x["passed"] for x in run.expects)
    head = (f"play {run.level}  {len(run.shots)} shots over {run.trace[-1]['t'] / 1000 if run.trace else 0:.2f}s"
            + (f"  expect: {passed}/{len(run.expects)} passed" if run.expects else ""))
    sections = []
    if lv is not None:
        sections.append((f"{head}   route (yellow), shot numbers, events: jump green, land orange, trigger cyan, "
                         f"hit/fell red", route_image(lv, run)))
    sections.append(((f"{head}   " if lv is None else "") + f"shots at {scale}x", grid))
    return stack(sections)


# ---- the browser -------------------------------------------------------------------------------
class PageDriver:
    def __init__(self, page, resolution: tuple[int, int]):
        self.page = page
        self.canvas = page.locator("canvas").first
        self.resolution = resolution

    def step(self, frames: int, inp: dict) -> dict:
        return self.page.evaluate("([ms, input]) => window.pixelforgePlay.step(ms, input)",
                                  [frames * FRAME_MS, inp])

    def state(self) -> dict:
        return self.page.evaluate("() => window.pixelforgePlay.state()")

    def shot(self, path: Path) -> None:
        import io
        im = Image.open(io.BytesIO(self.canvas.screenshot())).convert("RGBA")
        rw, rh = self.resolution
        if im.size != (rw, rh):   # the game's own zoom: back to its pixels (exact for a whole-number zoom)
            im = im.resize((rw, rh), Image.NEAREST)
        im.save(path)


def _launch(pw, headed: bool):
    errors = []
    for kw in ({}, {"channel": "msedge"}, {"channel": "chrome"}):
        try:
            return pw.chromium.launch(headless=not headed, **kw)
        except Exception as e:   # noqa: BLE001 - try the next browser
            errors.append(str(e).splitlines()[0])
    raise PlayUnavailable("couldn't start a browser for the playtest (" + "; ".join(errors) + ").\n"
                          f"Install one with: {INSTALL_HINT}")


def _start_server():
    from .server import make_server
    httpd = make_server(0, quiet=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _with_level(url: str, level: str) -> str:
    if "level=" in url:
        return url
    return url + ("&" if "?" in url else "?") + f"level={level}"


def play(level: str, script: str, url: str | None = None, shot_every_ms: int | None = 250,
         out_dir: Path | None = None, headed: bool = False, timeout_ms: int = 30000) -> tuple[Run, Path]:
    """Run the script against the level. Returns the run and the contact sheet's path."""
    from .level import Level
    from .model import game_resolution, root
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise PlayUnavailable(f"`pixelforge play` needs Playwright: {INSTALL_HINT}") from None
    actions = parse_script(script)
    lv = Level.load(level)
    resolution = tuple(game_resolution())
    out_dir = out_dir or root() / "previews"
    shots_dir = out_dir / f"play_{level}"
    shots_dir.mkdir(parents=True, exist_ok=True)
    for old in shots_dir.glob("*.png"):
        old.unlink()
    httpd = None
    if url:
        page_url = _with_level(url, level)
    else:
        httpd, base = _start_server()
        page_url = f"{base}/viewer/play.html?level={level}&test=1&zoom=1"
    run = Run(level=level, script=script, view=lv.view, url=page_url)
    try:
        with sync_playwright() as pw:
            browser = _launch(pw, headed)
            page = browser.new_page(viewport={"width": max(800, resolution[0] * 4), "height": max(600, resolution[1] * 4)})
            page.on("pageerror", lambda e: run.errors.append(str(e).splitlines()[0]))
            page.goto(page_url)
            try:
                page.wait_for_function("() => window.pixelforgePlay", timeout=timeout_ms)
                page.evaluate("async () => { await window.pixelforgePlay.ready; window.pixelforgePlay.freeze(); }")
            except Exception as e:   # noqa: BLE001
                why = "; ".join(run.errors) or str(e).splitlines()[0]
                raise RuntimeError(f"the game at {page_url} never got a level running ({why}). "
                                   + ("Is `npm run dev` running, and does its Level scene call installPixelforgePlay?"
                                      if url else "Phaser loads from cdn.jsdelivr.net: is this machine online?")) from None
            page.evaluate("() => window.pixelforgePlay.step(1000 / 30, {})")   # let a launched HUD scene start
            driver = PageDriver(page, resolution)
            every = max(1, round(shot_every_ms / FRAME_MS)) if shot_every_ms else None
            run_script(actions, driver, run, every, shots_dir)
            browser.close()
    finally:
        if httpd:
            httpd.shutdown()
            httpd.server_close()
    (shots_dir / "log.json").write_text(json.dumps({**run.to_json(), "notes": notes(run, lv.pixel_size)}, indent=1),
                                        encoding="utf-8")
    sheet = out_dir / f"play_{level}.png"
    contact_sheet(run, shots_dir, lv, resolution).save(sheet)
    return run, sheet
