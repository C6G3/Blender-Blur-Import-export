"""Collects every Blur effect's passes, inputs and typical values from the game's models.

    python tools/scan_effects.py F:/Games/BLUR [26Viewer/tools/research] [out.json]

For each effect file (veh_Paint_a.fx...), over all parts drawn with it: the
render-list entries of its passes (effect name and inputs: name, type, count),
the most common value of every number input, which texture names fill each
texture input, and how many parts / models use it. Writes the material presets
the add-on ships (blur_presets/effects.json).
"""

import collections
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from blur import model  # noqa: E402


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else "F:/Games/BLUR"
    research = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "..",
                                                                     "26Viewer", "tools", "research")
    out_path = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(__file__), "..", "presets",
                                                                     "effects.json")
    sys.path.insert(0, research)
    import blur_pak

    effects = {}
    for pak in ("root.pak", "boot.pak"):
        f, version, entries = blur_pak.parse(os.path.join(game, "cache", pak))
        for entry in entries:
            path = entry[0].replace("\\", "/").lstrip("/")
            if not path.lower().endswith(".model"):
                continue
            try:
                m = model.read(blur_pak.read(f, version, entry))
            except model.ModelError:
                continue
            for g in m.groups:
                if g.material >= len(m.effects):
                    continue
                fx = m.effects[g.material]
                e = effects.setdefault(fx.lower(), dict(name=fx, parts=0, models=set(), layouts=collections.Counter(),
                                                        values=collections.defaultdict(collections.Counter),
                                                        textures=collections.defaultdict(collections.Counter),
                                                        folders=collections.Counter(), skinned=0, shadow=0))
                e["parts"] += 1
                e["models"].add(path)
                e["folders"][path.rsplit("/", 1)[0]] += 1
                e["shadow"] += g.shadow
                vb = m.vertex_buffers[g.vertex_buffer]
                # skinned: bone slots (texcoord 3, four bytes) and weights (texcoord 4, 0..1);
                # cars use the same sets the other way round for damage data
                if vb.element(model.TEXCOORD, 3, (model.UBYTE4,)) and vb.element(model.TEXCOORD, 4, (model.UBYTE4N,)):
                    e["skinned"] += 1
                passes = []
                for v in g.pass_values:
                    if v >= len(m.value_sets):
                        passes = None
                        break
                    vs = m.value_sets[v]
                    entry_ = m.render_list[vs.entry]
                    passes.append((entry_.effect, tuple((i.name, i.type, i.count) for i in entry_.inputs)))
                    for name, values in vs.constants:
                        e["values"][name][tuple(round(x, 5) for x in values)] += 1
                    for name, values in vs.integers:
                        e["values"][name][tuple(values)] += 1
                    for name, index in vs.textures:
                        t = m.texture_for(index)
                        e["textures"][name][t.name if t else "(not held)"] += 1
                if passes:
                    # the vertex layout this effect is drawn with
                    layout = tuple((el.type, el.usage, el.index) for el in vb.elements)
                    e["layouts"][(tuple(passes), layout)] += 1
        print(pak, "done", len(effects), "effects so far")

    out = {}
    for key, e in sorted(effects.items()):
        if not e["layouts"]:
            continue
        (passes, layout), count = e["layouts"].most_common(1)[0]
        out[e["name"]] = dict(
            parts=e["parts"], models=len(e["models"]), shadow=e["shadow"] == e["parts"], skinned=e["skinned"] > 0,
            folder=e["folders"].most_common(1)[0][0],
            passes=[dict(effect=fx, inputs=[dict(name=n, type=model.INPUT_TYPE_NAMES[t], count=c) for n, t, c in inp])
                    for fx, inp in passes],
            vertex=[dict(type=t, usage=u, index=i) for t, u, i in layout],
            variants=len(e["layouts"]),
            defaults={name: list(c.most_common(1)[0][0]) for name, c in sorted(e["values"].items())},
            textures={name: [n for n, _ in c.most_common(5)] for name, c in sorted(e["textures"].items())},
        )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print(len(out), "effects written to", out_path)


if __name__ == "__main__":
    main()
