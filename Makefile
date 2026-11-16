.PHONY: fetch build check-votes tcpd figures names paper test lint

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
	mkdir -p data/raw/eci_results
	for f in GE_2024 AE_2024_2026; do \
		curl -fL -o data/raw/eci_results/$$f.csv.gz \
			https://raw.githubusercontent.com/in-rolls/eci_results/d89b109/data/release/$$f.csv.gz; \
	done
	shasum -a 256 $(RAW)/*.parquet data/raw/tcpd/*.csv.gz data/raw/eci_results/*.csv.gz

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

paper:
	uv run python -m candidate_namesakes.econometrics
	cd ms && latexmk -xelatex -interaction=nonstopmode main.tex

test:
	uv run pytest -q

lint:
	uv run black --check .
	uv run isort --check-only .
	uv run flake8 src tests
