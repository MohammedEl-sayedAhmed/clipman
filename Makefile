# Optional wrapper; every target delegates to scripts/dev.sh (what CI runs).
# Extra runner args: make test ARGS="-k database".

ARGS ?=

.PHONY: setup test lint check screenshot hooks-test deps help

help:
	@scripts/dev.sh help

setup:
	scripts/dev.sh setup

test:
	scripts/dev.sh test $(ARGS)

lint:
	scripts/dev.sh lint

check:
	scripts/dev.sh check $(ARGS)

screenshot:
	scripts/dev.sh screenshot $(ARGS)

hooks-test:
	scripts/dev.sh hooks-test

deps:
	scripts/dev.sh deps $(ARGS)
