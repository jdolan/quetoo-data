#!/usr/bin/env python3
"""
Convert a bspc-decompiled Quake 1 .map to Quetoo textures and entities.

Usage:
    q1_to_quetoo.py <source.bsp> <decompiled.map> <output.map>

The .bsp is read for the original texture dimensions, so that texture scale and shift
can be rescaled to the higher resolution textures in textures/quake.
"""

import math
import os
import re
import struct
import sys

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../target/default")
QUAKE_TEXTURES = os.path.join(DATA, "textures/quake")

# Quake 1 textures with no counterpart in textures/quake, and the closest substitute.
SUBSTITUTES = {
    "ecop1_1": "cop1_1",
    "ecop1_4": "cop1_4",
    "ecop1_6": "cop1_6",
    "ecop1_7": "cop1_7",
    "nmetal2_1": "metal2_1",
    "metal5_1": "metal5_2",
    "metal5_8": "m5_8",
    "metalt2_3": "metalt2_1",
    "metalt2_8": "metalt2_1",
    "metflor1_2": "metal1_2",
    "plat_top1": "plat_top2",
    "sfloor1_2": "sfloor1_1",
    "tech01_6": "tech01_5",
    "tlight01_2": "tlight01",
    "tlight08": "tlight07",
    "uwall1_2": "uwall1_3",
    "04mwat2": "water2",
    "teleport": "teleport_no_portal",
}

COMMON = {
    "trigger": "common/trigger",
    "clip": "common/clip",
}

# Quake 1 light styles 0 - 11, from world.qc.
LIGHT_STYLES = [
    "m",
    "mmnmmommommnonmmonqnmmo",
    "abcdefghijklmnopqrstuvwxyzyxwvutsrqponmlkjihgfedcba",
    "mmmmmaaaaammmmmaaaaaabcdefgabcdefg",
    "mamamamamama",
    "jklmnopqrstuvwxyzyxwvutsrqponmlkj",
    "nmonqnmomnmomomno",
    "mmmaaaabcdefgmmmmaaaammmaamm",
    "mmmaaammmaaammmabcdefaaaammmmabcdefmmmaaaa",
    "aaaaaaaazzzzzzzz",
    "mmamammmmammamamaaamammma",
    "abcdefghijklmnopqrrqponmlkjihgfedcba",
]

RENAME = {
    "weapon_supershotgun": "weapon_quake_supershotgun",
    "weapon_nailgun": "weapon_quake_nailgun",
    "weapon_supernailgun": "weapon_quake_supernailgun",
    "weapon_grenadelauncher": "weapon_quake_grenadelauncher",
    "weapon_rocketlauncher": "weapon_quake_rocketlauncher",
    "weapon_lightning": "weapon_quake_thunderbolt",
    "item_shells": "ammo_quake_shells",
    "item_spikes": "ammo_quake_nails",
    "item_rockets": "ammo_quake_rockets",
    "item_cells": "ammo_quake_bolts",
    "item_armor1": "item_quake_armor_jacket",
    "item_armor2": "item_quake_armor_combat",
    "item_armorInv": "item_quake_armor_body",
    "item_artifact_super_damage": "item_quad",
    "item_artifact_invisibility": "item_invisibility",
    "item_artifact_invulnerability": "item_invulnerability",
    "info_teleport_destination": "misc_teleporter_dest",
    "info_intermission": "info_player_intermission",
    "trigger_teleport": "trigger_teleporter",
}

REMOVE = {
    "info_player_coop",
    "info_null",
    "item_key1",
    "item_key2",
    "item_artifact_envirosuit",
    "misc_explobox",
    "misc_explobox2",
    "trigger_changelevel",
    "trigger_secret",
}

AMBIENT_SOUNDS = {
    "ambient_drip": "ambient/drip_1",
    "ambient_comp_hum": "ambient/comp",
    "ambient_swamp1": "ambient/frogs_1",
    "ambient_swamp2": "ambient/crickets_1",
    "ambient_drone": "ambient/drone_1",
    "ambient_suck_wind": "ambient/wind_1",
    "ambient_flouro_buzz": "ambient/hum",
    "ambient_light_buzz": "ambient/hum2",
    "ambient_thunder": "ambient/thunder_1",
}

# Quake 1 light entity variants: (default style, flame radius, sound)
LIGHT_VARIANTS = {
    "light": (None, None, None),
    "light_globe": (None, None, None),
    "light_torch_small_walltorch": (None, 8, None),
    "light_flame_small_yellow": (None, 8, None),
    "light_flame_small_white": (None, 8, None),
    "light_flame_large_yellow": (None, 16, None),
    "light_fluoro": (None, None, "ambient/hum"),
    "light_fluorospark": (10, None, "ambient/sparks"),
}

# The Quake 1 light compiler gives every light without a light key this value.
Q1_LIGHT_DEFAULT = 300

# MAX_BSP_LIGHTS is 512, and materials add lights of their own.
LIGHT_BUDGET = 500

# Long reach lights overlap more, and quemap warns above 5 lights per voxel. On death32c, a 4x
# reach needed 60% of its lights to stay below that.
LONG_REACH_BUDGET = 0.6

# Quake 1 item boxes are not centered on the origin, as Quetoo's -16 to 16 box is.
Q1_ITEM_OFFSETS = {
    "item_health": (16, 16, 16),
    "item_shells": (16, 16, 16),
    "item_spikes": (16, 16, 16),
    "item_rockets": (16, 16, 16),
    "item_cells": (16, 16, 16),
    "item_weapon": (16, 16, 16),
    "item_armor1": (0, 0, 16),
    "item_armor2": (0, 0, 16),
    "item_armorInv": (0, 0, 16),
    "weapon_supershotgun": (0, 0, 16),
    "weapon_nailgun": (0, 0, 16),
    "weapon_supernailgun": (0, 0, 16),
    "weapon_grenadelauncher": (0, 0, 16),
    "weapon_rocketlauncher": (0, 0, 16),
    "weapon_lightning": (0, 0, 16),
}

Q1_NOT_EASY, Q1_NOT_MEDIUM, Q1_NOT_HARD, Q1_NOT_DEATHMATCH = 256, 512, 1024, 2048

# Quake 1 moves a teleported player 27 units above the destination, and Quetoo moves it 8.
Q1_TELEPORT_Z = 27
QUETOO_TELEPORT_Z = 8

# A private key that marks Quake 1 doors that must not link with the doors they touch.
DONT_LINK = "_q1_dont_link"

CONTENTS_LAVA = 0x8
CONTENTS_SLIME = 0x10
CONTENTS_WATER = 0x20
CONTENTS_DECORATION = 0x4
CONTENTS_DETAIL = 0x8000000


def read_miptex_sizes(bsp_path):
    """Returns a dict of lowercase miptex name to (width, height) from a Quake 1 BSP."""
    with open(bsp_path, "rb") as f:
        data = f.read()
    version, = struct.unpack_from("<i", data, 0)
    if version != 29:
        raise SystemExit(f"{bsp_path}: not a Quake 1 BSP (version {version})")
    offset, length = struct.unpack_from("<ii", data, 4 + 2 * 8)
    count, = struct.unpack_from("<i", data, offset)
    sizes = {}
    for i in range(count):
        mip, = struct.unpack_from("<i", data, offset + 4 + i * 4)
        if mip == -1:
            continue
        name, w, h = struct.unpack_from("<16sII", data, offset + mip)
        sizes[name.split(b"\0")[0].decode("latin-1").lower()] = (w, h)
    return sizes


class Q1Bsp:
    """Point contents lookup in the world model of a Quake 1 BSP."""

    SOLID = -2

    def __init__(self, bsp_path):
        with open(bsp_path, "rb") as f:
            data = f.read()
        lump = lambda i: struct.unpack_from("<ii", data, 4 + i * 8)
        po, pl = lump(1)
        no, nl = lump(5)
        lo, ll = lump(10)
        mo, _ = lump(14)
        self.planes = [struct.unpack_from("<ffff", data, po + i * 20) for i in range(pl // 20)]
        self.nodes = [struct.unpack_from("<ihh", data, no + i * 24) for i in range(nl // 24)]
        self.leafs = [struct.unpack_from("<i", data, lo + i * 28)[0] for i in range(ll // 28)]
        self.headnode = struct.unpack_from("<9fi", data, mo)[9]

    def contents(self, p):
        n = self.headnode
        while n >= 0:
            planenum, front, back = self.nodes[n]
            a, b, c, d = self.planes[planenum]
            n = front if a * p[0] + b * p[1] + c * p[2] - d > 0 else back
        return self.leafs[-n - 1]

    def is_open(self, p):
        """Returns True if p and its axial neighbors are not solid, so that p is off every plane."""
        if self.contents(p) == self.SOLID:
            return False
        for axis in range(3):
            for sign in (1, -1):
                q = list(p)
                q[axis] += sign
                if self.contents(q) == self.SOLID:
                    return False
        return True

    def unstick(self, p, limit=64):
        """Returns p, or the nearest axial offset of p that is open, or None."""
        if self.is_open(p):
            return p
        for dist in range(4, limit + 1, 4):
            for axis in range(3):
                for sign in (1, -1):
                    q = list(p)
                    q[axis] += sign * dist
                    if self.is_open(q):
                        return tuple(q)
        return None


def q1_light_reach(bsp_path, lights):
    """Returns how far Quake 1 lights reached, as a multiple of their light value.

    The id light tool's -dist option scales falloff, so a map compiled with -dist 0.25 lit faces
    four times farther than its light values say. The lightmap still shows it: this measures the
    distance from each lit face to the nearest light, over that light's value.
    """
    with open(bsp_path, "rb") as f:
        data = f.read()
    lump = lambda i: struct.unpack_from("<ii", data, 4 + i * 8)
    fo, fl = lump(7)
    lo, ll = lump(8)
    vo, vl = lump(3)
    eo, el = lump(12)
    so, sl = lump(13)
    verts = [struct.unpack_from("<3f", data, vo + i * 12) for i in range(vl // 12)]
    edges = [struct.unpack_from("<HH", data, eo + i * 4) for i in range(el // 4)]
    surfedges = [struct.unpack_from("<i", data, so + i * 4)[0] for i in range(sl // 4)]
    faces = [struct.unpack_from("<hhihh4Bi", data, fo + i * 20) for i in range(fl // 20)]
    offsets = sorted({f[9] for f in faces if f[9] >= 0}) + [ll]
    following = dict(zip(offsets, offsets[1:]))

    ratios = []
    for face in faces:
        if face[9] < 0:
            continue
        luxels = data[lo + face[9]:lo + following[face[9]]]
        if len(set(luxels)) <= 1 or max(luxels) < 16:
            continue
        points = [verts[edges[abs(e)][0 if e >= 0 else 1]] for e in surfedges[face[2]:face[2] + face[3]]]
        center = [sum(p[i] for p in points) / len(points) for i in range(3)]
        ratios.append(min(math.dist(center, origin) / radius for origin, radius in lights))

    if not ratios:
        return 1.0
    ratios.sort()
    reach = round(ratios[int(0.99 * (len(ratios) - 1))] * 2) / 2
    return max(reach, 1.0)


def image_size(path):
    """Returns (width, height) of a JPEG or PNG file."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data):
            if data[i] != 0xFF:
                raise SystemExit(f"{path}: bad JPEG marker at {i}")
            marker, length = struct.unpack(">BH", data[i + 1:i + 4])
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + length
    raise SystemExit(f"{path}: unsupported image format")


def quetoo_image(name):
    for ext in ("jpg", "png", "tga"):
        path = os.path.join(QUAKE_TEXTURES, f"{name}.{ext}")
        if os.path.exists(path):
            return path
    return None


class Textures:
    def __init__(self, miptex):
        self.miptex = miptex
        self.cache = {}
        self.substituted = {}
        self.sky = None

    def material_diffuse(self, name):
        """Returns the diffusemap name of a material that has no image of its own, e.g. teleport_no_portal."""
        mat = os.path.join(QUAKE_TEXTURES, f"{name}.mat")
        if os.path.exists(mat):
            m = re.search(r"diffusemap\s+quake/(\S+)", open(mat).read())
            if m:
                return m.group(1)
        return name

    def resolve(self, q1name):
        """Returns (quetoo name, x factor, y factor), or raises if the texture can not be resolved."""
        if q1name in self.cache:
            return self.cache[q1name]
        lower = q1name.lower()
        if lower.startswith("sky"):
            self.sky = self.sky or lower
            result = ("common/sky", 1.0, 1.0)
        elif lower in COMMON:
            result = (COMMON[lower], 1.0, 1.0)
        else:
            name = lower.lstrip("*")
            m = re.match(r"^\+([0-9a-j])(.*)$", name)
            if m:
                name = f"{m.group(2)}+{m.group(1)}"
                if not quetoo_image(name) and quetoo_image(m.group(2)):
                    name = m.group(2)
            if name in SUBSTITUTES and (not quetoo_image(name) or os.path.exists(os.path.join(QUAKE_TEXTURES, SUBSTITUTES[name] + ".mat"))):
                self.substituted[q1name] = SUBSTITUTES[name]
                name = SUBSTITUTES[name]
            path = quetoo_image(name) or quetoo_image(self.material_diffuse(name))
            if not path:
                raise SystemExit(f"No Quetoo texture for {q1name} (tried quake/{name})")
            if lower not in self.miptex:
                raise SystemExit(f"No miptex dimensions for {q1name} in the BSP")
            qw, qh = image_size(path)
            mw, mh = self.miptex[lower]
            result = (f"quake/{name}", qw / mw, qh / mh)
        self.cache[q1name] = result
        return result


SIDE_RE = re.compile(
    r"^(\s*\(\s*\S+\s+\S+\s+\S+\s*\)\s*\(\s*\S+\s+\S+\s+\S+\s*\)\s*\(\s*\S+\s+\S+\s+\S+\s*\))"
    r"\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$")

KV_RE = re.compile(r'^\s*"([^"]+)"\s+"([^"]*)"\s*$')


def fmt(v):
    return f"{v:.6g}"


POINT_RE = re.compile(r"\(\s*(\S+)\s+(\S+)\s+(\S+)\s*\)")


def side_plane(line):
    p = [tuple(float(x) for x in m) for m in POINT_RE.findall(line)[:3]]
    a = [p[0][i] - p[1][i] for i in range(3)]
    b = [p[2][i] - p[1][i] for i in range(3)]
    n = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
    length = math.sqrt(sum(x * x for x in n))
    n = [x / length for x in n]
    return n, sum(n[i] * p[0][i] for i in range(3))


def base_winding(n, d, size=131072.0):
    axis = max(range(3), key=lambda i: abs(n[i]))
    up = [0.0, 0.0, 1.0] if axis != 2 else [1.0, 0.0, 0.0]
    dot = sum(up[i] * n[i] for i in range(3))
    up = [up[i] - dot * n[i] for i in range(3)]
    length = math.sqrt(sum(x * x for x in up))
    up = [x / length for x in up]
    right = [up[1] * n[2] - up[2] * n[1], up[2] * n[0] - up[0] * n[2], up[0] * n[1] - up[1] * n[0]]
    o = [n[i] * d for i in range(3)]
    return [[o[i] + (sx * right[i] + sy * up[i]) * size for i in range(3)]
            for sx, sy in ((-1, 1), (1, 1), (1, -1), (-1, -1))]


def clip_winding(w, n, d):
    """Keeps the part of w behind the plane, or returns None."""
    out = []
    for i in range(len(w)):
        a, b = w[i], w[(i + 1) % len(w)]
        da = sum(n[k] * a[k] for k in range(3)) - d
        db = sum(n[k] * b[k] for k in range(3)) - d
        if da <= 0:
            out.append(a)
        if (da < 0 < db) or (db < 0 < da):
            t = da / (da - db)
            out.append([a[k] + t * (b[k] - a[k]) for k in range(3)])
    return out if len(out) >= 3 else None


def winding_area(w):
    s = [0.0, 0.0, 0.0]
    for i in range(1, len(w) - 1):
        a = [w[i][k] - w[0][k] for k in range(3)]
        b = [w[i + 1][k] - w[0][k] for k in range(3)]
        s = [s[0] + a[1] * b[2] - a[2] * b[1], s[1] + a[2] * b[0] - a[0] * b[2], s[2] + a[0] * b[1] - a[1] * b[0]]
    return 0.5 * math.sqrt(sum(x * x for x in s))


def is_closed(brush):
    windings = brush_windings(brush)
    return all(w for w in windings) and all(abs(x) < 32768 for w in windings for p in w for x in p)


def remove_redundant_sides(brush):
    """Returns the sides of brush that bound it, dropping sides that only touch it along an edge.

    A side that is small but real SHOULD survive: if dropping the small sides opens the brush,
    the brush is returned unchanged.
    """
    kept = [line for line, w in zip(brush, brush_windings(brush)) if w is not None and winding_area(w) > 0.5]
    if len(kept) == len(brush) or is_closed(kept):
        return kept
    return brush


def q1_liquid_contents(tex):
    """Returns the Quake 1 contents of a liquid texture, which Quetoo materials MAY not agree with."""
    lower = tex.lower()
    if not lower.startswith("*") or lower.startswith("*tele"):
        return None
    if lower.startswith("*lava"):
        return CONTENTS_LAVA
    if lower.startswith("*slime"):
        return CONTENTS_SLIME
    return CONTENTS_WATER


def brush_windings(brush):
    planes = [side_plane(line) for line in brush]
    windings = []
    for i, (n, d) in enumerate(planes):
        w = base_winding(n, d)
        for j, (n2, d2) in enumerate(planes):
            if i != j:
                w = clip_winding(w, n2, d2)
                if w is None:
                    break
        windings.append(w)
    return windings


def brushes_bounds(brushes):
    points = [p for brush in brushes for w in brush_windings(brush) if w for p in w]
    return ([min(p[i] for p in points) for i in range(3)], [max(p[i] for p in points) for i in range(3)])


def brushes_center(brushes):
    mins, maxs = brushes_bounds(brushes)
    return tuple((mins[i] + maxs[i]) / 2 for i in range(3))


def convert_side(line, textures, contents=None):
    m = SIDE_RE.match(line)
    if not m:
        raise SystemExit(f"Unparsed brush side: {line}")
    planes, tex, sx, sy, rot, scx, scy = m.groups()
    name, fx, fy = textures.resolve(tex)
    if contents is None:
        contents = q1_liquid_contents(tex)
    sx, sy, scx, scy = float(sx) * fx, float(sy) * fy, float(scx) / fx, float(scy) / fy
    side = f"{planes} {name} {fmt(sx)} {fmt(sy)} {rot} {fmt(scx)} {fmt(scy)}"
    if contents is not None:
        side += f" {contents} 0 0"
    return side


def parse_entities(text):
    """Returns a list of (keys, brushes), where keys is an ordered list of (key, value)."""
    entities = []
    lines = text.splitlines()
    i = 0
    depth = 0
    keys, brushes, brush = None, None, None
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        i += 1
        if not stripped or stripped.startswith("//"):
            continue
        if stripped.startswith("{"):
            depth += 1
            if depth == 1:
                keys, brushes = [], []
            else:
                brush = []
            continue
        if stripped == "}":
            depth -= 1
            if depth == 0:
                entities.append((keys, brushes))
            else:
                brushes.append(brush)
            continue
        if depth == 1:
            m = KV_RE.match(line)
            if not m:
                raise SystemExit(f"Unparsed entity line: {line}")
            keys.append((m.group(1), m.group(2)))
        elif depth == 2:
            brush.append(line)
        else:
            raise SystemExit(f"Unexpected nesting at line {i}: {line}")
    if depth != 0:
        raise SystemExit("Unbalanced braces")
    return entities


def get(keys, key, default=None):
    for k, v in keys:
        if k == key:
            return v
    return default


def put(keys, key, value):
    for idx, (k, _) in enumerate(keys):
        if k == key:
            keys[idx] = (key, value)
            return
    keys.append((key, value))


def drop(keys, *names):
    keys[:] = [(k, v) for k, v in keys if k not in names]


def convert_entity(keys, brushes, report):
    """Returns a list of (keys, brushes, contents) for the converted entity, empty to remove it."""
    classname = get(keys, "classname")
    spawnflags = int(get(keys, "spawnflags", "0"))

    if spawnflags & Q1_NOT_DEATHMATCH:
        report.append(f"removed {classname} (not in deathmatch)")
        return []
    spawnflags &= ~(Q1_NOT_EASY | Q1_NOT_MEDIUM | Q1_NOT_HARD | Q1_NOT_DEATHMATCH)

    if classname in REMOVE:
        report.append(f"removed {classname}")
        return []

    contents = None

    if classname in Q1_ITEM_OFFSETS:
        origin = [float(x) for x in get(keys, "origin").split()]
        origin = [origin[i] + Q1_ITEM_OFFSETS[classname][i] for i in range(3)]
        put(keys, "origin", " ".join(fmt(x) for x in origin))

    if classname == "worldspawn":
        drop(keys, "wad", "_wad", "worldtype", "sounds")
        return [(keys, brushes, None)]

    if classname in AMBIENT_SOUNDS:
        return [([("classname", "misc_sound"), ("origin", get(keys, "origin")),
                  ("sound", AMBIENT_SOUNDS[classname])], [], None)]

    if classname in LIGHT_VARIANTS:
        style, flame, sound = LIGHT_VARIANTS[classname]
        out = [("classname", "light"), ("origin", get(keys, "origin")),
               ("radius", get(keys, "light", str(Q1_LIGHT_DEFAULT)))]
        color = get(keys, "_color")
        if color:
            rgb = [float(x) for x in color.split()]
            if max(rgb) > 1:
                rgb = [x / 255 for x in rgb]
            out.append(("color", " ".join(fmt(x) for x in rgb)))
        q1style = int(get(keys, "style", "0"))
        if q1style == 0 and style is not None:
            q1style = style
        if 0 < q1style < len(LIGHT_STYLES):
            out.append(("style", LIGHT_STYLES[q1style]))
        result = [(out, [], None)]
        if flame:
            result.append(([("classname", "misc_flame"), ("origin", get(keys, "origin")),
                            ("radius", str(flame))], [], None))
        if sound:
            result.append(([("classname", "misc_sound"), ("origin", get(keys, "origin")),
                            ("sound", sound)], [], None))
        return result

    if classname == "item_weapon":
        if spawnflags & 1:
            classname = "ammo_quake_shells"
        elif spawnflags & 2:
            classname = "ammo_quake_rockets"
        elif spawnflags & 4:
            classname = "ammo_quake_nails"
        else:
            raise SystemExit(f"item_weapon with unknown spawnflags {spawnflags}")
        spawnflags = 0
    elif classname == "item_health":
        if spawnflags & 1:
            classname = "item_health_quake_medium"
        elif spawnflags & 2:
            classname = "item_health_quake_mega"
        else:
            classname = "item_health_quake_large"
        spawnflags = 0
    elif classname in RENAME:
        classname = RENAME[classname]
        if classname.startswith(("ammo_", "item_", "weapon_", "trigger_teleporter")):
            spawnflags = 0

    if classname == "misc_teleporter_dest":
        origin = [float(x) for x in get(keys, "origin").split()]
        origin[2] += Q1_TELEPORT_Z - QUETOO_TELEPORT_Z
        put(keys, "origin", " ".join(fmt(x) for x in origin))
    elif classname == "info_player_intermission":
        mangle = get(keys, "mangle")
        if mangle:
            put(keys, "angles", mangle)
        drop(keys, "mangle")
    elif classname == "func_door":
        if spawnflags & 4:
            put(keys, DONT_LINK, "1")
        spawnflags = (spawnflags & 1) | (16 if spawnflags & 32 else 0)
        if get(keys, "speed") is None:
            put(keys, "speed", "100")
        sounds = int(get(keys, "sounds", "0"))
        drop(keys, "sounds")
        if sounds == 0:
            put(keys, "sounds", "-1")
        elif sounds in (1, 3):
            put(keys, "sounds", "1")
    elif classname == "func_door_secret":
        if spawnflags & 1 and get(keys, "wait") is None:
            put(keys, "wait", "-1")
        spawnflags = (spawnflags & 6) | (1 if spawnflags & 16 else 0)
        drop(keys, "sounds")
        if get(keys, "wait") is None:
            put(keys, "wait", "5")
        if get(keys, "speed") is None:
            put(keys, "speed", "50")
        if get(keys, "lip") is None:
            put(keys, "lip", "0.001")
    elif classname == "func_plat":
        drop(keys, "sounds")
        if get(keys, "speed") is None:
            put(keys, "speed", "150")
    elif classname == "func_button":
        drop(keys, "sounds")
        if get(keys, "wait") is None:
            put(keys, "wait", "1")
    elif classname == "func_train":
        drop(keys, "sounds")
    elif classname in ("trigger_multiple", "trigger_once"):
        shootable = get(keys, "health") is not None
        if spawnflags & 1 and not shootable:
            relay = [("classname", "trigger_relay"), ("origin", fmt_origin(brushes_center(brushes)))]
            relay.extend((k, v) for k, v in keys if k in ("target", "targetname", "killtarget", "delay", "message"))
            report.append(f"converted {classname} (notouch) to trigger_relay")
            return [(relay, [], None)]
        if shootable:
            report.append(f"{classname} is shootable, and in Quetoo it also fires on touch")
        spawnflags = 2 if shootable else 0
        drop(keys, "sounds", "health")
        if classname == "trigger_multiple" and get(keys, "wait") is None:
            put(keys, "wait", "0.2")
    elif classname == "func_illusionary":
        classname = "func_group"
        contents = CONTENTS_DECORATION | CONTENTS_DETAIL

    put(keys, "classname", classname)
    drop(keys, "spawnflags")
    if spawnflags:
        put(keys, "spawnflags", str(spawnflags))
    return [(keys, brushes, contents)]


def origin_of(keys):
    return tuple(float(x) for x in get(keys, "origin").split())


def fmt_origin(p):
    return " ".join(fmt(x) for x in p)


def unstick_point_entities(out, q1, report):
    """Moves lights and sounds that Quake 1 tolerated inside walls to the nearest open point."""
    result = []
    for keys, brushes, contents in out:
        classname = get(keys, "classname")
        if classname in ("light", "misc_sound", "misc_flame") and not brushes:
            p = origin_of(keys)
            q = q1.unstick(p)
            if q is None:
                report.append(f"removed {classname} (in solid)")
                continue
            if q != p:
                put(keys, "origin", fmt_origin(q))
                report.append(f"moved {classname} out of solid")
        result.append((keys, brushes, contents))
    return result


def link_doors(out, report):
    """Teams touching func_doors, as Quake 1 links them, and shares their activation keys.

    Quake 1 copies targetname, health and message to the master of linked doors, so the whole
    group opens together. Quetoo spawns a proximity trigger for any team master without them.
    """
    doors = [e for e in out if get(e[0], "classname") == "func_door" and e[1]]
    bounds = [brushes_bounds(e[1]) for e in doors]

    def touching(a, b):
        return all(a[0][i] <= b[1][i] and b[0][i] <= a[1][i] for i in range(3))

    team = list(range(len(doors)))

    def find(i):
        while team[i] != i:
            team[i] = team[team[i]]
            i = team[i]
        return i

    for i in range(len(doors)):
        if get(doors[i][0], DONT_LINK):
            continue
        for j in range(i + 1, len(doors)):
            if not get(doors[j][0], DONT_LINK) and touching(bounds[i], bounds[j]):
                team[find(j)] = find(i)

    groups = {}
    for i in range(len(doors)):
        groups.setdefault(find(i), []).append(doors[i][0])

    linked = 0
    for n, members in enumerate(g for g in groups.values() if len(g) > 1):
        linked += 1
        for keys in members:
            put(keys, "team", f"q1_door_{n}")
        for key in ("targetname", "health", "message"):
            values = {get(k, key) for k in members if get(k, key) is not None}
            if len(values) == 1:
                for keys in members:
                    put(keys, key, next(iter(values)))
            elif len(values) > 1:
                report.append(f"linked doors with different {key} values")

    for keys, _, _ in out:
        drop(keys, DONT_LINK)
    if linked:
        report.append(f"linked {linked} door teams")
    return out


def merge_lights(out, q1, budget, report):
    """Merges nearby point lights with the same style and color until at most `budget` remain."""
    lights = [e for e in out if get(e[0], "classname") == "light" and not e[1]]
    if len(lights) <= budget:
        return out

    others = [e for e in out if not (get(e[0], "classname") == "light" and not e[1])]
    distance = 32
    while True:
        groups = []
        for keys, _, _ in lights:
            p = origin_of(keys)
            key = (get(keys, "style", ""), get(keys, "color", ""))
            for group in groups:
                if group["key"] == key and math.dist(group["seed"], p) <= distance:
                    group["members"].append(keys)
                    break
            else:
                groups.append({"key": key, "seed": p, "members": [keys]})
        if len(groups) <= budget:
            break
        if distance > 1024:
            raise SystemExit(f"Can not merge {len(lights)} lights into {budget}: too many styles and colors")
        distance += 16

    merged = []
    for group in groups:
        members = group["members"]
        if len(members) == 1:
            merged.append((members[0], [], None))
            continue
        points = [origin_of(k) for k in members]
        center = tuple(sum(p[i] for p in points) / len(points) for i in range(3))
        if not q1.is_open(center):
            center = min(points, key=lambda p: math.dist(p, center))
        radius = max(float(get(k, "radius")) + math.dist(p, center) for k, p in zip(members, points))
        keys = [("classname", "light"), ("origin", fmt_origin(center)), ("radius", fmt(radius)),
                ("intensity", fmt(math.sqrt(len(members))))]
        style, color = group["key"]
        if color:
            keys.append(("color", color))
        if style:
            keys.append(("style", style))
        merged.append((keys, [], None))

    report.append(f"merged {len(lights)} lights into {len(merged)} (distance {distance})")
    return [others[0]] + merged + others[1:]


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    bsp, src, dst = sys.argv[1:]

    textures = Textures(read_miptex_sizes(bsp))
    entities = parse_entities(open(src).read())
    report = []

    out = []
    for keys, brushes in entities:
        out.extend(convert_entity(keys, brushes, report))

    world = out[0][0]
    if get(world, "classname") != "worldspawn":
        raise SystemExit("First entity is not worldspawn")

    q1 = Q1Bsp(bsp)
    lights = [(origin_of(k), float(get(k, "radius"))) for k, b, _ in out if get(k, "classname") == "light" and not b]
    reach = q1_light_reach(bsp, lights)
    budget = LIGHT_BUDGET
    if reach > 1:
        budget = min(budget, math.ceil(len(lights) * LONG_REACH_BUDGET))
        for keys, brushes, _ in out:
            if get(keys, "classname") == "light" and not brushes:
                put(keys, "radius", fmt(float(get(keys, "radius")) * reach))
        report.append(f"scaled light radius by {reach}, the reach measured from the Quake 1 lightmap")

    out = link_doors(out, report)
    out = unstick_point_entities(out, q1, report)
    out = merge_lights(out, q1, budget, report)

    lines = []
    for n, (keys, brushes, contents) in enumerate(out):
        lines.append(f"// entity {n}")
        lines.append("{")
        body = []
        for b, brush in enumerate(brushes):
            sides = remove_redundant_sides(brush)
            if len(sides) != len(brush):
                report.append("removed redundant brush side")
            if len(sides) < 4:
                report.append("removed degenerate brush")
                continue
            brush = sides
            body.append(f"// brush {b}")
            body.append("{")
            body.extend(convert_side(side, textures, contents) for side in brush)
            body.append("}")
        if n == 0:
            if textures.sky:
                put(keys, "sky", textures.sky)
            put(keys, "items", "quake")
            put(keys, "games", "dm")
        lines.extend(f'"{k}" "{v}"' for k, v in keys)
        lines.extend(body)
        lines.append("}")

    with open(dst, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"{dst}: {len(out)} entities")
    for q1, sub in sorted(textures.substituted.items()):
        print(f"  substituted {q1} -> quake/{sub}")
    counts = {}
    for r in report:
        counts[r] = counts.get(r, 0) + 1
    for r, c in sorted(counts.items()):
        print(f"  {c:3d}x {r}")


if __name__ == "__main__":
    main()
