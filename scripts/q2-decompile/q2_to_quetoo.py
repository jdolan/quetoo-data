#!/usr/bin/env python3
"""
Convert a bspc-decompiled Quake 2 .map to Quetoo textures, surface flags and entities.

Usage:
    q2_to_quetoo.py <decompiled.map> <output.map>

The original WAL textures are read from the paks and loose textures under $QUAKE2_DIR (default
~/.quake2), so that texture scale and shift can be rescaled to the higher resolution textures in
textures/quake2 and textures/ctf. Textures that Quetoo does not have are mapped to the name they
would have, unscaled, and listed in the report.
"""

import os
import re
import struct
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../q1-decompile"))

import q1_to_quetoo as q1  # noqa: E402
from q1_to_quetoo import LIGHT_STYLES, drop, fmt, get, parse_entities, put, remove_redundant_sides  # noqa: E402

TEXTURES = os.path.join(q1.DATA, "textures")
QUAKE2_DIR = os.path.expanduser(os.environ.get("QUAKE2_DIR", "~/.quake2"))

# Quake 2 shares most of its contents with Quetoo, but not the area portal and the monster contents.
Q2_CONTENTS_AREAPORTAL = 0x8000
Q2_CONTENTS_MONSTER = 0x2000000
Q2_CONTENTS_CORPSE = 0x4000000
DROPPED_CONTENTS = Q2_CONTENTS_AREAPORTAL | Q2_CONTENTS_MONSTER | Q2_CONTENTS_CORPSE

# Quake 2 surface flags that Quetoo shares: slick, sky, warp (liquid), trans33, trans66, nodraw, hint
# and skip. Light is a material in Quetoo, and flowing is 0x40, which in Quetoo is alpha blending.
Q2_SURFACE_LIGHT = 0x1
Q2_SURFACE_SKY = 0x4
Q2_SURFACE_FLOWING = 0x40
SHARED_SURFACE = 0x2 | 0x4 | 0x8 | 0x10 | 0x20 | 0x80 | 0x100 | 0x200

Q2_NOT_SKILL = 0x100 | 0x200 | 0x400
Q2_NOT_DEATHMATCH = 0x800
Q2_NOT_COOP = 0x1000

COMMON = {
    "trigger": "common/trigger",
    "clip": "common/clip",
    "hint": "common/hint",
    "skip": "common/skip",
    "origin": "common/origin",
}

# Quake 2 skies are cube maps, and Quetoo skies are not, so these are the nearest.
SKIES = {
    "space1": "nebula1",
}
DEFAULT_SKY = "sky1"

RENAME = {
    "weapon_shotgun": "weapon_quake2_shotgun",
    "weapon_supershotgun": "weapon_quake2_supershotgun",
    "weapon_machinegun": "weapon_quake2_machinegun",
    "weapon_chaingun": "weapon_quake2_chaingun",
    "weapon_grenadelauncher": "weapon_quake2_grenadelauncher",
    "weapon_rocketlauncher": "weapon_quake2_rocketlauncher",
    "weapon_hyperblaster": "weapon_quake2_hyperblaster",
    "weapon_railgun": "weapon_quake2_railgun",
    "weapon_bfg": "weapon_quake2_bfg",
    "ammo_shells": "ammo_quake2_shells",
    "ammo_bullets": "ammo_quake2_bullets",
    "ammo_grenades": "ammo_quake2_grenades",
    "ammo_rockets": "ammo_quake2_rockets",
    "ammo_cells": "ammo_quake2_cells",
    "ammo_slugs": "ammo_quake2_slugs",
    "item_pack": "item_quake2_backpack",
    "item_armor_jacket": "item_quake2_armor_jacket",
    "item_armor_combat": "item_quake2_armor_combat",
    "item_armor_body": "item_quake2_armor_body",
    "item_armor_shard": "item_quake2_armor_shard",
    "item_health_small": "item_quake2_health_small",
    "item_health": "item_quake2_health_medium",
    "item_health_large": "item_quake2_health_large",
    "item_health_mega": "item_quake2_health_mega",
    "item_adrenaline": "item_quake2_adrenaline",
    "item_invulnerability": "item_quake2_invulnerability",
    "trigger_teleport": "trigger_teleporter",
}

# Quake 2 entities that Quetoo has no equivalent of.
REMOVE = {
    "func_areaportal",
    "func_clock",
    "func_explosive",
    "func_killbox",
    "info_player_coop",
    "item_ancient_head",
    "item_bandolier",
    "item_breather",
    "item_enviro",
    "item_power_screen",
    "item_power_shield",
    "item_silencer",
    "light_mine1",
    "light_mine2",
    "misc_ctf_banner",
    "misc_ctf_small_banner",
    "misc_actor",
    "misc_banner",
    "misc_bigviper",
    "misc_blackhole",
    "misc_deadsoldier",
    "misc_easterchick",
    "misc_easterchick2",
    "misc_eastertank",
    "misc_explobox",
    "misc_gib_arm",
    "misc_gib_head",
    "misc_gib_leg",
    "misc_satellite_dish",
    "misc_strogg_ship",
    "misc_teleporter_dest_unused",
    "misc_viper",
    "misc_viper_bomb",
    "point_combat",
    "target_actor",
    "target_blaster",
    "target_changelevel",
    "target_crosslevel_target",
    "target_crosslevel_trigger",
    "target_earthquake",
    "target_explosion",
    "target_goal",
    "target_help",
    "target_laser",
    "target_lightramp",
    "target_secret",
    "target_spawner",
    "target_temp_entity",
    "trigger_counter",
    "trigger_elevator",
    "trigger_gravity",
    "trigger_key",
    "trigger_monsterjump",
    "viewthing",
}
REMOVE_PREFIXES = ("monster_", "key_")

# Quake 2 ambient sounds that have a Quetoo counterpart.
AMBIENT_SOUNDS = {
    "world/comp_hum1": "ambient/comp",
    "world/comp_hum2": "ambient/comp",
    "world/comp_hum3": "ambient/comp",
    "world/fan1": "ambient/fan_1",
    "world/klaxon1": "ambient/siren",
    "world/l_hum2": "ambient/hum2",
    "world/water1": "ambient/water_1",
    "world/mov_watr": "ambient/water_2",
    "world/wind2": "ambient/wind_2",
    "world/drip_amb": "ambient/drip_1",
}

# Quake 2 uses its light value as the distance the light reaches.
Q2_LIGHT_DEFAULT = 300

TEXTURE_EXTENSIONS = ("jpg", "png", "tga")


def read_pak_wals(path):
    """Returns a dict of texture name to (pak path, offset) for the WALs in a pak."""
    wals = {}
    with open(path, "rb") as f:
        magic, offset, length = struct.unpack("<4sii", f.read(12))
        if magic != b"PACK":
            return wals
        f.seek(offset)
        for _ in range(length // 64):
            name, pos, _size = struct.unpack("<56sii", f.read(64))
            name = name.split(b"\0")[0].decode("latin-1").lower()
            if name.startswith("textures/") and name.endswith(".wal"):
                wals.setdefault(name[len("textures/"):-len(".wal")], (path, pos))
    return wals


def find_wals(root):
    """Returns a dict of texture name to (path, offset) for the paks and loose WALs under root."""
    wals = {}
    if not os.path.isdir(root):
        return wals
    for game in sorted(os.listdir(root)):
        game_dir = os.path.join(root, game)
        if not os.path.isdir(game_dir):
            continue
        for name in sorted(os.listdir(game_dir)):
            if name.lower().endswith(".pak"):
                for k, v in read_pak_wals(os.path.join(game_dir, name)).items():
                    wals.setdefault(k, v)
        textures = os.path.join(game_dir, "textures")
        for dirpath, _, files in os.walk(textures):
            for name in files:
                if name.lower().endswith(".wal"):
                    rel = os.path.relpath(os.path.join(dirpath, name), textures)
                    wals.setdefault(rel[:-4].replace(os.sep, "/").lower(), (os.path.join(dirpath, name), 0))
    return wals


def wal_size(wals, name):
    """Returns (width, height) of a Quake 2 texture, or None if it is not in the paks."""
    entry = wals.get(name)
    if not entry:
        return None
    path, offset = entry
    with open(path, "rb") as f:
        f.seek(offset + 32)
        return struct.unpack("<II", f.read(8))


def texture_image(rel):
    """Returns the path of the image for a texture such as quake2/baselt_c, or None."""
    for ext in TEXTURE_EXTENSIONS:
        path = os.path.join(TEXTURES, f"{rel}.{ext}")
        if os.path.exists(path):
            return path
    return None


def material_image(rel):
    """Returns the image of a material that has none of its own, by its diffusemap, or None."""
    mat = os.path.join(TEXTURES, f"{rel}.mat")
    if os.path.exists(mat):
        m = re.search(r"diffusemap\s+(\S+)", open(mat).read())
        if m:
            return texture_image(m.group(1))
    return None


class Textures:
    def __init__(self, wals):
        self.wals = wals
        self.cache = {}
        self.missing = {}
        self.sky = None

    def resolve(self, q2name):
        """Returns (quetoo name, x factor, y factor). A texture Quetoo lacks keeps its scale."""
        if q2name in self.cache:
            return self.cache[q2name]

        lower = q2name.lower()
        category, _, base = lower.rpartition("/")
        name = base
        m = re.match(r"^\+([0-9a-j])(.*)$", name)
        if m:
            name = f"{m.group(2)}+{m.group(1)}"

        if base in COMMON:
            result = (COMMON[base], 1.0, 1.0)
        else:
            dirs = ("ctf", "quake2") if category == "ctf" else ("quake2", "ctf")
            candidates = [name, m.group(2)] if m else [name]
            found = None
            for d in dirs:
                for candidate in candidates:
                    path = texture_image(f"{d}/{candidate}") or material_image(f"{d}/{candidate}")
                    if path:
                        found = (f"{d}/{candidate}", path)
                        break
                if found:
                    break
            size = wal_size(self.wals, lower)
            if found and size:
                qw, qh = q1.image_size(found[1])
                result = (found[0], qw / size[0], qh / size[1])
            else:
                if found:
                    self.missing[lower] = "no WAL to read the size from"
                else:
                    self.missing[lower] = "no Quetoo texture"
                result = (found[0] if found else f"{dirs[0]}/{name}", 1.0, 1.0)

        self.cache[q2name] = result
        return result


SIDE_RE = re.compile(
    r"^(\s*\(\s*\S+\s+\S+\s+\S+\s*\)\s*\(\s*\S+\s+\S+\s+\S+\s*\)\s*\(\s*\S+\s+\S+\s+\S+\s*\))"
    r"\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)(?:\s+(\S+)\s+(\S+)\s+(\S+))?\s*$")


def convert_side(line, textures, stats):
    m = SIDE_RE.match(line)
    if not m:
        raise SystemExit(f"Unparsed brush side: {line}")
    planes, tex, sx, sy, rot, scx, scy, contents, flags, value = m.groups()
    contents, flags = int(contents or 0), int(flags or 0)

    if flags & Q2_SURFACE_SKY:
        textures.sky = True
        name, fx, fy = "common/sky", 1.0, 1.0
    else:
        name, fx, fy = textures.resolve(tex)

    if flags & Q2_SURFACE_LIGHT:
        stats["light"] = stats.get("light", 0) + 1

    contents &= ~DROPPED_CONTENTS
    surface = flags & SHARED_SURFACE
    sx, sy, scx, scy = float(sx) * fx, float(sy) * fy, float(scx) / fx, float(scy) / fy
    return f"{planes} {name} {fmt(sx)} {fmt(sy)} {rot} {fmt(scx)} {fmt(scy)} {contents} {surface} 0"


def convert_light(keys, report):
    out = [("classname", "light"), ("origin", get(keys, "origin")),
           ("radius", get(keys, "light", str(Q2_LIGHT_DEFAULT)))]
    color = get(keys, "_color")
    if color:
        rgb = [float(x) for x in color.split()]
        if max(rgb) > 1:
            rgb = [x / 255 for x in rgb]
        out.append(("color", " ".join(fmt(x) for x in rgb)))
    style = int(get(keys, "style", "0") or 0)
    if 0 < style < len(LIGHT_STYLES):
        out.append(("style", LIGHT_STYLES[style]))
    elif style:
        report.append("light style above 11 is not supported, made constant")
    if get(keys, "target"):
        report.append("spotlight converted to a point light")
    return [(out, [])]


def convert_speaker(keys, report):
    noise = get(keys, "noise", "")
    sound = re.sub(r"\.wav$", "", noise.lower())
    spawnflags = int(get(keys, "spawnflags", "0"))
    mapped = AMBIENT_SOUNDS.get(sound)
    if mapped is None and sound:
        report.append(f"no Quetoo sound for {sound}")
    sound = mapped or sound

    if spawnflags & 1 and not get(keys, "targetname"):
        return [([("classname", "misc_sound"), ("origin", get(keys, "origin")), ("sound", sound)], [])]

    out = [("classname", "target_speaker"), ("origin", get(keys, "origin")), ("sound", sound)]
    if get(keys, "targetname"):
        out.append(("targetname", get(keys, "targetname")))
    if spawnflags & 3:
        out.append(("spawnflags", str(spawnflags & 3)))
    return [(out, [])]


def convert_entity(keys, brushes, report):
    """Returns a list of (keys, brushes) for the converted entity, empty to remove it."""
    classname = get(keys, "classname")
    spawnflags = int(get(keys, "spawnflags", "0"))

    if spawnflags & Q2_NOT_DEATHMATCH:
        report.append(f"removed {classname} (not in deathmatch)")
        return []
    spawnflags &= ~(Q2_NOT_SKILL | Q2_NOT_DEATHMATCH | Q2_NOT_COOP)

    if classname in REMOVE or classname.startswith(REMOVE_PREFIXES):
        report.append(f"removed {classname}")
        return []

    if classname == "light":
        return convert_light(keys, report)
    if classname == "target_speaker":
        return convert_speaker(keys, report)

    if classname == "worldspawn":
        drop(keys, "sounds", "nextmap", "skyaxis", "skyrotate")
        return [(keys, brushes)]

    classname = RENAME.get(classname, classname)
    put(keys, "classname", classname)
    # The editor keys, e.g. _minlight, are not used by Quetoo, and neither are door and button sounds.
    keys[:] = [(k, v) for k, v in keys if not k.startswith("_")]
    drop(keys, "sounds", "spawnflags")
    if spawnflags:
        put(keys, "spawnflags", str(spawnflags))
    return [(keys, brushes)]


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    src, dst = sys.argv[1:]

    textures = Textures(find_wals(QUAKE2_DIR))
    entities = parse_entities(open(src).read())
    report = []
    stats = {}

    out = []
    for keys, brushes in entities:
        out.extend(convert_entity(keys, brushes, report))

    world = out[0][0]
    if get(world, "classname") != "worldspawn":
        raise SystemExit("First entity is not worldspawn")

    ctf = any(get(k, "classname") == "item_flag_team1" for k, _ in out)

    lines = []
    for n, (keys, brushes) in enumerate(out):
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
            body.append(f"// brush {b}")
            body.append("{")
            body.extend(convert_side(side, textures, stats) for side in sides)
            body.append("}")
        if n == 0:
            q2_sky = get(keys, "sky", "unit1_")
            sky = SKIES.get(q2_sky, DEFAULT_SKY)
            put(keys, "sky", sky)
            report.append(f"sky {q2_sky} is approximated by {sky}")
            put(keys, "items", "quake2")
            put(keys, "games", "ctf" if ctf else "dm")
        lines.extend(f'"{k}" "{v}"' for k, v in keys)
        lines.extend(body)
        lines.append("}")

    with open(dst, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"{dst}: {len(out)} entities")
    for name, why in sorted(textures.missing.items()):
        print(f"  missing {name} ({why})")
    if stats.get("light"):
        print(f"  {stats['light']} light emitting surfaces lost their light, which Quetoo takes from materials")
    counts = {}
    for r in report:
        counts[r] = counts.get(r, 0) + 1
    for r, c in sorted(counts.items()):
        print(f"  {c:3d}x {r}")


if __name__ == "__main__":
    main()
