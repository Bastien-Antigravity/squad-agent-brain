VERSION ?= $(shell cat VERSION.txt 2>/dev/null || echo "0.0.1")

.PHONY: all test run clean version

all: test

version:
	@echo $(VERSION)

test:
	@echo "Running tests for 08-Squad-Agent (version $(VERSION))..."
	pytest tests/

run:
	python3 main.py

clean:
	@echo "Cleaning cache and bytecode..."
	@rm -rf __pycache__ src/**/__pycache__ tests/__pycache__ .pytest_cache
