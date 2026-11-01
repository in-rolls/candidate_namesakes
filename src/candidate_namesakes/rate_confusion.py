"""Muse Spark's rating of how easily a voter could mix up two names.

Rates the pairs edit similarity leaves uncertain: names whose unshared words
are 0.5 to 0.8 similar, and names contained in another. Each distinct pair of
spelling keys is sent once, as one printed example of each name, to
muse-spark-1.3-contributor through museclient, which caches every request and
refuses calls past the cap. A rerun pays only for unfinished batches.

    python -m candidate_namesakes.rate_confusion stage --limit 2000 --cap 3
    python -m candidate_namesakes.rate_confusion all --cap 3
"""

import argparse
import concurrent.futures as cf
import hashlib
from pathlib import Path

import pandas as pd
from museclient import Client

BUILD = Path("data/build")
WORKDIR = BUILD / "muse"
RESULT = Path("data/release/muse_confusion.parquet")
BATCH = 40
SEED = 20261101
BAND = (0.5, 0.8)

PROMPT = """You see pairs of candidate names from the same village-election ballot in
Bihar, India. Voters see each name in Devanagari beside the candidate's symbol;
many read slowly or only partly. Names given in Latin letters were printed in
Devanagari on the ballot.

Rate how likely a voter looking for one candidate is to mistake the other name for it:
0 = clearly different names; nobody would mix them up.
1 = some resemblance, but a voter reading the name would tell them apart.
2 = look or sound alike; a voter glancing at the ballot could easily mix them up.
3 = the same name, spelled or printed differently (including misprints).

Return one result per input id, in any order."""

SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "confusion": {"type": "integer", "enum": [0, 1, 2, 3]},
                },
                "required": ["id", "confusion"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}
PROMPT_SHA = hashlib.sha256((PROMPT + str(SCHEMA)).encode()).hexdigest()[:12]


def band(pairs):
    """Distinct spelling-key pairs to rate, with one printed name for each."""
    similarity = pairs.differing_word_similarity
    uncertain = (similarity >= BAND[0]) & (similarity < BAND[1])
    rated = pairs[~pairs.is_same_spelling & (pairs.is_contained | uncertain)]
    rated = rated.drop_duplicates(["name_spelling_a", "name_spelling_b"])
    columns = [
        "name_spelling_a",
        "name_spelling_b",
        "candidate_name_a",
        "candidate_name_b",
    ]
    return rated[columns].sample(frac=1, random_state=SEED).reset_index(drop=True)


def rate_batch(client, batch):
    listing = "\n".join(
        f"{i}\t{a}\t{b}"
        for i, (a, b) in enumerate(zip(batch.candidate_name_a, batch.candidate_name_b))
    )
    answer = client.complete(
        [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": f"id\tname_a\tname_b\n{listing}"},
        ],
        schema=SCHEMA,
        name="confusion",
        max_completion_tokens=8000,
        reasoning_effort="low",
    )
    got = {r["id"]: r["confusion"] for r in answer["results"]}
    return [got.get(i) for i in range(len(batch))]


def rate_or_split(client, batch):
    """Rate a batch; if the answer is cut off or invalid, retry once as halves."""
    try:
        return rate_batch(client, batch)
    except Exception as error:  # noqa: BLE001 - every failure is retried once
        if len(batch) < 2:
            raise
        print(f"  splitting a batch of {len(batch)}: {type(error).__name__}")
        half = len(batch) // 2
        return rate_batch(client, batch.iloc[:half]) + rate_batch(
            client, batch.iloc[half:]
        )


def rate(client, pairs, workers):
    """Ratings in pair order; None where a batch failed twice."""
    batches = [pairs.iloc[i : i + BATCH] for i in range(0, len(pairs), BATCH)]
    ratings = [None] * len(batches)
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(rate_or_split, client, b): n for n, b in enumerate(batches)
        }
        for done, future in enumerate(cf.as_completed(futures), start=1):
            n = futures[future]
            try:
                ratings[n] = future.result()
            except Exception as error:  # noqa: BLE001 - recorded, run continues
                print(f"  batch {n} failed: {type(error).__name__}: {error}")
                ratings[n] = [None] * len(batches[n])
            if done % 25 == 0 or done == len(batches):
                print(f"  {done} of {len(batches)} batches; {client.spend()}")
    return [r for batch in ratings for r in batch]


def write(pairs, ratings, client, path):
    pairs = pairs.assign(
        muse_confusion=pd.array(ratings, dtype="Int8"),
        muse_confusion_method=f"{client.model} reasoning=low prompt={PROMPT_SHA}",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    pairs.to_parquet(path, index=False)
    returned = pairs.muse_confusion.notna().mean()
    print(f"wrote {path}: {len(pairs):,} pairs, {returned:.1%} rated")
    print(pairs.muse_confusion.value_counts(dropna=False).sort_index())
    return pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["stage", "all"])
    parser.add_argument("--pairs", default="data/release/name_pairs.parquet")
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--cap", type=float, required=True, help="authorized USD")
    args = parser.parse_args()
    pairs = band(pd.read_parquet(args.pairs))
    path = RESULT
    if args.stage == "stage":
        # Batches are cut in the same order as the full run, so these calls are
        # reused from the cache when it runs.
        pairs, path = pairs.head(args.limit), BUILD / "muse_confusion_stage.parquet"
    client = Client(args.cap, WORKDIR)
    write(pairs, rate(client, pairs, args.workers), client, path)
    print(client.spend())


if __name__ == "__main__":
    main()
