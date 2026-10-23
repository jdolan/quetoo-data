# quetoo-data

The game content for [Quetoo](https://github.com/jdolan/quetoo): maps, textures, models, sounds,
materials, HUD and UI icons. Engine chrome that renders before a game module loads (backgrounds,
fonts, conback, loading screen, menu sounds) lives in the `quetoo` repository instead.

This file is the shared instruction set for coding agents. It records only what the files do
**not** reveal: rules that fail silently, and constraints that live outside this repository. For
anything else, read the files and the `README.md`. The engine's own rules are in
`../quetoo/AGENTS.md`.

## A push to `main` is a release

`.github/workflows/publish.yml` runs on every push to `main`. It regenerates and commits
`target/default/manifest.mf`, then runs `aws s3 sync --delete target/ s3://quetoo-data`. Every
player's installer reads that bucket at its next start-up. A pushed mistake reaches players
within minutes, and `--delete` removes from the bucket any file that the push removed.

- You MUST NOT push to `main` unless Jay asks you to.
- You MUST NOT edit `manifest.mf` by hand. CI owns it.
- A tag `v*` runs `release.yml`, which also builds the `.deb`, the `.rpm` and the cold-install
  `quetoo-data.zip`.

## Maps ship as pk3s

`make` compiles each `target/<game>/maps/<name>.map` to `build/<game>/maps/<name>.bsp` (not
committed), and packs that BSP and its `.mf` into `target/<game>/map-<name>.pk3`. A pk3 is output
only. The `.map` source, the docs and the mapshots stay loose, versioned files in `target/`.

These rules fail silently:

- **The `quemap` on `PATH` is what runs.** The `Makefile` calls `quemap`, normally the installed
  `/usr/local/bin/quemap`. After a quemap change in `../quetoo`, install it before `make`, or the
  old binary packs every shared asset into each pk3.
- **A loose BSP or manifest shadows the build.** A `maps/<name>.bsp` or `maps/<name>.mf` in
  `target/<game>/maps/`, or anywhere on the search path (including a user-dir symlink into this
  repository), wins over `build/`. quemap's light stage and its `-zip` stage then read the stale
  copy. You MUST NOT commit `target/<game>/maps/*.bsp` or `target/<game>/maps/*.mf`.
- **quemap's data dir MUST resolve to this `target/`**, normally because `/usr/local/share/quetoo`
  is a symbolic link to it. quemap leaves out of a pk3 only the assets that resolve into its data
  dir. If the link is missing, each pk3 silently holds every texture, sound and model its map uses.
- **A rebake makes every player download every map again.** The manifest hashes each pk3 as
  stored, and quemap writes byte-identical output for identical input. Rebake only for a real
  change to a map or to the BSP format. Jay wants at most one rebake per release.

After a rebake, check one pk3: `unzip -l target/default/map-<name>.pk3` MUST list exactly
`maps/<name>.bsp` and `maps/<name>.mf`.

## Constraints that live outside this repository

- **BSP format changes pair releases.** If a quetoo release changes the BSP format, this
  repository MUST be rebaked and tagged with that release. Packaged dedicated servers update
  themselves, cannot load maps of the other format, and fail with no error in the journal.
- **Map doc names are read by quemap.** `docs/maps-<name>.txt` and `docs/maps-<name>.license.txt`
  are spelled in `../quetoo/src/quemap/manifest.c`. Renaming them here drops them from every map
  manifest, with no error.
- **Material keywords are a content format.** The keywords in `.mat` files are parsed by
  `Material_Load` in `../quetoo`, and user maps use them too. They MUST NOT be renamed here alone.
- **An entity is defined in four places across three repositories:** the QUAKED comment beside its
  spawn function in `../quetoo/src/game/`, `target/default/scripts/entities.def`,
  `target/default/scripts/trenchbroom/Quetoo/Quetoo.fgd`, and TrenchBroom's own copy of that
  `.fgd`. Changes drift in both directions, including from TrenchBroom back to this repository.
  Compare all four before you conclude that one is wrong.
- **The installer syncs a fixed list of games.** At start-up it syncs each game in
  `syncedGames` (`../quetoo/src/common/installer.c`), and no other. `make manifest` writes a
  `manifest.mf` for every directory in `target/`. A new game directory reaches players only after
  it is added to `syncedGames` in an engine release.
- **Linux packages have no installer.** A package-managed install turns the installer off, so
  `linux/Makefile` MUST package every game directory.

## Conventions

The commit rules in `../quetoo/AGENTS.md` and `../quetoo/CONTRIBUTING.md` apply here. In
particular, a commit MUST NOT carry a `Co-Authored-By:` trailer that names Claude, Copilot or any
other agent. A trailer cannot be removed later without a change to the SHA of every later commit.

Binaries are tracked in git without LFS, so each committed BSP, pk3 or texture stays in the history
for good. Commit generated content only when it is final.
