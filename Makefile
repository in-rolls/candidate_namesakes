.PHONY: fetch build check-votes test lint

SOURCE_URL = https://raw.githubusercontent.com/in-rolls/local_elections/112e86b749257aba5b10106f5727e36019e924f4/data/master/candidates_bihar.parquet
SOURCE = data/raw/local_elections/candidates_bihar.parquet

fetch:
	mkdir -p $(dir $(SOURCE))
	curl -fL -o $(SOURCE) $(SOURCE_URL)
	shasum -a 256 $(SOURCE)

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
