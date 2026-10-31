"""Count candidates who share a name with a rival in the same contest.

A contest is one seat in one election (``row_id`` in the pooled table). Writes
one row per contest, one row per candidate who has a namesake, a year-by-post
summary, and the close-but-unmerged name pairs that go to review.
"""

import argparse
import hashlib
import json
from itertools import combinations
from pathlib import Path

import pandas as pd
from rapidfuzz.distance import Levenshtein

from candidate_namesakes.names import exact_key, spelling_key

CONTEST_COLUMNS = [
    "row_id",
    "state",
    "year",
    "tier",
    "tier_local",
    "district",
    "block",
    "gp_no",
    "gram_panchayat",
    "ward_no",
    "reserved_caste",
    "reserved_woman",
]
CANDIDATE_COLUMNS = [
    "candidate_id",
    "candidate_name",
    "relation_name",
    "candidate_age",
    "candidate_woman",
    "votes",
    "elected",
]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, expected_sha256):
    found = sha256(path)
    if found != expected_sha256:
        raise SystemExit(f"{path}: sha256 {found}, expected {expected_sha256}")
    candidates = pd.read_parquet(path, columns=CONTEST_COLUMNS + CANDIDATE_COLUMNS)
    candidates["name_exact"] = candidates.candidate_name.map(exact_key)
    candidates["name_spelling"] = candidates.candidate_name.map(spelling_key)
    relation = candidates.relation_name.map(exact_key)
    # The 2016 release repeats some candidates inside a contest, often with
    # different vote totals. Same name, relation and age is one person; where
    # relation or age is blank there is no evidence of a repeat.
    candidates["is_duplicate_record"] = (
        candidates.assign(relation=relation).duplicated(
            ["row_id", "name_exact", "relation", "candidate_age"]
        )
        & candidates.name_exact.notna()
        & relation.notna()
        & candidates.candidate_age.notna()
    )
    return candidates


def flag_namesakes(candidates):
    people = candidates[~candidates.is_duplicate_record & candidates.name_exact.notna()]
    for key in ["exact", "spelling"]:
        size = people.groupby(["row_id", f"name_{key}"]).name_exact.transform("size")
        candidates[f"namesake_{key}_group_size"] = size.reindex(candidates.index)
        candidates[f"has_namesake_{key}"] = candidates[f"namesake_{key}_group_size"].ge(
            2
        )
    return candidates


def summarize_contests(candidates):
    people = candidates[~candidates.is_duplicate_record & candidates.name_exact.notna()]
    grouped = people.groupby("row_id")
    contests = candidates.drop_duplicates("row_id")[CONTEST_COLUMNS].set_index("row_id")
    contests["candidate_count"] = grouped.size()
    contests["duplicate_record_count"] = candidates.groupby(
        "row_id"
    ).is_duplicate_record.sum()
    for key in ["exact", "spelling"]:
        flag = f"has_namesake_{key}"
        contests[f"namesake_{key}_count"] = grouped[flag].sum()
        contests[f"namesake_{key}_group_count"] = (
            people[people[flag]].groupby("row_id")[f"name_{key}"].nunique()
        )
    contests = contests.fillna(
        {
            "candidate_count": 0,
            "namesake_exact_group_count": 0,
            "namesake_spelling_group_count": 0,
            "namesake_exact_count": 0,
            "namesake_spelling_count": 0,
        }
    )
    for column in contests.columns:
        if column.endswith("_count"):
            contests[column] = contests[column].astype("int32")
    contests["has_namesake_exact"] = contests.namesake_exact_count > 0
    contests["has_namesake_spelling"] = contests.namesake_spelling_count > 0
    return contests.reset_index()


def summarize_posts(contests):
    grouped = contests.groupby(["year", "tier"], observed=True)
    summary = grouped.agg(
        contests=("row_id", "size"),
        candidates=("candidate_count", "sum"),
        mean_candidates=("candidate_count", "mean"),
        mean_namesake_exact=("namesake_exact_count", "mean"),
        mean_namesake_spelling=("namesake_spelling_count", "mean"),
        contests_with_namesake_exact_pct=("has_namesake_exact", "mean"),
        contests_with_namesake_spelling_pct=("has_namesake_spelling", "mean"),
        duplicate_records=("duplicate_record_count", "sum"),
    )
    for column in summary.columns:
        if column.endswith("_pct"):
            summary[column] *= 100
    return summary.round(3).reset_index()


def max_edits(length):
    # One edit for a word up to 8 letters, two beyond.
    return 1 if length <= 8 else 2


def close_pair(a, b):
    """Same words except one, and that word differs by an edit or two."""
    words_a, words_b = a.split(), b.split()
    if len(words_a) != len(words_b):
        return None
    differing = [(x, y) for x, y in zip(words_a, words_b) if x != y]
    if len(differing) != 1:
        return None
    x, y = differing[0]
    edits = Levenshtein.distance(x, y)
    return edits if edits <= max_edits(min(len(x), len(y))) else None


def review_pairs(candidates):
    """Pairs in one contest whose spelling keys differ in one word, slightly."""
    people = candidates[
        ~candidates.is_duplicate_record & candidates.name_spelling.notna()
    ]
    rows = []
    for row_id, keys in people.groupby("row_id").name_spelling:
        for a, b in combinations(sorted(set(keys)), 2):
            edits = close_pair(a, b)
            if edits is not None:
                rows.append((row_id, a, b, edits))
    columns = ["row_id", "name_spelling_a", "name_spelling_b", "edits"]
    return pd.DataFrame(rows, columns=columns)


OFFICES = {
    "gp_head": "Mukhiya",
    "gp_ward": "Ward member",
    "block_member": "Panchayat samiti",
    "zp_member": "Zila parishad",
    "kachahari_head": "Sarpanch",
    "kachahari_member": "Panch",
}


def summary_markdown(summary):
    header = (
        "| Year | Office | Contests | Mean candidates | Mean namesakes, exact "
        "| Mean namesakes, spelling | Contests with a namesake, exact (%) "
        "| Contests with a namesake, spelling (%) | Repeated records dropped |\n"
        "|---|---|---:|---:|---:|---:|---:|---:|---:|\n"
    )
    order = {tier: i for i, tier in enumerate(OFFICES)}
    rows = summary.sort_values(
        ["year", "tier"], key=lambda c: c.astype(str).map(order).fillna(c)
    )
    lines = [
        f"| {r.year} | {OFFICES[r.tier]} (`{r.tier}`) | {r.contests:,} "
        f"| {r.mean_candidates:.1f} | {r.mean_namesake_exact:.2f} "
        f"| {r.mean_namesake_spelling:.2f} | {r.contests_with_namesake_exact_pct:.1f} "
        f"| {r.contests_with_namesake_spelling_pct:.1f} | {r.duplicate_records:,} |"
        for r in rows.itertuples()
    ]
    return header + "\n".join(lines)


def update_readme(summary, path=Path("README.md")):
    text = path.read_text()
    start, end = "<!-- summary:start -->", "<!-- summary:end -->"
    before, rest = text.split(start)
    _, after = rest.split(end)
    table = summary_markdown(summary)
    path.write_text(f"{before}{start}\n\n{table}\n\n{end}{after}")


def write(frame, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".csv":
        frame.to_csv(path, index=False)
    else:
        frame.to_parquet(path, index=False)
    return {"path": str(path), "rows": len(frame), "sha256": sha256(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="data/source.json")
    parser.add_argument("--release", default="data/release")
    parser.add_argument("--build", default="data/build")
    args = parser.parse_args()

    source = json.loads(Path(args.source).read_text())
    candidates = flag_namesakes(load(source["path"], source["sha256"]))
    contests = summarize_contests(candidates)
    release, build = Path(args.release), Path(args.build)
    keep = ["row_id", "state", "year", "tier"] + CANDIDATE_COLUMNS
    namesakes = candidates[
        candidates.has_namesake_spelling & ~candidates.is_duplicate_record
    ][
        keep
        + [
            "name_exact",
            "name_spelling",
            "namesake_exact_group_size",
            "namesake_spelling_group_size",
        ]
    ]
    summary = summarize_posts(contests)
    outputs = [
        write(contests, release / "contests.parquet"),
        write(namesakes, release / "namesake_candidates.parquet"),
        write(summary, release / "summary.csv"),
    ]
    update_readme(summary)
    write(review_pairs(candidates), build / "review_pairs.parquet")
    manifest = {"source": source, "outputs": outputs}
    Path("MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
