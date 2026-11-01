.PHONY: fetch build check-votes test lint

COMMIT = 112e86b749257aba5b10106f5727e36019e924f4
BASE = https://raw.githubusercontent.com/in-rolls/local_elections/$(COMMIT)/data/master
RAW = data/raw/local_elections
STATES = bihar rajasthan

fetch:
	mkdir -p $(RAW)
	for state in $(STATES); do \
		curl -fL -o $(RAW)/candidates_$$state.parquet $(BASE)/candidates_$$state.parquet; \
	done
	shasum -a 256 $(RAW)/*.parquet

build:
	uv run python -m candidate_namesakes.count_namesakes

check-votes:
	uv run python -m candidate_namesakes.check_votes

test:
	uv run pytest -q

lint:
	uv run black --check .
	uv run isort --check-only .
	uv run flake8 src tests
