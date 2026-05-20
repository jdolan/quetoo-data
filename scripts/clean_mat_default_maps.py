#!/usr/bin/env python3
"""
Remove redundant normalmap/specularmap directives from .mat files.

A normalmap or specularmap directive is considered redundant when it matches
the material's default naming convention:

  ${material}_norm
  ${material}_spec

Usage:
    python3 scripts/clean_mat_default_maps.py
    python3 scripts/clean_mat_default_maps.py --dry-run
    python3 scripts/clean_mat_default_maps.py target/default/textures/quake
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SUPPORTED_KEYS = {"material", "diffusemap", "normalmap", "specularmap"}


@dataclass(frozen=True)
class Directive:
    key: str
    value: str


def parse_directive(line: str) -> Directive | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("//"):
        return None

    parts = stripped.split()
    if len(parts) < 2:
        return None

    key = parts[0].lower()
    if key not in SUPPORTED_KEYS:
        return None

    return Directive(key=key, value=parts[1])


def normalize_material_token(token: str) -> str:
    for prefix in ("models/", "textures/"):
        if token.startswith(prefix):
            return token[len(prefix) :]
    return token


def infer_file_material(path: Path) -> str:
    posix = path.as_posix()

    markers = (
        "target/default/textures/",
        "src/default/textures/",
        "target/default/models/",
        "src/default/models/",
        "target/default/",
        "src/default/",
    )

    for marker in markers:
        if marker in posix:
            rel = posix.split(marker, 1)[1]
            return rel[:-4] if rel.endswith(".mat") else rel

    return path.stem


def find_block_ranges(lines: list[str]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    depth = 0
    start = -1

    for i, line in enumerate(lines):
        opens = line.count("{")
        closes = line.count("}")

        if depth == 0 and opens > 0:
            start = i

        depth += opens
        depth -= closes

        if depth == 0 and start != -1:
            ranges.append((start, i))
            start = -1

    return ranges


def resolve_block_material(
    block_lines: Iterable[str], file_material_if_single_block: str | None
) -> str | None:
    material: str | None = None
    diffuse: str | None = None

    for line in block_lines:
        directive = parse_directive(line)
        if directive is None:
            continue

        if directive.key == "material" and material is None:
            material = directive.value
        elif directive.key == "diffusemap" and diffuse is None:
            diffuse = normalize_material_token(directive.value)

    return material or file_material_if_single_block or diffuse


def clean_file(path: Path) -> tuple[int, str]:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    block_ranges = find_block_ranges(lines)
    file_material = infer_file_material(path)
    single_block_material = file_material if len(block_ranges) == 1 else None

    to_remove: set[int] = set()

    for start, end in block_ranges:
        block_lines = lines[start : end + 1]
        base = resolve_block_material(block_lines, single_block_material)
        if not base:
            continue

        expected = {
            "normalmap": f"{base}_norm",
            "specularmap": f"{base}_spec",
        }

        for i in range(start, end + 1):
            directive = parse_directive(lines[i])
            if not directive or directive.key not in expected:
                continue
            if directive.value == expected[directive.key]:
                to_remove.add(i)

    if not to_remove:
        return 0, original

    cleaned_lines = [line for i, line in enumerate(lines) if i not in to_remove]
    cleaned = "".join(cleaned_lines)
    return len(to_remove), cleaned


def iter_mat_files(inputs: list[Path]) -> list[Path]:
    files: list[Path] = []

    for item in inputs:
        if item.is_file():
            if item.suffix == ".mat":
                files.append(item)
            continue

        if item.is_dir():
            files.extend(item.rglob("*.mat"))

    return sorted(set(files))


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove redundant map directives from .mat files.")
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path(".")],
        help="File or directory paths to scan (defaults to current directory).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report files and counts without modifying files.",
    )
    args = parser.parse_args()

    mat_files = iter_mat_files(args.paths)
    changed_files = 0
    removed_lines = 0

    for path in mat_files:
        removed, cleaned = clean_file(path)
        if removed == 0:
            continue

        changed_files += 1
        removed_lines += removed

        rel = path.as_posix()
        print(f"{rel}: removed {removed}")

        if not args.dry_run:
            path.write_text(cleaned, encoding="utf-8")

    action = "Would remove" if args.dry_run else "Removed"
    print(f"{action} {removed_lines} lines across {changed_files} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
