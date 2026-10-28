# Convenience targets. Everything here is a thin wrapper around scripts/,
# so the scripts stay usable on their own.

VARIANT ?= Ender3S1-F1-v2

.PHONY: help verify docs build bootstrap flash-name clean

help:
	@echo "make verify                     check checksums, vector tables, config sanity, doc links"
	@echo "make build                      build $(VARIANT) from the prepared tree"
	@echo "make bootstrap                  clone the pinned sources into build/"
	@echo "make flash-name                 print an unused 8.3 filename for the SD card"
	@echo "make clean                      remove build/"

verify:
	./scripts/verify-artifacts.sh
	python3 scripts/check-docs.py .
	python3 tools/configurator/validate_catalog.py
	python3 -m py_compile tools/configurator/*.py
	python3 tools/configurator/sources.py --list --offline > /dev/null

docs:
	python3 scripts/check-docs.py .

bootstrap:
	./scripts/bootstrap.sh $(VARIANT)

build:
	./scripts/build.sh $(VARIANT)

flash-name:
	./scripts/flash-card.sh --next-name

clean:
	rm -rf build
