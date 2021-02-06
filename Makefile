# Makefile for Quetoo Data distributable, requires awscli.

TARGET = target
QUETOO_DATA_S3_BUCKET = s3://quetoo-data

all:
	git rev-parse --short HEAD > $(TARGET)/revision
	aws s3 sync --delete $(TARGET) $(QUETOO_S3_BUCKET)

