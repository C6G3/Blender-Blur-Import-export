"""Reads every .model in Blur's archives and prints totals (a check of the reader).

    python tools/check_all_models.py F:/Games/BLUR [path to 26Viewer/tools/research]

Needs 26Viewer's research pak reader (tools/research/blur_pak.py) to open the
.pak archives. Prints models read, failures and level-0 triangles (no shadow
hulls) per archive: the same numbers as `26viewer-cli media <pak> .model`.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from blur import model  # noqa: E402


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else "F:/Games/BLUR"
    research = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "..",
                                                                     "26Viewer", "tools", "research")
    sys.path.insert(0, research)
    import blur_pak

    for name in ("root.pak", "boot.pak"):
        f, version, entries = blur_pak.parse(os.path.join(game, "cache", name))
        start = time.time()
        models = failures = triangles = 0
        for entry in entries:
            if not entry[0].lower().endswith(".model"):
                continue
            try:
                m = model.read(blur_pak.read(f, version, entry))
            except model.ModelError as e:
                failures += 1
                print("  ", entry[0], e)
                continue
            models += 1
            triangles += sum(len(model.triangles(m, g, 0)) for g in m.groups if not g.shadow)
        print(f"{name}: {models} model(s), {triangles} triangles, {failures} failure(s) in {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
