"""Do candidates whose names resemble the winner's get more votes?

If voters mix up look-alike names, some votes meant for a strong candidate land
on the candidate whose name resembles it. The check compares candidates in the
same contest: among those who did not win, does vote share rise with how close
the name is to the winner's? Contest fixed effects remove everything shared
within a contest (its size, its turnout, how many candidates stood).

Placebo: the same comparison against the last-placed candidate, whose votes
are too few for confusion to move anything. A rise there would mean the
measure picks up something other than confusion (a family or community name
that also draws votes).

    python -m candidate_namesakes.check_votes
"""

import json
from pathlib import Path

import pandas as pd
import statsmodels.api as sm

from candidate_namesakes.count_namesakes import load, update_readme

LEVELS = [
    "same name",
    "contained",
    "similarity 0.8+",
    "similarity 0.6-0.8",
    "similarity 0.5-0.6",
]
RESULT = Path("data/release/vote_check.csv")


def level(pair):
    if pair is None:
        return "unlike"
    if pair.is_same_spelling:
        return "same name"
    if pair.is_contained:
        return "contained"
    similarity = pair.differing_word_similarity
    if not pair.shares_a_word:
        return "unlike"
    if similarity >= 0.8:
        return "similarity 0.8+"
    if similarity >= 0.6:
        return "similarity 0.6-0.8"
    return "similarity 0.5-0.6"


def contests_with_votes(candidates):
    """Candidates in contests where every vote count is recorded and one wins."""
    people = candidates[
        ~candidates.is_duplicate_record & candidates.name_spelling.notna()
    ].copy()
    recorded = people.votes.notna().groupby(people.row_id).transform("all")
    total = people.groupby("row_id").votes.transform("sum")
    size = people.groupby("row_id").votes.transform("size")
    people = people[recorded & (total > 0) & (size >= 3)]
    grouped = people.groupby("row_id").votes
    top = grouped.transform("max")
    bottom = grouped.transform("min")
    single_top = people.votes.eq(top).groupby(people.row_id).transform("sum") == 1
    single_bottom = people.votes.eq(bottom).groupby(people.row_id).transform("sum") == 1
    people = people[single_top & single_bottom]
    people["vote_share_pct"] = (
        100 * people.votes / people.groupby("row_id").votes.transform("sum")
    )
    people["is_winner"] = people.votes.eq(
        people.groupby("row_id").votes.transform("max")
    )
    people["is_last"] = people.votes.eq(people.groupby("row_id").votes.transform("min"))
    return people


def resemblance_to(people, pairs, flag):
    """Each candidate's resemblance level to the contest's flagged candidate."""
    target = people[people[flag]].set_index("row_id").candidate_id
    lookup = {}
    for pair in pairs.itertuples(index=False):
        lookup[(pair.candidate_id_a, pair.candidate_id_b)] = pair
        lookup[(pair.candidate_id_b, pair.candidate_id_a)] = pair
    return [
        level(lookup.get((cid, target.get(rid))))
        for cid, rid in zip(people.candidate_id, people.row_id)
    ]


def within_contest_fit(frame, column):
    """OLS of vote share on resemblance levels, demeaned within contest."""
    dummies = pd.get_dummies(frame[column])[LEVELS].astype(float)
    data = pd.concat([frame[["row_id", "vote_share_pct"]], dummies], axis=1)
    demeaned = data.drop(columns="row_id") - data.groupby("row_id").transform("mean")
    groups = pd.factorize(frame.row_id)[0]
    fit = sm.OLS(demeaned.vote_share_pct, demeaned[LEVELS]).fit(
        cov_type="cluster", cov_kwds={"groups": groups}
    )
    counts = frame[column].value_counts()
    return pd.DataFrame(
        {
            "level": LEVELS,
            "candidates": [int(counts.get(name, 0)) for name in LEVELS],
            "vote_share_gap_pct": fit.params.values,
            "std_error": fit.bse.values,
        }
    )


def vote_markdown(result, people):
    pooled = result[result.office == "all offices"]
    lines = [
        f"{people.row_id.nunique():,} contests with every vote count recorded and "
        "one clear winner and last-placed candidate.",
        "",
        "| Resembles | Resemblance | Candidates | Vote-share gap (points) "
        "| Standard error |",
        "|---|---|---:|---:|---:|",
    ]
    lines += [
        f"| {r.resembles} | {r.level} | {r.candidates:,} "
        f"| {r.vote_share_gap_pct:+.2f} | {r.std_error:.2f} |"
        for r in pooled.itertuples()
    ]
    return "\n".join(lines)


def main():
    source = json.loads(Path("data/source.json").read_text())
    candidates = load(source)
    pairs = pd.read_parquet("data/release/name_pairs.parquet")
    people = contests_with_votes(candidates)
    people["like_winner"] = resemblance_to(people, pairs, "is_winner")
    people["like_last"] = resemblance_to(people, pairs, "is_last")
    tables = []
    by_office = people.groupby("tier", observed=True)
    for office, subset in [("all offices", people), *by_office]:
        office = str(office)
        losers = subset[~subset.is_winner]
        middle = subset[~subset.is_winner & ~subset.is_last]
        for target, frame, column in [
            ("winner", losers, "like_winner"),
            ("last-placed (placebo)", middle, "like_last"),
        ]:
            if frame[column].isin(LEVELS).sum() < 30:
                continue
            table = within_contest_fit(frame, column)
            table.insert(0, "resembles", target)
            table.insert(0, "office", office)
            table["baseline_mean_share_pct"] = frame.loc[
                frame[column] == "unlike", "vote_share_pct"
            ].mean()
            tables.append(table)
    result = pd.concat(tables).round(3)
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(RESULT, index=False)
    print(people.groupby("state").row_id.nunique())
    update_readme(vote_markdown(result, people), marker="votes")
    print(f"{people.row_id.nunique():,} contests with complete votes")
    pd.set_option("display.width", 200)
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
