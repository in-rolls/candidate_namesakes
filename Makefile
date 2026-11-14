.PHONY: fetch build check-votes tcpd figures names test lint

COMMIT = 8326acf957a96a75769f973a096169f80c270270
BASE = https://raw.githubusercontent.com/in-rolls/local_elections/$(COMMIT)/data/master
RAW = data/raw/local_elections
STATES = bihar rajasthan

fetch:
	mkdir -p $(RAW)
	for state in $(STATES); do \
		curl -fL -o $(RAW)/candidates_$$state.parquet $(BASE)/candidates_$$state.parquet; \
	done
	mkdir -p data/raw/tcpd
	for et in GE AE; do \
		curl -fL -o data/raw/tcpd/TCPD_$${et}_All_States_2026-7-26.csv.gz \
			https://raw.githubusercontent.com/Ayush12358/electoral-reservation/8e9a5c6dadcc6bf84abcf74d83e0bb24b90981af/data/TCPD_$${et}_All_States_2026-7-26.csv.gz; \
	done
	shasum -a 256 $(RAW)/*.parquet data/raw/tcpd/*.csv.gz

build:
	uv run python -m candidate_namesakes.count_namesakes

check-votes:
	uv run python -m candidate_namesakes.check_votes

tcpd:
	uv run python -m candidate_namesakes.tcpd

figures:
	uv run python -m candidate_namesakes.figures

names:
	uv run python -m candidate_namesakes.inventory_names

test:
	uv run pytest -q

lint:
	uv run black --check .
	uv run isort --check-only .
	uv run flake8 src tests
