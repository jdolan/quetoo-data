#!/usr/bin/env python3
"""
Migrate a Quetoo .map file to use Quake-themed item entities.

Usage:
    python3 migrate_quake_map.py <map_file> [<map_file> ...]

Rewrites classnames in-place and writes a .bak backup of the original.
Entities marked REMOVE are deleted (the entire { ... } block is stripped).
"""

import re
import sys

# Many-to-one and one-to-one classname replacements.
# Order matters for the REMOVE sentinel — keep it last per group.
REPLACEMENTS = {
    # Weapons
    "weapon_shotgun":         "weapon_quake_supershotgun",
    "weapon_supershotgun":    "weapon_quake_supershotgun",
    "weapon_machinegun":      "weapon_quake_nailgun",
    "weapon_grenadelauncher": "weapon_quake_grenadelauncher",
    "weapon_rocketlauncher":  "weapon_quake_rocketlauncher",
    "weapon_hyperblaster":    "weapon_quake_supernailgun",
    "weapon_lightning":       "weapon_quake_lightning",
    "weapon_railgun":         "weapon_quake_lightning",
    "weapon_bfg":             "weapon_quake_lightning",

    # Ammo
    "ammo_shells":   "ammo_quake_shells",
    "ammo_bullets":  "ammo_quake_nails",
    "ammo_grenades": "ammo_quake_rockets",
    "ammo_rockets":  "ammo_quake_rockets",
    "ammo_bolts":    "ammo_quake_bolts",
    "ammo_cells":    "ammo_quake_bolts",
    "ammo_slugs":    "ammo_quake_bolts",
    "ammo_nukes":    "ammo_quake_bolts",

    # Armor
    "item_armor_jacket":  "item_quake_armor_jacket",
    "item_armor_combat":  "item_quake_armor_combat",
    "item_armor_body":    "item_quake_armor_body",
    "item_armor_shard":   "REMOVE",

    # Health
    "item_health":       "item_health_quake_medium",
    "item_health_large": "item_health_quake_large",
    "item_health_mega":  "item_health_quake_mega",
    "item_health_small": "REMOVE",
}

CLASSNAME_RE = re.compile(r'"classname"\s+"([^"]+)"')


def migrate(path: str) -> None:
    with open(path, "r") as f:
        text = f.read()

    # Split into entity blocks: everything between { ... } at the top level,
    # plus any leading/trailing text.
    # .map format: each entity is "// entity N\n{\n...\n}\n"
    # We split on top-level { } blocks, preserving surrounding text.
    block_re = re.compile(r'(\{[^{}]*\})', re.DOTALL)

    removed = 0
    replaced = {}

    def process_block(m):
        nonlocal removed
        block = m.group(1)
        cn_match = CLASSNAME_RE.search(block)
        if not cn_match:
            return block
        classname = cn_match.group(1)
        action = REPLACEMENTS.get(classname)
        if action is None:
            return block
        if action == "REMOVE":
            removed += 1
            return ""  # Collapse the block; comment line cleaned up below
        replaced[classname] = replaced.get(classname, 0) + 1
        return block.replace(f'"classname" "{classname}"',
                             f'"classname" "{action}"', 1)

    new_text = block_re.sub(process_block, text)

    # Clean up orphaned "// entity N" comment lines whose block was removed
    # (they now precede a blank line or another comment).
    new_text = re.sub(r'// entity \d+\n(?=\s*(?:// entity|\Z))', '', new_text)
    # Collapse runs of blank lines to a single blank line.
    new_text = re.sub(r'\n{3,}', '\n\n', new_text)

    # Write backup then overwrite.
    with open(path + ".bak", "w") as f:
        f.write(text)
    with open(path, "w") as f:
        f.write(new_text)

    print(f"{path}:")
    for src, dst in REPLACEMENTS.items():
        if src in replaced:
            print(f"  {replaced[src]:2d}x  {src} -> {dst}")
    if removed:
        print(f"  {removed:2d}x  (entities removed)")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <map_file> [...]")
        sys.exit(1)
    for path in sys.argv[1:]:
        migrate(path)
