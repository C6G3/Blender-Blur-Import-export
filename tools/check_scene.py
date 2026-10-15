"""Reads the scene stream of every .model in Blur's archives and writes it back.

    python tools/check_scene.py F:/Games/BLUR [path to 26Viewer/tools/research]

A model passes when blur/scene.py reads its Render/Scene chunk to the exact end
and writing what it read gives the same bytes. Prints the failures grouped by
reason, with one example each.
"""

import collections
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from blur import chunks, scene  # noqa: E402


def scene_end(data):
    found = []

    def walk(c):
        if c.name == "Scene":
            found.append(c.offset + c.size)
        for k in c.children:
            walk(k)
    walk(chunks.parse(data))
    return found[0] if found else None


def check(data):
    """None if the model round-trips, else the reason."""
    start, end = data.find(b"ARCH"), scene_end(data)
    if start < 0 or end is None:
        return "no scene"
    try:
        s = scene.read(data, start, end)
    except scene.SceneError as e:
        return f"read: {e}"
    if s["_end"] != end:
        return f"read: stopped at {s['_end']:#x}, the scene ends at {end:#x}"
    out = scene.write(s)
    if out != data[start:end]:
        at = next((i for i, (a, b) in enumerate(zip(out, data[start:end])) if a != b), min(len(out), end - start))
        return f"write: differs at +{at:#x} (wrote {len(out):#x} bytes of {end - start:#x})"
    return None


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else "F:/Games/BLUR"
    research = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "..",
                                                                     "26Viewer", "tools", "research")
    sys.path.insert(0, research)
    import blur_pak

    fails, examples, total = collections.Counter(), {}, 0
    for name in ("root.pak", "boot.pak"):
        f, version, entries = blur_pak.parse(os.path.join(game, "cache", name))
        for entry in entries:
            if not entry[0].lower().endswith(".model"):
                continue
            total += 1
            why = check(blur_pak.read(f, version, entry))
            if why:
                key = why.split(" at ")[0].split(" (")[0][:70]
                fails[key] += 1
                examples.setdefault(key, (entry[0], why))
    print(f"{total - sum(fails.values())} of {total} model scene(s) read and written back byte for byte")
    for key, n in fails.most_common():
        print(f"  {n} x {key}\n      e.g. {examples[key][0]}: {examples[key][1]}")


if __name__ == "__main__":
    main()
