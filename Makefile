# Makefile for Quetoo Data distributable, requires awscli.

TARGET = target

MAPS = $(wildcard $(TARGET)/default/maps/*.map)
BSPS = $(MAPS:.map=.bsp)

default: $(BSPS)

$(TARGET)/default/maps/%.bsp: $(TARGET)/default/maps/%.map
	quemap -bsp -w ./$(TARGET)/default maps/$*.map

QUETOO_DATA_S3_BUCKET = s3://quetoo-data

s3:
	git rev-parse --short HEAD > $(TARGET)/revision
	aws s3 sync --delete $(TARGET) $(QUETOO_DATA_S3_BUCKET)

