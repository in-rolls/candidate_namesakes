"""Count candidates who share a name with a rival in the same contest.

A contest is one seat in one election (``row_id`` in the pooled table). Writes
one row per contest, one row per candidate who has a namesake, one row per pair
of candidates whose names resemble each other, and a year-by-office summary.
"""

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from candidate_namesakes.names import exact_key, spelling_key
from candidate_namesakes.pairs import build_pairs

CONTEST_COLUMNS = [
    "row_id",
    "state",
    "year",
    "tier",
    "tier_local",
    "election_type",
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


def read_inputs(source):
    """Every pinned input, hash-checked, as one candidate table."""
    frames = []
    for item in source["inputs"]:
        found = sha256(item["path"])
        if found != item["sha256"]:
            raise SystemExit(
                f"{item['path']}: sha256 {found}, expected {item['sha256']}"
            )
        frames.append(
            pd.read_parquet(item["path"], columns=CONTEST_COLUMNS + CANDIDATE_COLUMNS)
        )
    candidates = pd.concat(frames, ignore_index=True)
    for column in ["tier", "reserved_caste", "election_type"]:
        candidates[column] = candidates[column].astype("string")
    return candidates


def load(source):
    candidates = read_inputs(source)
    candidates["name_exact"] = candidates.candidate_name.map(exact_key)
    candidates["name_spelling"] = candidates.candidate_name.map(spelling_key)
    # Grouping ignores spaces: राज कुमार and राजकुमार are one name.
    candidates["name_spelling_compact"] = candidates.name_spelling.str.replace(" ", "")
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
    for key, column in [("exact", "name_exact"), ("spelling", "name_spelling_compact")]:
        size = people.groupby(["row_id", column]).name_exact.transform("size")
        candidates[f"namesake_{key}_group_size"] = size.reindex(candidates.index)
        candidates[f"has_namesake_{key}"] = candidates[f"namesake_{key}_group_size"].ge(
            2
        )
    return candidates


# Muse Spark's pilot rated 34 of 37 pairs at this similarity "easily confused"
# and 11 of 16 just below it (README, Look-alike names).
LOOKALIKE_SIMILARITY = 0.7


def flag_lookalikes(candidates, pairs):
    """A candidate is a look-alike if any pair with them is close enough."""
    close = pairs[
        pairs.is_same_spelling
        | pairs.is_contained
        | (
            pairs.differing_word_similarity.ge(LOOKALIKE_SIMILARITY)
            & pairs.shares_a_word
        )
    ]
    ids = set(close.candidate_id_a) | set(close.candidate_id_b)
    candidates["has_lookalike"] = candidates.candidate_id.isin(ids)
    return candidates


def summarize_contests(candidates):
    people = candidates[~candidates.is_duplicate_record & candidates.name_exact.notna()]
    grouped = people.groupby("row_id")
    contests = candidates.drop_duplicates("row_id")[CONTEST_COLUMNS].set_index("row_id")
    contests["candidate_count"] = grouped.size()
    contests["duplicate_record_count"] = candidates.groupby(
        "row_id"
    ).is_duplicate_record.sum()
    contests["lookalike_count"] = grouped.has_lookalike.sum()
    for key in ["exact", "spelling"]:
        flag = f"has_namesake_{key}"
        contests[f"namesake_{key}_count"] = grouped[flag].sum()
        column = "name_exact" if key == "exact" else "name_spelling_compact"
        contests[f"namesake_{key}_group_count"] = (
            people[people[flag]].groupby("row_id")[column].nunique()
        )
    contests = contests.fillna(
        {
            "candidate_count": 0,
            "namesake_exact_group_count": 0,
            "namesake_spelling_group_count": 0,
            "namesake_exact_count": 0,
            "namesake_spelling_count": 0,
            "lookalike_count": 0,
        }
    )
    for column in contests.columns:
        if column.endswith("_count"):
            contests[column] = contests[column].astype("int32")
    contests["has_namesake_exact"] = contests.namesake_exact_count > 0
    contests["has_namesake_spelling"] = contests.namesake_spelling_count > 0
    contests["has_lookalike"] = contests.lookalike_count > 0
    return contests.reset_index()


POST = ["state", "year", "tier", "tier_local", "election_type"]


def summarize_posts(contests):
    grouped = contests.groupby(POST, observed=True, dropna=False)
    summary = grouped.agg(
        contests=("row_id", "size"),
        candidates=("candidate_count", "sum"),
        mean_candidates=("candidate_count", "mean"),
        mean_namesake_exact=("namesake_exact_count", "mean"),
        mean_namesake_spelling=("namesake_spelling_count", "mean"),
        contests_with_namesake_exact_pct=("has_namesake_exact", "mean"),
        contests_with_namesake_spelling_pct=("has_namesake_spelling", "mean"),
        contests_with_lookalike_pct=("has_lookalike", "mean"),
        duplicate_records=("duplicate_record_count", "sum"),
    )
    for column in summary.columns:
        if column.endswith("_pct"):
            summary[column] *= 100
    return summary.round(3).reset_index()


def summary_markdown(summary):
    header = (
        "| State | Year | Office | Election | Contests | Mean candidates "
        "| Mean namesakes, exact | Mean namesakes, spelling "
        "| Contests with a namesake, exact (%) "
        "| Contests with a namesake, spelling (%) | Contests with a look-alike (%) "
        "| Repeated records dropped |\n"
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|\n"
    )
    rows = summary.sort_values(["state", "year", "contests"], ascending=[1, 1, 0])
    lines = [
        f"| {r.state} | {r.year} | {r.tier_local.title()} (`{r.tier}`) "
        f"| {r.election_type if isinstance(r.election_type, str) else 'not recorded'} "
        f"| {r.contests:,} | {r.mean_candidates:.1f} | {r.mean_namesake_exact:.2f} "
        f"| {r.mean_namesake_spelling:.2f} | {r.contests_with_namesake_exact_pct:.1f} "
        f"| {r.contests_with_namesake_spelling_pct:.1f} "
        f"| {r.contests_with_lookalike_pct:.1f} | {r.duplicate_records:,} |"
        for r in rows.itertuples()
    ]
    return header + "\n".join(lines)


def update_readme(table, marker="summary", path=Path("README.md")):
    """Replace the README block between ``<!-- marker:start/end -->``."""
    text = path.read_text()
    start, end = f"<!-- {marker}:start -->", f"<!-- {marker}:end -->"
    before, rest = text.split(start)
    _, after = rest.split(end)
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
    args = parser.parse_args()

    source = json.loads(Path(args.source).read_text())
    candidates = flag_namesakes(load(source))
    pairs = build_pairs(candidates)
    candidates = flag_lookalikes(candidates, pairs)
    contests = summarize_contests(candidates)
    release = Path(args.release)
    meta = candidates.drop_duplicates("row_id")[["row_id", "state", "year", "tier"]]
    pairs = meta.merge(pairs, on="row_id", how="right")
    keep = ["row_id", "state", "year", "tier"] + CANDIDATE_COLUMNS
    namesakes = candidates[
        (candidates.has_namesake_spelling | candidates.has_lookalike)
        & ~candidates.is_duplicate_record
    ][
        keep
        + [
            "name_exact",
            "name_spelling",
            "namesake_exact_group_size",
            "namesake_spelling_group_size",
            "has_lookalike",
        ]
    ]
    summary = summarize_posts(contests)
    outputs = [
        write(contests, release / "contests.parquet"),
        write(namesakes, release / "namesake_candidates.parquet"),
        write(pairs, release / "name_pairs.parquet"),
        write(summary, release / "summary.csv"),
    ]
    update_readme(summary_markdown(summary))
    manifest = {"source": source, "outputs": outputs}
    Path("MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
