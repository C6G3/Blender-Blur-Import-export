"""Pixel formats of Blur textures and .dds files for them.

Blur stores textures with Direct3D 9 format codes: a FourCC for compressed
ones ("DXT1"...) or a D3DFORMAT number (21 = A8R8G8B8). A .dds holding the
pixels as they are lets Blender show them, and keeps them byte-exact for export.
Same layout as 26Viewer's image::writeDds.
"""

import struct


def fourcc(text):
    return struct.unpack("<I", text.encode("ascii"))[0]


DXT1, DXT3, DXT5, ATI1, ATI2 = (fourcc(t) for t in ("DXT1", "DXT3", "DXT5", "ATI1", "ATI2"))
R8G8B8, A8R8G8B8, X8R8G8B8, R5G6B5, A1R5G5B5, A4R4G4B4, A8, A8B8G8R8, L8, A8L8 = 20, 21, 22, 23, 25, 26, 28, 32, 50, 51

# code -> (name, block bytes for compressed / bytes per pixel, compressed)
FORMATS = {
    DXT1: ("DXT1", 8, True),
    DXT3: ("DXT3", 16, True),
    DXT5: ("DXT5", 16, True),
    ATI1: ("ATI1", 8, True),
    ATI2: ("ATI2", 16, True),
    R8G8B8: ("R8G8B8", 3, False),
    A8R8G8B8: ("A8R8G8B8", 4, False),
    X8R8G8B8: ("X8R8G8B8", 4, False),
    R5G6B5: ("R5G6B5", 2, False),
    A1R5G5B5: ("A1R5G5B5", 2, False),
    A4R4G4B4: ("A4R4G4B4", 2, False),
    A8: ("A8", 1, False),
    A8B8G8R8: ("A8B8G8R8", 4, False),
    L8: ("L8", 1, False),
    A8L8: ("A8L8", 2, False),
}


def name(code):
    return FORMATS[code][0] if code in FORMATS else f"format {code}"


def surface_size(code, w, h):
    _, unit, compressed = FORMATS[code]
    if compressed:
        return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * unit
    return w * h * unit


def chain_size(code, w, h, mips):
    total = 0
    for _ in range(mips):
        total += surface_size(code, w, h)
        w, h = max(1, w // 2), max(1, h // 2)
    return total


def full_mip_count(w, h):
    levels, size = 1, max(w, h)
    while size > 1:
        size //= 2
        levels += 1
    return levels


def write(code, width, height, mips, pixels):
    """A .dds file holding `pixels` (every mip level, largest first) unchanged."""
    ALPHAPIXELS, ALPHA, FOURCC, RGB, LUMINANCE = 0x1, 0x2, 0x4, 0x40, 0x20000
    masks = {
        A8R8G8B8: (RGB | ALPHAPIXELS, 0, 32, 0xFF0000, 0xFF00, 0xFF, 0xFF000000),
        X8R8G8B8: (RGB, 0, 32, 0xFF0000, 0xFF00, 0xFF, 0),
        A8B8G8R8: (RGB | ALPHAPIXELS, 0, 32, 0xFF, 0xFF00, 0xFF0000, 0xFF000000),
        R8G8B8: (RGB, 0, 24, 0xFF0000, 0xFF00, 0xFF, 0),
        R5G6B5: (RGB, 0, 16, 0xF800, 0x07E0, 0x001F, 0),
        A1R5G5B5: (RGB | ALPHAPIXELS, 0, 16, 0x7C00, 0x03E0, 0x001F, 0x8000),
        A4R4G4B4: (RGB | ALPHAPIXELS, 0, 16, 0x0F00, 0x00F0, 0x000F, 0xF000),
        L8: (LUMINANCE, 0, 8, 0xFF, 0, 0, 0),
        A8: (ALPHA, 0, 8, 0, 0, 0, 0xFF),
        A8L8: (LUMINANCE | ALPHAPIXELS, 0, 16, 0xFF, 0, 0, 0xFF00),
    }
    compressed = FORMATS[code][2]
    pf = (FOURCC, code, 0, 0, 0, 0, 0) if compressed else masks[code]
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | (0x80000 if compressed else 0x8)
    if mips > 1:
        flags |= 0x20000
    pitch = surface_size(code, width, height) if compressed else surface_size(code, width, 1)
    caps = 0x1000 | (0x8 | 0x400000 if mips > 1 else 0)
    header = [0] * 32
    header[0] = 0x20534444  # "DDS "
    header[1] = 124
    header[2] = flags
    header[3] = height
    header[4] = width
    header[5] = pitch
    header[7] = mips
    header[19] = 32
    header[20:27] = pf
    header[27] = caps
    return struct.pack("<32I", *header) + bytes(pixels[:chain_size(code, width, height, mips)])


def read(data):
    """(code, width, height, mips, pixels) of a .dds file (DX9 header), or None."""
    if len(data) < 128 or data[:4] != b"DDS ":
        return None
    h = struct.unpack_from("<32I", data, 0)
    height, width, mips = h[3], h[4], max(1, h[7])
    flags, cc, bits, r, g, b, a = h[20:27]
    if flags & 0x4:
        code = cc
    else:
        by_masks = {
            (32, 0xFF0000, 0xFF00, 0xFF, 0xFF000000): A8R8G8B8,
            (32, 0xFF0000, 0xFF00, 0xFF, 0): X8R8G8B8,
            (32, 0xFF, 0xFF00, 0xFF0000, 0xFF000000): A8B8G8R8,
            (24, 0xFF0000, 0xFF00, 0xFF, 0): R8G8B8,
            (16, 0xF800, 0x07E0, 0x001F, 0): R5G6B5,
            (16, 0x7C00, 0x03E0, 0x001F, 0x8000): A1R5G5B5,
            (16, 0x0F00, 0x00F0, 0x000F, 0xF000): A4R4G4B4,
            (8, 0xFF, 0, 0, 0): L8,
            (8, 0, 0, 0, 0xFF): A8,
            (16, 0xFF, 0, 0, 0xFF00): A8L8,
        }
        code = by_masks.get((bits, r, g, b, a if flags & 0x3 else 0))
    if code not in FORMATS:
        return None
    pixels = data[128:]
    while mips > 1 and chain_size(code, width, height, mips) > len(pixels):
        mips -= 1
    if chain_size(code, width, height, mips) > len(pixels):
        return None
    return code, width, height, mips, pixels[:chain_size(code, width, height, mips)]
