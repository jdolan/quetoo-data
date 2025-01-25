# Makefile for Quetoo Data distributable, requires awscli.

V ?= 0

QUEMAP := quemap
QUEMAP_FLAGS := -bsp -light

BUILD := $(CURDIR)/build
INST_DIR := $(HOME)/.quetoo/default

ALL_BSP_TARGETS = $(patsubst %.map,%.bsp,$(wildcard maps/*.map))

BSP_TARGETS = \
	maps/edge.bsp \
	maps/hallways.bsp \
	maps/pits.bsp \
	maps/tokays.bsp \
	maps/fragpipe.bsp \
	maps/lavatomb.bsp \
	maps/slimyplace.bsp \
	maps/warehouse.bsp \

ifeq ($(V),0)
Q = @
else
Q =
endif

.PHONY: clean

bsp: $(BSP_TARGETS)
all: $(ALL_BSP_TARGETS)

$(BUILD):
	@echo "MKDIR $@"
	$(Q)mkdir -p $@

%.bsp: %.map
	@echo "QUEMAP $<"
ifeq ($(V),1)
	$(QUEMAP) -w $(CURDIR) -p . $(QUEMAP_FLAGS) $<
else
	@$(QUEMAP) -w $(CURDIR) -p . $(QUEMAP_FLAGS) $< >/dev/null 2>&1
endif

clean:
	@echo "RM maps/*.bsp"
	$(Q)rm -rf maps/*.bsp
