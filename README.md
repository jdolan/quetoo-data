[![Build Status](https://github.com/jdolan/quetoo-data/actions/workflows/publish.yml/badge.svg)](https://github.com/jdolan/quetoo-data/actions/workflows/publish.yml)
[![CC-BY-SA License](https://img.shields.io/badge/license-CC--BY--SA-brightgreen.svg)](LICENSE.md)
![This software is BETA](https://img.shields.io/badge/development_stage-BETA-yellowgreen.svg)

# Quetoo BETA Game Data

![Quetoo BETA](https://raw.githubusercontent.com/jdolan/quetoo/main/quetoo-edge.jpg)

## Overview

This repository provides the game data for [_Quetoo_](https://github.com/jdolan/quetoo) — a free, open-source first-person shooter. It contains all maps, textures, models, sounds, music, and supporting assets. Game data is distributed separately from the engine and is published automatically to S3 and as GitHub Releases on every commit to `main`.

## Repository Layout

```
src/default/          # Editable source assets
  maps/               # Map sources (.map) for TrenchBroom
  textures/           # Texture sources (.png, .kra) organized by theme set
  models/             # 3D model sources (.obj/.mtl) for weapons, items, and map objects
  players/            # Player character skin sources (bunker, dragoon, guard, qforcer)
  sky/                # Skybox source images
  sprites/            # Sprite source images
  scripts/            # Python utilities for asset processing

target/default/       # Built and distributable assets (committed to the repo)
  maps/               # Compiled BSP maps alongside their .map sources
  textures/           # Processed textures
  models/             # Compiled model assets
  players/            # Player skins
  sounds/             # Sound effects
  music/              # OGG background music tracks
  sky/                # Skybox textures
  decals/             # Decal textures
  icons/              # UI icons
  mapshots/           # Map preview screenshots
  docs/               # Map credits and license documents
  manifest.mf         # Auto-generated asset manifest (do not edit by hand)
```

The `src/` tree contains the original editable assets. The `target/` tree is what the game engine loads at runtime and what gets published. Both are committed to the repository.

## Maps

There are over 20 multiplayer maps, including high-quality remakes of classic id Software levels and original designs. Map sources live in `target/default/maps/*.map` and are compiled to `*.bsp` using `quemap`.

To compile all maps that have a newer `.map` than `.bsp`:

```sh
make
```

To compile a single map:

```sh
quemap -w target/default -bsp maps/<mapname>.map
```

Map sources use the Quake3 `.map` format, fully supporting Bézier patches. The `src/default/maps/` directory holds additional work-in-progress sources that are not yet part of the distributable.

## Textures

Textures are stored as PNG files under `target/default/textures/`, organized into named theme sets (e.g. `base1/`, `quake/`, `aerowalk/`). Source Krita (`.kra`) working files are kept in `src/default/textures/`.

Common texture suffixes used by the material system:

| Suffix | Purpose |
|--------|---------|
| _(none)_ | Diffuse / albedo |
| `_norm` | Normal map |
| `_spec` | Specular map |
| `_fx`   | Material animations |
| `_glow` | Emissive / glow map |

The special set `textures/common/` contains engine-reserved surfaces (clip, sky, trigger, etc.) that are not rendered in-game.

## Models

3D models are stored as Wavefront OBJ under `src/default/models/` and compiled into the target tree. Models are organized by category:

- `models/weapons/` — player-held weapons (blaster, shotgun, railgun, etc.)
- `models/items/` — pickups (health, ammo, armor, powerups)
- `models/mapobjects/` — decorative and structural map props
- `models/players/` — third-person player body meshes

Each model directory contains the mesh (`*-tris.obj`), a `skin.png` diffuse texture, and optional `skin_glow.png` or `.mat` material overrides.

## Players

Player skins live under `target/default/players/<character>/`. Available characters are **bunker**, **dragoon**, **guard**, and **qforcer**. Each character provides multiple skin variants:

| Filename pattern | Purpose |
|-----------------|---------|
| `default.png` | Default skin |
| `ctf.png` | CTF team-colored skin |
| `*_h.png` | Helmet / head skin variant |
| `*_fx.png` | Effects overlay |

## Installing for Development

To use this data with a local Quetoo build, clone the repository and symlink the target directory:

```sh
git clone https://github.com/jdolan/quetoo-data.git
sudo ln -s $(pwd)/quetoo-data/target /usr/local/share/quetoo
```

## Contributing

Contributions of maps, textures, models, and sounds are welcome. Assets must be original work or appropriately licensed for redistribution under [CC-BY-SA](LICENSE.md). Include attribution information in `target/default/docs/` alongside any asset with third-party origins.

## Community

Join the official [Quetoo Discord](https://discord.gg/unb9U4b) to find games, get mapping help, and discuss contributions.
