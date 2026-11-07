"""Grid: a 2D array of palette keys. '.' is always transparent."""
from __future__ import annotations

from dataclasses import dataclass, field

TRANSPARENT = "."


class GridError(ValueError):
    pass


@dataclass
class Grid:
    width: int
    height: int
    cells: list[list[str]] = field(default_factory=list)

    def __post_init__(self):
        if not self.cells:
            self.cells = [[TRANSPARENT] * self.width for _ in range(self.height)]

    # ---- construction / serialization -------------------------------------------------
    @classmethod
    def blank(cls, width: int, height: int) -> "Grid":
        return cls(width, height)

    @classmethod
    def parse(cls, text: str, width: int | None = None, height: int | None = None,
              strict: bool = True) -> "Grid":
        """Parse a text grid. Blank trailing lines and trailing whitespace are ignored.

        With strict=True, mismatched row widths/row counts raise GridError (with the
        offending line number). With strict=False rows are padded/truncated so the
        caller can still render a broken frame and report problems separately.
        """
        lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
        while lines and lines[-1] == "":
            lines.pop()
        w = width if width is not None else max((len(ln) for ln in lines), default=0)
        h = height if height is not None else len(lines)
        if strict:
            if len(lines) != h:
                raise GridError(f"expected {h} rows, got {len(lines)}")
            for y, ln in enumerate(lines):
                if len(ln) != w:
                    raise GridError(f"row {y} has {len(ln)} chars, expected {w}")
        cells = []
        for y in range(h):
            ln = lines[y] if y < len(lines) else ""
            row = list(ln[:w]) + [TRANSPARENT] * max(0, w - len(ln))
            row = [TRANSPARENT if c == " " else c for c in row]
            cells.append(row)
        return cls(w, h, cells)

    def to_text(self) -> str:
        return "\n".join("".join(r) for r in self.cells) + "\n"

    def copy(self) -> "Grid":
        return Grid(self.width, self.height, [r[:] for r in self.cells])

    # ---- access -----------------------------------------------------------------------
    def get(self, x: int, y: int) -> str:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.cells[y][x]
        return TRANSPARENT

    def set(self, x: int, y: int, key: str) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.cells[y][x] = key

    def keys(self) -> set[str]:
        return {c for r in self.cells for c in r if c != TRANSPARENT}

    def opaque_count(self) -> int:
        return sum(1 for r in self.cells for c in r if c != TRANSPARENT)

    def bbox(self) -> tuple[int, int, int, int] | None:
        """(left, top, right, bottom) inclusive, or None if fully transparent."""
        xs, ys = [], []
        for y, r in enumerate(self.cells):
            for x, c in enumerate(r):
                if c != TRANSPARENT:
                    xs.append(x)
                    ys.append(y)
        if not xs:
            return None
        return min(xs), min(ys), max(xs), max(ys)

    # ---- transforms (all return new grids) --------------------------------------------
    def offset(self, dx: int, dy: int) -> "Grid":
        out = Grid.blank(self.width, self.height)
        for y in range(self.height):
            for x in range(self.width):
                out.set(x + dx, y + dy, self.cells[y][x])
        return out

    def flip(self, axis: str) -> "Grid":
        if axis == "h":
            return Grid(self.width, self.height, [r[::-1] for r in self.cells])
        if axis == "v":
            return Grid(self.width, self.height, [r[:] for r in self.cells[::-1]])
        raise GridError(f"flip must be 'h' or 'v', got {axis!r}")

    def composite(self, top: "Grid") -> "Grid":
        """Paint `top` over this grid; transparent cells in `top` show through."""
        out = self.copy()
        for y in range(min(self.height, top.height)):
            for x in range(min(self.width, top.width)):
                c = top.cells[y][x]
                if c != TRANSPARENT:
                    out.cells[y][x] = c
        return out

    def replace(self, old: str, new: str) -> "Grid":
        return Grid(self.width, self.height,
                    [[new if c == old else c for c in r] for r in self.cells])

    def diff(self, other: "Grid") -> list[tuple[int, int]]:
        """Coordinates where the two grids differ."""
        return [(x, y)
                for y in range(max(self.height, other.height))
                for x in range(max(self.width, other.width))
                if self.get(x, y) != other.get(x, y)]

    # ---- debug ------------------------------------------------------------------------
    def to_ruled_text(self) -> str:
        """Text with column/row numbers, for pointing at exact pixels."""
        tens = "    " + "".join(str(x // 10) if x % 10 == 0 else " " for x in range(self.width))
        ones = "    " + "".join(str(x % 10) for x in range(self.width))
        body = [f"{y:>3} " + "".join(r) for y, r in enumerate(self.cells)]
        return "\n".join([tens, ones, *body])
