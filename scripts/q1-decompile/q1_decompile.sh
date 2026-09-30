#!/bin/sh
#
# Decompile Quake 1 BSPs to Quetoo .map files.
#
# Usage: q1_decompile.sh <map.bsp> [<map.bsp> ...]
#
# Writes <map>.map next to each .bsp. bspc is cloned, patched and built once, in $BSPC_DIR.
# The output SHOULD be compiled with quemap and checked in game before it is used.
#

set -e

HERE=$(cd "$(dirname "$0")" && pwd)
BSPC_DIR=${BSPC_DIR:-${TMPDIR:-/tmp}/quetoo-bspc}
BSPC_COMMIT=10d23c5ebd042ddc5d03e17de0f560f5076649dc

if [ $# -eq 0 ]; then
	sed -n 3,9p "$0"
	exit 1
fi

STAMP="$BSPC_COMMIT $(cksum < "$HERE/bspc.patch")"

if [ ! -x "$BSPC_DIR/bspc" ] || [ "$(cat "$BSPC_DIR/.stamp" 2>/dev/null)" != "$STAMP" ]; then
	rm -rf "$BSPC_DIR"
	git clone -q https://github.com/TTimo/bspc.git "$BSPC_DIR"
	git -C "$BSPC_DIR" checkout -q $BSPC_COMMIT
	git -C "$BSPC_DIR" apply "$HERE/bspc.patch"
	make -C "$BSPC_DIR" -s \
		CC="cc -Wno-error=implicit-function-declaration -Wno-error=implicit-int -Wno-error=int-conversion" \
		> "$BSPC_DIR/build.log" 2>&1 || { cat "$BSPC_DIR/build.log"; exit 1; }
	echo "$STAMP" > "$BSPC_DIR/.stamp"
fi

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

for BSP in "$@"; do
	BSP=$(cd "$(dirname "$BSP")" && pwd)/$(basename "$BSP")
	NAME=$(basename "$BSP" .bsp)
	(cd "$WORK" && "$BSPC_DIR/bspc" -bsp2map "$BSP" -output "$WORK" > "$WORK/$NAME.log" 2>&1) || {
		cat "$WORK/$NAME.log"
		exit 1
	}
	if grep -q 'WARNING: exceeded' "$WORK/$NAME.log"; then
		grep 'WARNING: exceeded' "$WORK/$NAME.log"
		exit 1
	fi
	python3 "$HERE/q1_to_quetoo.py" "$BSP" "$WORK/$NAME.map" "$(dirname "$BSP")/$NAME.map"
done
