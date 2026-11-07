import json
import tempfile
from pathlib import Path

from pixelforge import model


class TempProject:
    """Points pixelforge at a throwaway project root for the duration of a test."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        model.set_root(self.root)
        return self

    def __exit__(self, *exc):
        model.set_root(None)
        self._tmp.cleanup()

    def sprite(self, name, size, palette, frames, animations, origin=None):
        d = self.root / "sprites" / name
        (d / "frames").mkdir(parents=True)
        for fid, text in frames.items():
            (d / "frames" / f"{fid}.txt").write_text(text)
        meta = {"name": name, "size": list(size), "palette": palette, "animations": animations}
        if origin:
            meta["origin"] = origin
        (d / "sprite.json").write_text(json.dumps(meta))
        return d
