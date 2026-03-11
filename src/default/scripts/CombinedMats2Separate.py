#!/usr/bin/env python3
"""
gen_materials.py
Parses a Quetoo material definition file and generates individual .mat files,
routing outputs based on whether the texture lives under common/ or not.

Usage:
    python gen_materials.py <input.mat> <common_root> <src_root>

Arguments:
    input.mat       Path to the source material definition file
    common_root     Output root for textures under common/
                    e.g. D:/quetoo_dev/github/quetoo-data/target/default/textures
    src_root        Output root for all other textures
                    e.g. D:/quetoo_dev/github/quetoo/src/default/textures

Example:
    python gen_materials.py quake.mat \\
        D:/quetoo_dev/github/quetoo-data/target/default/textures \\
        D:/quetoo_dev/github/quetoo/src/default/textures
"""

import sys
import os
import re


def parse_blocks(text):
    """Parse top-level { } blocks from the material def, preserving nested blocks."""
    blocks = []
    depth = 0
    current = []

    for line in text.splitlines():
        stripped = line.strip()

        if stripped == '{':
            depth += 1
            if depth == 1:
                current = ['{']
                continue
        
        if stripped == '}':
            depth -= 1
            if depth == 0:
                current.append('}')
                blocks.append('\n'.join(current))
                current = []
                continue

        if depth >= 1:
            current.append(line)

    return blocks


def get_diffuse(block):
    """Extract the diffusemap path from a block. Supports both 'diffusemap' and legacy 'material' keywords."""
    for line in block.splitlines():
        m = re.match(r'\s*(?:diffusemap|material)\s+(\S+)', line)
        if m:
            return m.group(1)
    return None


# Numeric keys where a value of 1 (in any float form) is the default and should be stripped
DEFAULT_ONE_KEYS = {'roughness', 'hardness', 'specularity', 'parallax', 'shadow'}


def is_default_value(value):
    """Return True if the value is numerically equal to 1.0 (e.g. 1, 1.0, 1.00)."""
    try:
        return float(value) == 1.0
    except ValueError:
        return False


def strip_defaults(block):
    """Remove numeric key lines whose value equals 1.0 from top-level block only (not nested stages)."""
    lines = block.splitlines()
    result = []
    depth = 0

    for line in lines:
        stripped = line.strip()

        if stripped == '{':
            depth += 1
            result.append(line)
            continue
        if stripped == '}':
            depth -= 1
            result.append(line)
            continue

        # Only strip at top level (depth == 1), leave nested stage blocks untouched
        if depth == 1:
            m = re.match(r'(\s*)(\w+)\s+(\S+)$', line)
            if m and m.group(2) in DEFAULT_ONE_KEYS and is_default_value(m.group(3)):
                continue  # drop this line

        result.append(line)

    return '\n'.join(result)


def resolve_output_path(diffuse, common_root, src_root):
    """
    Route the output path based on whether the texture is under common/ or not.
    common/* -> common_root/<diffuse>.mat
    anything else -> src_root/<diffuse>.mat
    """
    if diffuse.startswith('common/') or diffuse.startswith('common\\'):
        root = common_root
    else:
        root = src_root

    rel_path = diffuse.replace('/', os.sep).replace('\\', os.sep)
    return os.path.join(root, rel_path + '.mat')


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)

    input_file  = sys.argv[1]
    common_root = sys.argv[2]
    src_root    = sys.argv[3]

    if not os.path.isfile(input_file):
        print(f"ERROR: Input file not found: {input_file}")
        sys.exit(1)

    # Sanity check: warn if common_root ends with 'common' or 'common/' — this causes path doubling
    common_tail = os.path.normpath(common_root).split(os.sep)[-1].lower()
    if common_tail == 'common':
        print(f"WARNING: common_root appears to end with 'common': {common_root}")
        print(f"         This will produce doubled paths like common/common/...")
        print(f"         Did you mean: {os.path.dirname(os.path.normpath(common_root))}")
        print()
        answer = input("Continue anyway? [y/N]: ").strip().lower()
        if answer != 'y':
            print("Aborted.")
            sys.exit(0)
        print()

    with open(input_file, 'r') as f:
        text = f.read()

    blocks = parse_blocks(text)

    created  = 0
    skipped  = 0
    errors   = 0

    print(f"Input:       {input_file}")
    print(f"common/ →   {common_root}")
    print(f"other/  →   {src_root}")
    print()

    for block in blocks:
        diffuse = get_diffuse(block)
        if not diffuse:
            print(f"  WARNING: Block with no diffusemap, skipping.")
            skipped += 1
            continue

        out_path = resolve_output_path(diffuse, common_root, src_root)
        out_dir  = os.path.dirname(out_path)

        try:
            os.makedirs(out_dir, exist_ok=True)
            with open(out_path, 'w', newline='\n') as f:
                f.write(strip_defaults(block) + '\n')
            print(f"  [OK]  {out_path}")
            created += 1
        except OSError as e:
            print(f"  [ERR] {out_path} — {e}")
            errors += 1

    print()
    print(f"Done. {created} written, {skipped} skipped, {errors} errors.")


if __name__ == '__main__':
    main()
