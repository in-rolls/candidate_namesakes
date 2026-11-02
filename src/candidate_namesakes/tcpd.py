"""Namesakes of the leading candidates in Lok Sabha and assembly elections.

Input: TCPD Indian Elections Data v2.0 (Lok Dhaba), every candidate in every
Lok Sabha (GE) and state assembly (AE) election since 1962. A contest is one
poll in one constituency: TCPD's ``Poll_No`` is 0 at a general election and
counts by-elections after it.

For the winner and runner-up of each contest, the other candidates whose names
resemble theirs are counted at four levels, each including the ones before:
exact name, same spelling (word order ignored), same except initials, and
look-alike (one name inside the other, or a shared word and the remaining
words at least 0.7 similar). Writes per-contest rows and summaries by election
and year.

    python -m candidate_namesakes.tcpd
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd

from candidate_namesakes.count_namesakes import (
    LOOKALIKE_SIMILARITY,
    sha256,
    update_readme,
)
from candidate_namesakes.names import add_name_columns
from candidate_namesakes.pairs import build_pairs

CONTEST = ["election", "State_Name", "Assembly_No", "Constituency_No", "Year"]
CONTEST += ["month", "Poll_No"]
LEVELS = ["exact", "spelling", "alias", "initials", "lookalike"]
# ECI order: candidate photographs on EVMs and ballots from 1 May 2015.
PHOTO_RULE = 201505
RELEASE = Path("data/release/tcpd")
# In some years TCPD (from the ECI reports) prints most names as initials and a
# surname ("K.N. RAO"); a match then says only that two surnames agree. A
# state-election-year is set aside when its share of such names is this far
# above the state's median year. Where initials and a given name are the
# custom (Tamil Nadu, Puducherry) the median is high and nothing is dropped.
ABBREVIATED_JUMP = 0.4


def is_abbreviated(name):
    """True for a name that is only initials and one word."""
    words = re.sub(r"[^A-Z ]", " ", str(name).upper()).split()
    return (
        len(words) >= 2 and all(len(w) == 1 for w in words[:-1]) and len(words[-1]) > 1
    )


def read_tcpd(source):
    frames = []
    for item in source["tcpd"]:
        found = sha256(item["path"])
        if found != item["sha256"]:
            raise SystemExit(
                f"{item['path']}: sha256 {found}, expected {item['sha256']}"
            )
        frame = pd.read_csv(item["path"], low_memory=False)
        frame["election"] = item["election"]
        frames.append(frame)
    tcpd = pd.concat(frames, ignore_index=True)
    tcpd = tcpd[tcpd.Party.ne("NOTA") & tcpd.Candidate.ne("NOTA")].copy()
    tcpd["row_id"] = tcpd.groupby(CONTEST, dropna=False, sort=False).ngroup()
    tcpd["candidate_id"] = tcpd.row_id.astype(str) + "|" + tcpd.Position.astype(str)
    tcpd["candidate_name"] = tcpd.Candidate
    # ECI reports do not number namesakes; a trailing I or V is an initial.
    tcpd = add_name_columns(tcpd, "Candidate", False)
    tcpd["is_duplicate_record"] = False
    tcpd["is_abbreviated"] = tcpd.Candidate.map(is_abbreviated)
    share = tcpd.groupby(["election", "State_Name", "Year"]).is_abbreviated.mean()
    usual = share.groupby(level=["election", "State_Name"]).transform("median")
    flagged = (share - usual).ge(ABBREVIATED_JUMP).rename("names_abbreviated")
    tcpd = tcpd.join(flagged, on=["election", "State_Name", "Year"])
    return tcpd


def tier(pairs):
    """The strictest level at which each pair's names match, or None."""
    lookalike = pairs.is_contained | (
        pairs.differing_word_similarity.ge(LOOKALIKE_SIMILARITY) & pairs.shares_a_word
    )
    level = pd.Series(pd.NA, index=pairs.index, dtype="string")
    level[lookalike] = "lookalike"
    level[pairs.is_same_except_initials] = "initials"
    level[pairs.is_alias_match] = "alias"
    level[pairs.is_same_spelling] = "spelling"
    level[pairs.is_same_exact] = "exact"
    return level


def namesakes_of_leaders(tcpd, pairs):
    """One row per contest: the leaders' namesakes at each level."""
    pairs = pairs.assign(level=tier(pairs)).dropna(subset=["level"])
    position = tcpd.set_index("candidate_id").Position
    rows = pd.concat(
        [
            pairs.rename(
                columns={"candidate_id_a": "target", "candidate_id_b": "other"}
            ),
            pairs.rename(
                columns={"candidate_id_b": "target", "candidate_id_a": "other"}
            ),
        ]
    )
    rows["target_position"] = rows.target.map(position)
    rows["other_position"] = rows.other.map(position)
    # A leader's namesake is a lower-placed candidate; the two leaders
    # resembling each other is a different event, counted separately.
    rows = rows[rows.target_position.le(2) & rows.other_position.gt(2)]
    other = tcpd.set_index("candidate_id")
    rows["other_votes"] = rows.other.map(other.Votes)
    rows["other_independent"] = rows.other.map(other.Party).eq("IND")
    contests = tcpd.groupby("row_id").agg(
        election=("election", "first"),
        state=("State_Name", "first"),
        year=("Year", "first"),
        month=("month", "first"),
        constituency=("Constituency_Name", "first"),
        by_election=("Poll_No", lambda p: bool((p > 0).any())),
        names_abbreviated=("names_abbreviated", "first"),
        candidates=("Candidate", "size"),
        valid_votes=("Valid_Votes", "first"),
    )
    winner = tcpd[tcpd.Position.eq(1)].set_index("row_id")
    runner = tcpd[tcpd.Position.eq(2)].set_index("row_id")
    contests["winner"] = winner.Candidate
    contests["runner_up"] = runner.Candidate
    contests["margin"] = winner.Votes - runner.Votes
    order = {name: i for i, name in enumerate(LEVELS)}
    rows["rank"] = rows.level.map(order)
    for name in LEVELS:
        within = rows[rows["rank"] <= order[name]].drop_duplicates(["row_id", "other"])
        grouped = within.groupby("row_id")
        contests[f"namesakes_{name}"] = grouped.size()
        contests[f"namesake_votes_{name}"] = grouped.other_votes.sum()
        contests[f"namesakes_{name}_independent"] = grouped.other_independent.sum()
        of_runner = within[within.target_position.eq(2)].groupby("row_id")
        contests[f"runner_up_namesake_votes_{name}"] = of_runner.other_votes.sum()
    counts = [c for c in contests.columns if c.startswith(("namesake", "runner_up_n"))]
    contests[counts] = contests[counts].fillna(0)
    contests["after_photo_rule"] = (contests.year * 100 + contests.month).ge(PHOTO_RULE)
    return contests.reset_index()


def pair_rates(tcpd, pairs):
    """Namesake pairs per 10,000: leader-minor pairs vs minor-minor pairs."""
    pairs = pairs.assign(level=tier(pairs)).dropna(subset=["level"])
    position = tcpd.set_index("candidate_id").Position
    lead_a = pairs.candidate_id_a.map(position).le(2)
    lead_b = pairs.candidate_id_b.map(position).le(2)
    pairs["kind"] = "minor-minor"
    pairs.loc[lead_a ^ lead_b, "kind"] = "leader-minor"
    pairs = pairs[~(lead_a & lead_b)]
    usable = tcpd[~tcpd.names_abbreviated]
    pairs = pairs[pairs.row_id.isin(usable.row_id)]
    sizes = usable.groupby("row_id").agg(
        election=("election", "first"),
        n=("Candidate", "size"),
        leaders=("Position", lambda p: int(p.le(2).sum())),
    )
    minors = sizes.n - sizes.leaders
    possible = pd.DataFrame(
        {
            "election": sizes.election,
            "leader-minor": sizes.leaders * minors,
            "minor-minor": minors * (minors - 1) / 2,
        }
    )
    possible = possible.groupby("election").sum()
    election = pairs.row_id.map(sizes.election)
    order = {name: i for i, name in enumerate(LEVELS)}
    rows = []
    for name in LEVELS:
        within = pairs[pairs.level.map(order) <= order[name]]
        found = within.groupby([election[within.index], within.kind]).size()
        for (elec, kind), count in found.items():
            rows.append(
                {
                    "election": elec,
                    "level": name,
                    "pair": kind,
                    "namesake_pairs": int(count),
                    "possible_pairs": int(possible.loc[elec, kind]),
                }
            )
    rates = pd.DataFrame(rows)
    rates["per_10000"] = 1e4 * rates.namesake_pairs / rates.possible_pairs
    return rates.round(3)


def extent(contests):
    """By election and year: how often a leader faces a namesake."""
    general = contests[~contests.by_election & ~contests.names_abbreviated]
    out = []
    for keys, group in general.groupby(["election", "year"]):
        row = dict(zip(["election", "year"], keys))
        row["contests"] = len(group)
        for name in LEVELS:
            has = group[f"namesakes_{name}"] > 0
            row[f"with_{name}_pct"] = 100 * has.mean()
            row[f"namesakes_{name}"] = int(group[f"namesakes_{name}"].sum())
        faced = group[group.namesakes_lookalike > 0]
        row["lookalike_independent_pct"] = (
            100
            * group.namesakes_lookalike_independent.sum()
            / max(group.namesakes_lookalike.sum(), 1)
        )
        row["lookalike_vote_share_pct"] = (
            100 * (faced.namesake_votes_lookalike / faced.valid_votes).median()
            if len(faced)
            else None
        )
        row["pivotal_lookalike"] = int(
            (group.runner_up_namesake_votes_lookalike > group.margin).sum()
        )
        out.append(row)
    return pd.DataFrame(out).round(2)


def extent_markdown(table, rates):
    lines = [
        "| Election | Year | Contests | Exact (%) | Same spelling (%) "
        "| Alias (%) | Initials differ (%) | Look-alike (%) "
        "| Look-alikes who are independents (%) "
        "| Runner-up's look-alikes outpolled the margin |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    big = table[table.contests >= 100]
    for r in big.sort_values(["election", "year"]).itertuples():
        lines.append(
            f"| {r.election.replace('_', ' ').title()} | {r.year} | {r.contests:,} "
            f"| {r.with_exact_pct:.1f} | {r.with_spelling_pct:.1f} "
            f"| {r.with_alias_pct:.1f} | {r.with_initials_pct:.1f} "
            f"| {r.with_lookalike_pct:.1f} | {r.lookalike_independent_pct:.0f} "
            f"| {r.pivotal_lookalike:,} |"
        )
    wide = rates.pivot_table(
        index=["election", "level"], columns="pair", values="per_10000"
    ).reset_index()
    lines += [
        "",
        "| Election | Match level | Leader-minor pairs (per 10,000) "
        "| Minor-minor pairs (per 10,000) | Ratio |",
        "|---|---|---:|---:|---:|",
    ]
    order = {name: i for i, name in enumerate(LEVELS)}
    wide = wide.sort_values(["election", "level"], key=lambda c: c.map(order).fillna(c))
    for r in wide.to_dict("records"):
        lead, minor = r["leader-minor"], r["minor-minor"]
        lines.append(
            f"| {r['election'].replace('_', ' ').title()} | {r['level']} | {lead:.1f} "
            f"| {minor:.1f} | {lead / minor:.2f} |"
        )
    return "\n".join(lines)


def write_readme():
    table = pd.read_csv(RELEASE / "extent.csv")
    rates = pd.read_csv(RELEASE / "pair_rates.csv")
    update_readme(extent_markdown(table, rates), marker="tcpd")


def main():
    if "--readme" in sys.argv:
        write_readme()
        return
    source = json.loads(Path("data/source.json").read_text())
    tcpd = read_tcpd(source)
    pairs = build_pairs(tcpd)
    contests = namesakes_of_leaders(tcpd, pairs)
    RELEASE.mkdir(parents=True, exist_ok=True)
    contests.to_parquet(RELEASE / "contests.parquet", index=False)
    table = extent(contests)
    table.to_csv(RELEASE / "extent.csv", index=False)
    rates = pair_rates(tcpd, pairs)
    excluded = (
        contests[contests.names_abbreviated]
        .groupby(["election", "state", "year"])
        .size()
        .rename("contests")
        .reset_index()
    )
    excluded.to_csv(RELEASE / "excluded_abbreviated.csv", index=False)
    rates.to_csv(RELEASE / "pair_rates.csv", index=False)
    keep = ["row_id", "candidate_id_a", "candidate_id_b", "candidate_name_a"]
    keep += ["candidate_name_b"]
    leveled = pairs.assign(level=tier(pairs)).dropna(subset=["level"])
    leveled[keep + ["level"]].to_parquet(RELEASE / "name_pairs.parquet", index=False)
    write_readme()
    print(table.to_string(index=False))
    print(rates.to_string(index=False))


if __name__ == "__main__":
    main()
