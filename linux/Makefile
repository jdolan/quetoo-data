# Makefile for Quetoo Data Linux packages.
# Produces: .deb (architecture: all) and .rpm (architecture: noarch)
# Requires: fpm

ARCH    = x86_64
TARGET  = target
PKGDIR  = $(TARGET)/pkg
VERSION := $(shell cd .. && git rev-list --count HEAD 2>/dev/null || echo 0)

# Install path must match the data_dir the engine derives at runtime for
# a package-managed install: binary at /usr/lib/quetoo/bin/quetoo →
# base_dir = /usr/lib/quetoo → data_dir = /usr/lib/quetoo/share/quetoo.
# Each game directory (default, ctf, ...) is installed beneath it. A package-
# managed install has no installer, so every game MUST be in the package.
DATADIR = $(PKGDIR)/usr/lib/quetoo/share/quetoo
GAME_DIRS = $(wildcard ../target/*/)
STAGED = $(TARGET)/staged

DEB = $(TARGET)/quetoo-data_$(VERSION)_all.deb
RPM = $(TARGET)/quetoo-data-$(VERSION)-1.noarch.rpm

all: deb rpm

$(STAGED): $(GAME_DIRS)
	rm -rf $(PKGDIR)
	install -d $(DATADIR)
	cp -r $(GAME_DIRS:/=) $(DATADIR)/
	touch $@

# ---------------------------------------------------------------------------
# .deb

deb: $(STAGED)
	fpm -s dir -t deb \
		-n quetoo-data -v $(VERSION) \
		--architecture all \
		--description "Game data for Quetoo" \
		--url "https://quetoo.org" \
		--license "GPL-2.0" \
		--maintainer "jdolan <jdolan@jdolan.net>" \
		-p $(DEB) \
		-C $(PKGDIR) .

# ---------------------------------------------------------------------------
# .rpm

rpm: $(STAGED)
	fpm -s dir -t rpm \
		-n quetoo-data -v $(VERSION) \
		--architecture noarch \
		--description "Game data for Quetoo" \
		--url "https://quetoo.org" \
		--license "GPL-2.0" \
		--maintainer "jdolan <jdolan@jdolan.net>" \
		-p $(RPM) \
		-C $(PKGDIR) .

clean:
	rm -rf $(TARGET)

.PHONY: all deb rpm clean
