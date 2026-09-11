# Makefile for Quetoo Data distributable, requires awscli.

TARGET = target

MAPS = $(wildcard $(TARGET)/default/maps/*.map)
BSPS = $(MAPS:.map=.bsp)

default: $(BSPS)

$(TARGET)/default/maps/%.bsp: $(TARGET)/default/maps/%.map
	python3 scripts/map-fu/map_fu.py $< && quemap -w $(TARGET)/default -bsp maps/$*.map

.PHONY: maps
maps: $(BSPS)

QUETOO_DATA_S3_BUCKET = s3://quetoo-data
MANIFEST = $(TARGET)/default/manifest.mf

.PHONY: manifest
manifest:
	@echo "Writing $(MANIFEST)..."
	@python3 manifest.py $(TARGET)/default > $(MANIFEST)
	@echo "Wrote $$(wc -l < $(MANIFEST) | tr -d ' ') entries to $(MANIFEST)."

s3: manifest
	aws s3 sync --delete $(TARGET) $(QUETOO_DATA_S3_BUCKET)

# Cold-install archive, published as a GitHub Releases asset. Engine installs
# with no local manifest fetch this in one shot rather than pulling thousands of
# files from S3, which keeps first-run downloads on GitHub's free egress.
# Inter-release deltas still come from S3, so the `s3` target stays.
#
# Built at the repo root, not under $(TARGET), so `s3` above does not sync a
# ~1GB archive into the bucket.
#
# Do not add -9. It silently overrides -n, deflating the JPG/PNG/OGG that are
# most of the payload for under 1% gain and a far slower build.
ZIP = quetoo-data.zip

.PHONY: zip
zip: manifest
	@echo "Writing $(ZIP)..."
	@rm -f $(ZIP)
	@cd $(TARGET) && zip -r -q -n .jpg:.png:.ogg ../$(ZIP) default -x '*/.DS_Store'
	@echo "Wrote $$(du -h $(ZIP) | cut -f1 | tr -d ' \t') to $(ZIP)."


# Compact git history to reclaim disk space. Purges history of all files that
# no longer exist in the working tree (deleted binaries, old assets, etc.).
# Current files are untouched. Text-based formats keep full history.
# After running, all other clones must be re-cloned or hard-reset to origin/main.
compact:
	@command -v git-filter-repo >/dev/null 2>&1 || { echo "Error: git-filter-repo is required (brew install git-filter-repo)"; exit 1; }
	@test -z "$$(git status --porcelain)" || { echo "Error: working tree must be clean"; exit 1; }
	@echo "=== Before ==="
	@du -sh .git
	@git log --all --pretty=format: --name-only --diff-filter=A | sort -u | sed '/^$$/d' > .git/paths-in-history.txt
	@git ls-files | sort -u > .git/paths-current.txt
	@comm -23 .git/paths-in-history.txt .git/paths-current.txt > .git/paths-to-prune.txt
	@rm -f .git/paths-in-history.txt .git/paths-current.txt
	@echo "Pruning $$(wc -l < .git/paths-to-prune.txt | tr -d ' ') deleted paths from history..."
	git filter-repo \
		--paths-from-file .git/paths-to-prune.txt \
		--invert-paths --force
	git remote add origin git@github.com:jdolan/quetoo-data.git
	git remote set-url --push origin git@github.com:jdolan/quetoo-data.git
	git remote set-url --push --add origin git@github.com:quetoo/quetoo-data.git
	@echo "=== After ==="
	@du -sh .git
	@echo
	@echo "Review the result, then run: git push --force --set-upstream origin main"
