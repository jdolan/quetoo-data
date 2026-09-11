#!/usr/bin/env python3
"""
Generates manifest.mf for a quetoo-data game directory.
Enumerates all files under the given game directory, sorted by path, and
writes a manifest in the format: <md5> <size> <path>, where paths are
relative to the game directory (i.e., true Quake paths).
"""

import hashlib
import os
import sys

def main():
    game_dir = sys.argv[1] if len(sys.argv) > 1 else "target/default"

    entries = []
    for dirpath, dirnames, filenames in os.walk(game_dir):
        dirnames.sort()
        for filename in sorted(filenames):
            if filename in ("manifest.mf", ".DS_Store"):
                continue
            filepath = os.path.join(dirpath, filename)
            relpath  = os.path.relpath(filepath, game_dir)
            data     = open(filepath, "rb").read()
            md5      = hashlib.md5(data).hexdigest()
            entries.append((relpath, md5, len(data)))

    entries.sort()
    for path, md5, size in entries:
        print(f"{md5} {size} {path}")


if __name__ == "__main__":
    main()
