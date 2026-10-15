"""Textures for a model's scene: new keyed textures from pictures, and DXT compression.

A keyed texture (the scene object's table, not streamed) is the record
blur.scene.keyed_texture reads: name, u32 key, kind 2, the name again, sampler
words, u32 hash (= the key in every model), then its data:

    u32 width, height, depth (1), mip count, format (FourCC / D3DFORMAT), 0, 3
    the whole mip chain, largest first

The sampler's last word is 1 for colour textures and 0 for data (normal maps,
masks): checked over the cars' tables. Keys only need to be unique; the game's
own look like the exporter's IDs.
"""

import copy
import struct
import zlib

import numpy as np

from . import dds

SAMPLER = [0, 0, 0, 1, 1, 1, 0, 0, 0, 1]


def data_record(code, width, height, mips, pixels):
    return struct.pack("<7I", width, height, 1, mips, code, 0, 3) + bytes(pixels)


def new_key(name, pixels, taken):
    key = zlib.crc32(name.encode("utf-8") + bytes(pixels[:4096])) or 1
    while key in taken or key == 0xFFFFFFFF:
        key = (key * 1103515245 + 12345) & 0xFFFFFFFF
    return key


def add_keyed(scene_dict, name, code, width, height, mips, pixels, colour=True):
    """Appends a keyed texture to the scene object; returns its number in the table."""
    table = scene_dict["scene"]["keyed"]
    key = new_key(name, pixels, {t["key"] for t in table})
    if table:
        rec = copy.deepcopy(table[0])
    else:
        rec = {"_vw": 0, "_v": 0, "kind": 2, "_vs": 1}
    rec.update(name=name, key=key, name2=name, kind=2, hash=key,
               data=data_record(code, width, height, mips, pixels))
    sampler = list(rec.get("sampler") or SAMPLER)
    if len(sampler) < 10:
        sampler = SAMPLER[:]
        rec["_vs"] = 1
    sampler[9] = 1 if colour else 0
    rec["sampler"] = sampler
    table.append(rec)
    return len(table) - 1


# ---- pictures -> compressed mip chains -----------------------------------------------------------

def mip_chain(rgba):
    """[level arrays] from (h, w, 4) uint8 down to 1x1 (2x2 box filter)."""
    levels = [rgba]
    cur = rgba.astype(np.float32)
    while cur.shape[0] > 1 or cur.shape[1] > 1:
        h, w = cur.shape[:2]
        if h > 1:
            cur = (cur[0:h - h % 2:2] + cur[1:h:2]) / 2
        if w > 1:
            cur = (cur[:, 0:w - w % 2:2] + cur[:, 1:w:2]) / 2
        levels.append(np.clip(np.rint(cur), 0, 255).astype(np.uint8))
    return levels


def _blocks(img):
    """(n, 16, 4) float blocks of 4x4 pixels (edges repeated to fill)."""
    h, w = img.shape[:2]
    ph, pw = (h + 3) // 4 * 4, (w + 3) // 4 * 4
    if (ph, pw) != (h, w):
        img = np.pad(img, ((0, ph - h), (0, pw - w), (0, 0)), mode="edge")
    b = img.reshape(ph // 4, 4, pw // 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 4)
    return b.astype(np.float32)


def _565(c):
    c = np.clip(np.rint(c), 0, 255).astype(np.int32)
    return ((c[..., 0] >> 3) << 11) | ((c[..., 1] >> 2) << 5) | (c[..., 2] >> 3)


def _from565(v):
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], -1).astype(np.float32)


def _colour_blocks(b):
    """DXT colour halves (n, 8 bytes): endpoints along the block's main colour axis."""
    rgb = b[:, :, :3]
    mean = rgb.mean(axis=1, keepdims=True)
    centred = rgb - mean
    cov = np.einsum("npi,npj->nij", centred, centred)
    axis = np.ones((len(b), 3), np.float32)
    for _ in range(4):                                   # power iteration
        axis = np.einsum("nij,nj->ni", cov, axis)
        axis /= np.maximum(np.linalg.norm(axis, axis=1, keepdims=True), 1e-6)
    t = np.einsum("npi,ni->np", centred, axis)
    lo = mean[:, 0] + axis * t.min(1, keepdims=True)
    hi = mean[:, 0] + axis * t.max(1, keepdims=True)
    c0, c1 = _565(hi), _565(lo)
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    p0, p1 = _from565(c0), _from565(c1)
    palette = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], 1)          # (n, 4, 3)
    d = ((rgb[:, :, None, :] - palette[:, None, :, :]) ** 2).sum(-1)                # (n, 16, 4)
    idx = d.argmin(-1).astype(np.uint32)
    idx = np.where((c0 == c1)[:, None], 0, idx)
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(1).astype(np.uint32)
    out = np.zeros((len(b), 8), np.uint8)
    out[:, 0:2] = c0.astype("<u2").view(np.uint8).reshape(-1, 2)
    out[:, 2:4] = c1.astype("<u2").view(np.uint8).reshape(-1, 2)
    out[:, 4:8] = bits.astype("<u4").view(np.uint8).reshape(-1, 4)
    return out


def _alpha_blocks(b):
    """DXT5 alpha halves (n, 8 bytes)."""
    a = b[:, :, 3]
    a0, a1 = a.max(1), a.min(1)
    a0 = np.clip(np.rint(a0), 0, 255).astype(np.int32)
    a1 = np.clip(np.rint(a1), 0, 255).astype(np.int32)
    a0 = np.where(a0 == a1, np.minimum(a1 + 1, 255), a0)
    a1 = np.where(a0 == a1, a0 - 1, a1)
    steps = np.stack([a0, a1] + [((8 - k) * a0 + (k - 1) * a1) / 7 for k in range(2, 8)], 1)   # (n, 8)
    idx = np.abs(a[:, :, None] - steps[:, None, :]).argmin(-1).astype(np.uint64)
    bits = (idx << (3 * np.arange(16, dtype=np.uint64))).sum(1)
    out = np.zeros((len(b), 8), np.uint8)
    out[:, 0] = a0
    out[:, 1] = a1
    out[:, 2:8] = bits.astype("<u8").view(np.uint8).reshape(-1, 8)[:, :6]
    return out


def compress(rgba, alpha):
    """(format code, mip count, bytes) of an (h, w, 4) uint8 picture: DXT5 when `alpha`, else DXT1."""
    levels = mip_chain(rgba)
    out = []
    for lv in levels:
        b = _blocks(lv)
        if alpha:
            out.append(np.concatenate([_alpha_blocks(b), _colour_blocks(b)], 1).tobytes())
        else:
            out.append(_colour_blocks(b).tobytes())
    return (dds.DXT5 if alpha else dds.DXT1), len(levels), b"".join(out)


def decompress_dxt1(data, w, h):
    """Top level of a DXT1 picture as (h, w, 3) uint8 (for checks)."""
    n = max(1, (w + 3) // 4) * max(1, (h + 3) // 4)
    blk = np.frombuffer(data[:8 * n], np.uint8).reshape(n, 8)
    c0 = blk[:, 0:2].copy().view("<u2")[:, 0].astype(np.int32)
    c1 = blk[:, 2:4].copy().view("<u2")[:, 0].astype(np.int32)
    p0, p1 = _from565(c0), _from565(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], 1)
    bits = blk[:, 4:8].copy().view("<u4")[:, 0]
    idx = (bits[:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3
    px = np.take_along_axis(pal, idx[:, :, None].astype(np.int64).repeat(3, 2), 1)
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    img = px.reshape(bh, bw, 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 3)
    return np.clip(np.rint(img[:h, :w]), 0, 255).astype(np.uint8)


# ---- textures held by a model ---------------------------------------------------------------------

class Stored:
    """A texture in the model's scene: every mip level, largest first."""

    def __init__(self, name, source, code, width, height, mips, pixels, streamed):
        self.name, self.source, self.format = name, source, code
        self.width, self.height, self.mip_count = width, height, mips
        self.pixels, self.streamed = pixels, streamed


def stored(scene_dict):
    """Every texture the scene holds: the keyed table ("k:<n>"), then each package's streamed
    ones ("p:<package>:<n>"). A streamed texture's level 0 copy holds the small sizes (a
    whole chain from 16x16 or so down), each of levels 1-9 one larger size (its top level)."""
    out = []
    for i, t in enumerate(scene_dict["scene"]["keyed"]):
        d = t["data"]
        if len(d) < 28:
            continue
        w, h, depth, mips, code = struct.unpack_from("<5I", d, 0)
        if code not in dds.FORMATS or not w or not h:
            continue
        size = dds.chain_size(code, w, h, mips)
        out.append(Stored(t["name"], f"k:{i}", code, w, h, mips, bytes(d[28:28 + size]), False))
    for pi, p in enumerate(scene_dict["packages"]):
        levels = p["levels"]
        for j, first in enumerate(levels[0]["textures"]):
            copies = []
            for lv in levels:
                tex = lv["textures"][j] if j < len(lv["textures"]) else None
                if tex and tex.get("copy"):
                    copies.append(tex["copy"])
            if not copies:
                continue
            copies.sort(key=lambda c: -c["head"][1] * c["head"][2])
            _, w, h, depth, mips0, code = copies[0]["head"][:6]
            if code not in dds.FORMATS:
                continue
            chain, mips = [], 0
            for c in copies[:-1]:                 # the larger sizes: their top level
                cw, ch = c["head"][1], c["head"][2]
                chain.append(bytes(c["blob"]["data"][:dds.surface_size(code, cw, ch)]))
                mips += 1
            last = copies[-1]                     # the small sizes: a whole chain
            lw, lh, lm = last["head"][1], last["head"][2], last["head"][4]
            chain.append(bytes(last["blob"]["data"][:dds.chain_size(code, lw, lh, lm)]))
            mips += lm
            out.append(Stored(first.get("name", ""), f"p:{pi}:{j}", code, w, h, mips, b"".join(chain), True))
    return out
