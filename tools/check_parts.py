"""Checks blur/parts.py on every .model in Blur's archives.

    python tools/check_parts.py F:/Games/BLUR [path to 26Viewer/tools/research]

For each model, every part is "edited" with its own geometry (its vertices and
its triangles, decoded from the file), the buffers are rebuilt, the scene is
written, put back into the model and read again. A model passes when every
part then draws the same triangles with the same vertex bytes at every level
of detail. Also checks the strip maker on random triangle lists.
"""

import collections
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from blur import chunks, parts, scene  # noqa: E402


def drawn(s, p, lod):
    """(vertex rows per triangle corner) of part p at level lod, as a sorted array of bytes."""
    start, count, lo, n = p.lods[lod]
    if not count:
        return b""
    ib = np.frombuffer(parts.index_buffer(s, p.ib)["blob"]["data"], np.uint16)
    tris = parts.strip_triangles(ib[start:start + count])
    raw = parts.rows(parts.vertex_buffer(s, p.vb))
    corners = raw[tris + p.base]                       # (t, 3, stride)
    # a triangle as its corners' bytes, rotated to start at the smallest corner
    flat = [tuple(bytes(c) for c in t) for t in corners]
    canon = [min(t[i:] + t[:i] for i in range(3)) for t in flat]
    return sorted(canon)


def edit_of(s, p):
    raw = parts.rows(parts.vertex_buffer(s, p.vb))
    span = p.span
    lods = []
    ib = np.frombuffer(parts.index_buffer(s, p.ib)["blob"]["data"], np.uint16)
    for start, count, lo, n in p.lods:
        lods.append(parts.strip_triangles(ib[start:start + count]) if count else None)
    return parts.Edit(raw[p.base:p.base + span].copy(), lods)


def check(data):
    root = chunks.parse(data)
    path = chunks.find_path(root, "Scene") if root else []
    if not path:
        return "no scene"
    s = scene.read(data, path[-1].payload_offset, path[-1].offset + path[-1].size)
    ps = [p for p in parts.parts(s) if p.vb is not None]
    if not ps:
        return None
    before = {p.key: [drawn(s, p, i) for i in range(len(p.lods))] for p in ps}
    edits = {p.key: edit_of(s, p) for p in ps}
    parts.rebuild(s, edits)
    new = chunks.replace_payload(data, path, scene.write(s))
    root2 = chunks.parse(new)
    path2 = chunks.find_path(root2, "Scene")
    s2 = scene.read(new, path2[-1].payload_offset, path2[-1].offset + path2[-1].size)
    if s2["_end"] != path2[-1].offset + path2[-1].size:
        return "scene doesn't end with its chunk"
    if [c.name for c in root2.children] != [c.name for c in root.children]:
        return "chunk tree changed"
    after = {p.key: p for p in parts.parts(s2)}
    for key, old in before.items():
        p = after[key]
        for i, tris in enumerate(old):
            if drawn(s2, p, i) != tris:
                return f"part {key} level {i} draws differently"
    return None


def check_strips(rng):
    for _ in range(300):
        n = rng.integers(3, 40)
        tris = rng.integers(0, n, size=(rng.integers(1, 60), 3))
        tris = tris[(tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])]
        got = parts.strip_triangles(parts.make_strip(tris))
        canon = lambda t: sorted(min(tuple(x[i:]) + tuple(x[:i]) for i in range(3)) for x in t.tolist())
        if canon(got) != canon(tris):
            return f"strip of {tris.tolist()} draws {got.tolist()}"
    return None


def main():
    why = check_strips(np.random.default_rng(1))
    print("strips:", why or "ok")
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
            try:
                why = check(blur_pak.read(f, version, entry))
            except (parts.PartsError, scene.SceneError) as e:
                why = f"{type(e).__name__}: {e}"
            if why:
                key = why.split(" part ")[0][:60] if "part" in why else why[:60]
                fails[key] += 1
                examples.setdefault(key, (entry[0], why))
    print(f"{total - sum(fails.values())} of {total} models rebuilt with the same drawing")
    for key, n in fails.most_common():
        print(f"  {n} x {key}\n      e.g. {examples[key][0]}: {examples[key][1]}")


if __name__ == "__main__":
    main()
