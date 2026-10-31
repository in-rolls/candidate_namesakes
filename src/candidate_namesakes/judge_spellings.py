"""Ask Muse Spark whether two close names in one contest are the same name.

The spelling key merges variants a rule can describe. What is left in
data/build/review_pairs.parquet are names one letter apart, mostly different
names (Kabita, Sabita) with some spellings of one name (Imtiyaz, Imtyaz). Each
unique pair is sent once, as printed, to muse-spark-1.3-contributor through
museclient, which caches each request and refuses calls past the cap.

    python -m candidate_namesakes.judge_spellings pilot --cap 0.1
    python -m candidate_namesakes.judge_spellings all --cap 1
"""

import argparse
import hashlib
from pathlib import Path

import pandas as pd
from museclient import Client

from candidate_namesakes.count_namesakes import load

BUILD = Path("data/build")
WORKDIR = BUILD / "muse"
PAIRS = BUILD / "review_pairs.parquet"
RESULT = Path("data/release/spelling_judgments.parquet")
SOURCE = "data/raw/local_elections/candidates_bihar.parquet"
SOURCE_SHA256 = "98df872c1e9e4e53cab53018fa420bf951ed0a45f74d27960e686fff10e6698b"
BATCH = 40
SEED = 20261031

PROMPT = """You read pairs of candidate names from village elections in India,
printed in Devanagari or in Latin letters. Both names in a pair stood for the
same seat.

For each pair, decide whether the two are the same name written two ways (a
spelling, vowel-length, transliteration or typing variant of one name), or two
different names that happen to look alike. Imtiyaz and Imtyaz are the same name;
Kabita and Sabita are different names; Nirmala and Nirmaala are the same name;
Rita and Rina are different names. Judge the names only, not whether the people
are the same.

Set same_name to true or false. Set cannot_decide to true only when the pair
cannot be judged (a placeholder or text that is not a name).

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
                    "same_name": {"type": "boolean"},
                    "cannot_decide": {"type": "boolean"},
                },
                "required": ["id", "same_name", "cannot_decide"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}
PROMPT_SHA = hashlib.sha256((PROMPT + str(SCHEMA)).encode()).hexdigest()[:12]

# Pilot pairs with a known answer, not drawn from the prompt's own examples.
KNOWN = [
    ("रोकसाना खातून", "रोखसाना खातून", True),
    ("इमतयाज आलम", "इमतियाज आलम", True),
    ("SAILENDRA KUMAR", "SHAILENDRA KUMAAR", True),
    ("निर्मला देवी", "निरमाला देवी", True),
    ("उर्मिला देवी", "परमिला देवी", False),
    ("SALIMA KHATUN", "SAMIMA KHATUN", False),
    ("KALESHWAR RAM", "KAMESHWAR RAM", False),
    ("निरंजन दास", "बिरंजन दास", False),
]


def examples():
    """Each unique close pair, with one printed spelling of each name."""
    pairs = pd.read_parquet(PAIRS).drop_duplicates(
        ["name_spelling_a", "name_spelling_b"]
    )
    candidates = load(SOURCE, SOURCE_SHA256)
    printed = (
        candidates.dropna(subset=["name_spelling"])
        .drop_duplicates("name_spelling")
        .set_index("name_spelling")
        .candidate_name
    )
    pairs["name_a"] = pairs.name_spelling_a.map(printed)
    pairs["name_b"] = pairs.name_spelling_b.map(printed)
    return pairs[["name_spelling_a", "name_spelling_b", "name_a", "name_b"]]


def judge(client, pairs):
    """{(name_a, name_b): (same_name, cannot_decide)}, BATCH pairs at a time."""
    out = {}
    for start in range(0, len(pairs), BATCH):
        batch = pairs[start : start + BATCH]
        listing = "\n".join(f"{i}\t{a}\t{b}" for i, (a, b) in enumerate(batch))
        answer = client.complete(
            [
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": f"id\tname_a\tname_b\n{listing}"},
            ],
            schema=SCHEMA,
            name="same_name",
            max_completion_tokens=8000,
            reasoning_effort="low",
        )
        got = {r["id"]: r for r in answer["results"] if 0 <= r["id"] < len(batch)}
        for i, pair in enumerate(batch):
            if i in got:
                out[pair] = (bool(got[i]["same_name"]), bool(got[i]["cannot_decide"]))
        done = min(start + BATCH, len(pairs))
        print(f"  judged {done} of {len(pairs)}; {client.spend()}", flush=True)
    return out


def pilot(client):
    known = pd.DataFrame(KNOWN, columns=["name_a", "name_b", "expected"])
    sample = examples().sample(BATCH - len(known), random_state=SEED)
    pairs = list(zip(known.name_a, known.name_b)) + list(
        zip(sample.name_a, sample.name_b)
    )
    got = judge(client, pairs)
    print(f"\nreturned {len(got)} of {len(pairs)} pairs")
    known["same_name"] = [
        got.get(p, (None, None))[0] for p in zip(known.name_a, known.name_b)
    ]
    print(known.to_string(index=False))
    sample["same_name"] = [
        got.get(p, (None, None))[0] for p in zip(sample.name_a, sample.name_b)
    ]
    print(sample[["name_a", "name_b", "same_name"]].to_string(index=False))


def judge_all(client):
    pairs = examples()
    got = judge(client, list(zip(pairs.name_a, pairs.name_b)))
    pairs["same_name"] = [
        got.get(p, (None, None))[0] for p in zip(pairs.name_a, pairs.name_b)
    ]
    pairs["cannot_decide"] = [
        got.get(p, (None, None))[1] for p in zip(pairs.name_a, pairs.name_b)
    ]
    pairs["method"] = f"{client.model} reasoning=low prompt={PROMPT_SHA}"
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    pairs.to_parquet(RESULT, index=False)
    print(f"wrote {RESULT}: {pairs.same_name.notna().sum()} of {len(pairs)} pairs")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["pilot", "all"])
    parser.add_argument("--cap", type=float, required=True, help="authorized USD")
    args = parser.parse_args()
    client = Client(args.cap, WORKDIR)
    (pilot if args.stage == "pilot" else judge_all)(client)
    print(client.spend())


if __name__ == "__main__":
    main()
