"""Do namesake candidates confuse voters, and does it change who wins?

Within-contest comparisons of independent (IND) candidates whose names resemble
a leading party candidate against other independents in the same Lok Sabha or
assembly contest, on three outcomes that answer different questions:

- the candidate's percentile rank among the contest's independents (does the
  name help at all, regardless of a few large vote totals);
- log(1 + votes) (the proportional gain of a typical namesake);
- votes, by Poisson regression (the proportional gain in mean votes, which a
  few large independent totals dominate).

The 1 May 2015 rule putting photographs on voting machines is tested against
placebo break dates and a trend in the namesake premium. Bihar's panchayat
elections are a local-election comparison. Writes LaTeX tables (pyfixest
etable / maketables) and macros to ``tabs/`` and figures to ``figs/``.

    python -m candidate_namesakes.econometrics
"""

import json
from pathlib import Path

import maketables as mt
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyfixest as pf
from rapidfuzz import fuzz

from candidate_namesakes import plotstyle
from candidate_namesakes.check_votes import contests_with_votes, resemblance_to
from candidate_namesakes.count_namesakes import load as load_local
from candidate_namesakes.tcpd import PHOTO_RULE, read_tcpd

TABS = Path("tabs")
FIGS = Path("figs")

# Clustering by constituency, not contest: a constituency holds repeated
# contests over six decades, and its namesake supply and voters persist.
CLUSTER = {"CRV1": "constituency"}
TIER_ORDER = {"exact": 0, "spelling": 1, "alias": 2, "initials": 3, "lookalike": 4}
PHOTO_YEAR = PHOTO_RULE // 100 + (PHOTO_RULE % 100 - 1) / 12
PLACEBO_BREAKS = [1977, 1980, 1985, 1989, 1991, 1996, 1998, 2000, 2004, 2008]
PLACEBO_BREAKS += [2010, 2012, 2014, PHOTO_YEAR, 2017, 2019]
PERIODS = [
    ("p1962_1989", "1962–89"),
    ("p1990_1999", "1990–99"),
    ("p2000_2004", "2000–04"),
    ("p2005_2009", "2005–09"),
    ("p2010_Apr2015", "2010–Apr 15"),
    ("pMay2015_2019", "May 15–19"),
    ("p2020_2026", "2020–26"),
]
OUTCOMES = {
    "rank_pct": "Rank (percentile pts.)",
    "log_votes": "Log(1 + votes)",
    "Votes": "Votes (Poisson)",
}
LABELS = {
    **OUTCOMES,
    "t_exact": "Exact / spelling",
    "t_init": "Initials differ",
    "t_look": "Look-alike",
    "t_close": "Close name",
    "m_exact": "Placebo: exact / spelling",
    "m_init": "Placebo: initials differ",
    "m_look": "Placebo: look-alike",
    "t_close_post": "Close name x after May 2015",
    "t_look_post": "Look-alike x after May 2015",
    "t_close_trend": "Close name x decades from May 2015",
    "t_look_trend": "Look-alike x decades from May 2015",
    "log_name_freq": "Log name frequency",
    "b_same": "Same name / alias",
    "b_contained": "One name contains the other",
    "b_sim8": "Similarity 0.8+",
    "b_sim6": "Similarity 0.6-0.8",
}
ETABLE = dict(
    type="tex",
    labels=LABELS,
    felabels={"row_id": "Contest fixed effects"},
    coef_fmt="b:.2f \n (se:.2f)",
    exact_match=True,
    model_stats=["N"],
    model_stats_labels={"N": "Candidates"},
)


def period_bin(ym):
    year = ym // 100
    for upper, key in [(1990, 0), (2000, 1), (2005, 2), (2010, 3)]:
        if year < upper:
            return PERIODS[key][0]
    if ym < PHOTO_RULE:
        return PERIODS[4][0]
    return PERIODS[5][0] if year < 2020 else PERIODS[6][0]


def rank_pct(votes, contest):
    """Mid-rank percentile (0-100) of each candidate's votes within contest.

    (rank - 0.5) / n has mean exactly 50 in every contest, so a within-contest
    regression coefficient reads as percentile points above the average rival.
    """
    ranks = votes.groupby(contest).rank(method="average")
    size = votes.groupby(contest).transform("size")
    return 100 * (ranks - 0.5) / size


def diverted_share(log_premium):
    """Share of a namesake's votes owed to the name, if it multiplies votes.

    A premium b means the namesake polls exp(b) times what it would otherwise,
    so 1 - exp(-b) of its votes came from the resemblance; none if b <= 0.
    """
    return np.clip(1 - np.exp(-np.asarray(log_premium, dtype=float)), 0, None)


def _fit(df, outcome, regressors, poisson=False):
    est = pf.fepois if poisson else pf.feols
    return est(f"{outcome} ~ {' + '.join(regressors)} | row_id", df, vcov=CLUSTER)


def _etable(name, fits, keep, notes, **kwargs):
    tex = pf.etable(fits, keep=keep, notes=notes, **ETABLE, **kwargs)
    (TABS / name).write_text(tex)


def _tiers(df, col, prefix="t_"):
    df[prefix + "exact"] = df[col].isin(["exact", "spelling", "alias"]).astype(float)
    df[prefix + "init"] = (df[col] == "initials").astype(float)
    df[prefix + "look"] = (df[col] == "lookalike").astype(float)
    df[prefix + "close"] = df[prefix + "exact"] + df[prefix + "init"]
    return df


def _sample(ind):
    """Independents in contests with at least two of them, with rank outcome."""
    n = ind.groupby("row_id").row_id.transform("size")
    d = ind[n >= 2].copy()
    d["rank_pct"] = rank_pct(d["Votes"], d["row_id"])
    return d


# ECI's national parties from its order of 10 April 2023 (BJP, INC, BSP,
# CPI(M), AAP, NPP), by TCPD-PPI Party_ID; TCPD's own flag covers earlier years.
NATIONAL_2023 = {1605, 3482, 16651, 14635, 13, 5671}
INCUMBENT_SIMILARITY = 90


def mark_incumbents(usable):
    """Flag the candidate who won the seat's previous general election.

    TCPD links candidates across elections by a person ID that the post-2023
    files lack, so one rule is used for every year: in each contest, the
    candidate whose name is most similar to the previous general election's
    winner of the same seat (rapidfuzz token-set ratio of at least 90, seat
    boundaries unchanged), ties going to the winner's party. Party is known
    before the vote; votes are not. At most one per contest, so a namesake of
    the sitting member is not also flagged. On TCPD's 2014-2023 rows this
    agrees with TCPD's Incumbent flag for 98.6% of candidates.
    """
    general = usable[usable["Poll_No"] == 0]
    seq = general["Year"] * 100 + general["month"].fillna(0)
    polls = (
        general.assign(seq=seq)
        .drop_duplicates(["election", "State_Name", "seq"])[
            ["election", "State_Name", "seq"]
        ]
        .sort_values("seq")
    )
    polls["prev_seq"] = polls.groupby(["election", "State_Name"])["seq"].shift(1)
    rows = general.assign(seq=seq).merge(
        polls, on=["election", "State_Name", "seq"], how="left"
    )
    rows.index = general.index
    seat = ["election", "State_Name", "Constituency_No"]
    winners = rows[rows["Position"] == 1][
        seat + ["seq", "name_spelling", "DelimID", "Party"]
    ].rename(
        columns={
            "seq": "prev_seq",
            "name_spelling": "prev_name",
            "DelimID": "prev_delim",
            "Party": "prev_party",
        }
    )
    rows = rows.reset_index().merge(winners, on=seat + ["prev_seq"], how="left")
    rows = rows.set_index("index")
    same_seat = rows["prev_name"].notna() & rows["DelimID"].eq(rows["prev_delim"])
    score = pd.Series(0.0, index=rows.index)
    score[same_seat] = [
        fuzz.token_set_ratio(a, b)
        for a, b in zip(
            rows.loc[same_seat, "name_spelling"], rows.loc[same_seat, "prev_name"]
        )
    ]
    rows["score"] = score
    rows["same_party"] = rows["Party"].eq(rows["prev_party"])
    best = (
        rows[rows["score"] >= INCUMBENT_SIMILARITY]
        .sort_values(["score", "same_party"], ascending=False)
        .drop_duplicates(["row_id"])
        .index
    )
    return usable.index.isin(best)


def _prepare_tcpd(source):
    tcpd = read_tcpd(source)
    pairs = pd.read_parquet("data/release/tcpd/name_pairs.parquet")
    usable = tcpd[
        (tcpd.Poll_No == 0)
        & (~tcpd.names_abbreviated)
        & (tcpd.Valid_Votes > 0)
        & tcpd.Votes.notna()
    ].copy()
    usable["log_votes"] = np.log1p(usable["Votes"])
    usable["ym"] = usable["Year"] * 100 + usable["month"].fillna(0)
    usable["post2015"] = (usable["ym"] >= PHOTO_RULE).astype(int)
    usable["year_frac"] = usable["Year"] + (usable["month"].fillna(1) - 1) / 12
    freq = usable["name_spelling"].value_counts()
    usable["log_name_freq"] = np.log1p(usable["name_spelling"].map(freq).fillna(0))
    usable["is_incumbent"] = mark_incumbents(usable)
    usable["constituency"] = (
        usable["State_Name"].astype(str)
        + "|"
        + usable["election"].astype(str)
        + "|"
        + usable["Constituency_Name"].astype(str).str.upper()
    )

    pairs = pairs[pairs.row_id.isin(usable.row_id.unique())].dropna(subset=["level"])
    pairs = pairs.assign(rank=pairs["level"].map(TIER_ORDER))
    cols = ["row_id", "level", "rank"]
    p_sym = pd.concat(
        [
            pairs[cols + ["candidate_id_a", "candidate_id_b"]].rename(
                columns={"candidate_id_a": "ind_id", "candidate_id_b": "target_id"}
            ),
            pairs[cols + ["candidate_id_b", "candidate_id_a"]].rename(
                columns={"candidate_id_b": "ind_id", "candidate_id_a": "target_id"}
            ),
        ],
        ignore_index=True,
    )
    info = usable.set_index("candidate_id")
    party = p_sym["target_id"].map(info["Party"])
    pos = p_sym["target_id"].map(info["Position"])
    incumbent = p_sym["target_id"].map(info["is_incumbent"]).fillna(False)
    year = p_sym["target_id"].map(info["Year"])
    national = p_sym["target_id"].map(info["Party_Type_TCPD"]).eq("National Party")
    national |= year.ge(2024) & p_sym["target_id"].map(info["Party_ID"]).isin(
        NATIONAL_2023
    )
    is_party = party.notna() & (party != "IND")

    ind = usable[usable["Party"] == "IND"].copy()

    def attach(mask, col):
        sub = p_sym[mask].sort_values("rank").drop_duplicates("ind_id")
        ind[col] = (
            ind["candidate_id"].map(sub.set_index("ind_id")["level"]).fillna("unlike")
        )

    attach(is_party & (pos == 1), "like_winner")
    attach(is_party & (pos == 2), "like_runner_up")
    attach(is_party & (pos <= 2), "like_leader")
    attach(is_party & (incumbent | national), "like_exante")
    attach(is_party & (pos >= 3), "like_minor_party")
    return usable, ind


def confusion_table(d):
    """Table 1: leader resemblance and the minor-party placebo, three outcomes."""
    d = _tiers(_tiers(d.copy(), "like_leader"), "like_minor_party", "m_")
    regs = ["t_exact", "t_init", "t_look", "m_exact", "m_init", "m_look"]
    regs.append("log_name_freq")
    fits = {o: _fit(d, o, regs, poisson=o == "Votes") for o in OUTCOMES}
    treated = f"{int((d.like_leader != 'unlike').sum()):,}"
    _etable(
        "confusion.tex",
        list(fits.values()),
        regs,
        "Independents placed third or lower, in contests with at least two of "
        "them. Rows 1-3: resemblance to a party candidate placed first or "
        "second; rows 4-6: to a party candidate placed third or lower. "
        "Standard errors clustered by constituency in parentheses.",
        custom_model_stats={
            "Independent namesakes of a leader": [treated] * 3,
            "Contests": [f"{d.row_id.nunique():,}"] * 3,
        },
    )
    return fits, d


def targets_table(d, ind):
    """Table 2: close-name and look-alike premium across targets and samples."""
    every = _sample(ind)
    specs = [
        ("Top-2 leader", d, "like_leader"),
        ("Winner", d, "like_winner"),
        ("Incumbent or national party", d, "like_exante"),
        ("All independents", every, "like_leader"),
        ("Lok Sabha", d[d.election == "lok_sabha"], "like_leader"),
        ("Assembly", d[d.election == "assembly"], "like_leader"),
    ]
    regs = ["t_close", "t_look", "log_name_freq"]
    fits = []
    for _, df, col in specs:
        df = _tiers(df.copy(), col)
        fits.append({o: _fit(df, o, regs, poisson=o == "Votes") for o in OUTCOMES})
    for out, panel in zip(OUTCOMES, "abc"):
        _etable(
            f"targets_{panel}.tex",
            [f[out] for f in fits],
            ["t_close", "t_look"],
            " ",
            model_heads=[s[0] for s in specs],
            head_order="h",
            show_fe=False,
        )
    return fits


def _photo_fit(d, outcome, post, trend=False):
    d = d.copy()
    d["post"] = post.astype(float)
    regs = ["t_close", "t_look"]
    for k in ["t_close", "t_look"]:
        d[f"{k}_post"] = d[k] * d["post"]
        regs.append(f"{k}_post")
        if trend:
            d[f"{k}_trend"] = d[k] * (d["year_frac"] - PHOTO_YEAR) / 10
            regs.append(f"{k}_trend")
    return _fit(d, outcome, regs + ["log_name_freq"])


def photo_table(d):
    """Table 3: does the 2015 break survive a trend and a narrower window?"""
    window = d[(d.Year >= 2005) & (d.Year <= 2019)]
    fits = []
    for out in ["rank_pct", "log_votes"]:
        fits += [
            _photo_fit(d, out, d.post2015),
            _photo_fit(d, out, d.post2015, trend=True),
            _photo_fit(window, out, window.post2015),
        ]
    keep = ["t_close", "t_close_post", "t_close_trend"]
    keep += ["t_look", "t_look_post", "t_look_trend"]
    _etable(
        "photo_rule.tex",
        fits,
        keep,
        "Sample as in Table 1. Trend terms are in decades from 1 May 2015. "
        "Standard errors clustered by constituency in parentheses.",
        model_heads=["1962-2026", "+ trend", "2005-2019"] * 2,
    )
    return fits


def placebo_breaks(d):
    """Close-name x after-break estimate for each candidate break date."""
    rows = []
    for year in PLACEBO_BREAKS:
        for out in ["rank_pct", "log_votes"]:
            fit = _photo_fit(d, out, d["year_frac"] >= year)
            rows.append(
                {
                    "break": year,
                    "outcome": out,
                    "estimate": fit.coef()["t_close_post"],
                    "se": fit.se()["t_close_post"],
                    "t": fit.tstat()["t_close_post"],
                }
            )
    return pd.DataFrame(rows)


def event_study(d):
    d = d.copy()
    d["period"] = d["ym"].map(period_bin)
    cols = []
    for key, _ in PERIODS:
        d[key] = d["t_close"] * (d["period"] == key)
        cols.append(key)
    return {
        out: _fit(d, out, cols + ["t_look", "log_name_freq"])
        for out in ["rank_pct", "log_votes"]
    }


def plot_photo(es_fits, breaks):
    plotstyle.apply()
    fig, axes = plt.subplots(2, 2, figsize=(9.0, 6.4))
    x = np.arange(len(PERIODS))
    units = {"rank_pct": "Percentile points", "log_votes": "Log points"}
    for col, out in enumerate(["rank_pct", "log_votes"]):
        fit = es_fits[out]
        est = np.array([fit.coef()[k] for k, _ in PERIODS])
        se = np.array([fit.se()[k] for k, _ in PERIODS])
        ax = axes[0, col]
        ax.axhline(0, color="0.4", lw=0.8)
        ax.axvline(4.5, color=plotstyle.RULE, lw=1)
        plotstyle.interval_bars(ax, x, est, se)
        ax.set_xticks(x)
        ax.set_xticklabels([lbl for _, lbl in PERIODS], fontsize=8, rotation=30)
        ax.set_ylabel(units[out])
        plotstyle.tidy(ax, f"Premium by period: {OUTCOMES[out].lower()}")
        ax.text(4.6, ax.get_ylim()[1], "photos on\nEVMs, 2015", color=plotstyle.RULE,
                va="top", fontsize=8.5)  # fmt: skip

        b = breaks[breaks.outcome == out].sort_values("break")
        real = np.isclose(b["break"], PHOTO_YEAR)
        ax = axes[1, col]
        ax.axhline(0, color="0.4", lw=0.8)
        low, high = b.estimate - 1.96 * b.se, b.estimate + 1.96 * b.se
        ax.fill_between(b["break"], low, high, color=plotstyle.BAND, lw=0)
        ax.plot(b["break"], b.estimate, color="black", lw=1.2)
        ax.scatter(b["break"][~real], b.estimate[~real], color=plotstyle.DOT, s=14,
                   zorder=3)  # fmt: skip
        ax.scatter(b["break"][real], b.estimate[real], color=plotstyle.RULE, s=30,
                   zorder=4)  # fmt: skip
        ax.annotate("May 2015", (PHOTO_YEAR, float(b.estimate[real].iloc[0])),
                    xytext=(-6, -14), textcoords="offset points", ha="right",
                    color=plotstyle.RULE, fontsize=8.5)  # fmt: skip
        ax.set_xlabel("Break date")
        ax.set_ylabel(units[out])
        plotstyle.tidy(ax, "Change after each break date")
    fig.tight_layout()
    fig.savefig(FIGS / "photo_rule.png", dpi=220)
    plt.close(fig)


def overturn_table(usable, ind, conf_fits):
    """Table 4: could the runner-up's namesakes have cost them the seat?

    A runner-up's independent namesake's diverted votes are its votes times
    1 - exp(-b) for its tier's log premium b (point estimate and 95% bounds).
    """
    winners = usable[usable.Position == 1].drop_duplicates("row_id")
    runners = usable[usable.Position == 2].drop_duplicates("row_id")
    winners, runners = winners.set_index("row_id"), runners.set_index("row_id")
    margin = winners["Votes"] - runners["Votes"].reindex(winners.index)
    margin = margin[runners["Party"].reindex(winners.index) != "IND"].dropna()

    log_fit = conf_fits["log_votes"]
    bounds = {
        "point": log_fit.coef(),
        "low": log_fit.coef() - 1.96 * log_fit.se(),
        "high": log_fit.coef() + 1.96 * log_fit.se(),
    }
    nm = _tiers(ind[ind.row_id.isin(margin.index)].copy(), "like_runner_up")
    nm["tier"] = np.select(
        [nm["t_exact"] == 1, nm["t_init"] == 1, nm["t_look"] == 1],
        ["t_exact", "t_init", "t_look"],
        default="",
    )
    nm = nm[nm.tier != ""]
    groups = [
        ("Exact / spelling", ["t_exact"]),
        ("Close name (adds initials)", ["t_exact", "t_init"]),
        ("Any look-alike", ["t_exact", "t_init", "t_look"]),
    ]
    rows = []
    for label, tiers in groups:
        g = nm[nm.tier.isin(tiers)]
        votes = g.groupby("row_id").Votes.sum()
        r = {"label": label, "contests": len(votes)}
        r["bound"] = int((votes > margin.reindex(votes.index)).sum())
        for tag, coef in bounds.items():
            share = diverted_share([coef[t] for t in g.tier])
            div = (g.Votes.astype(float) * share).groupby(g.row_id).sum()
            r[tag] = int((div > margin.reindex(div.index)).sum())
        rows.append(r)

    third = usable[(usable.Position == 3) & usable.row_id.isin(margin.index)]
    third = third.drop_duplicates("row_id").set_index("row_id").Votes
    third_over = float((third > margin.reindex(third.index)).mean())

    spanner = "Namesake votes exceed the margin"
    table = pd.DataFrame(
        {
            ("", "Runner-up has one"): [f"{r['contests']:,}" for r in rows],
            (spanner, "All votes (bound)"): [f"{r['bound']:,}" for r in rows],
            (spanner, "Votes owed to name"): [f"{r['point']:,}" for r in rows],
            (spanner, r"95\% range"): [f"{r['low']:,}-{r['high']:,}" for r in rows],
        },
        index=[r["label"] for r in rows],
    )
    table.columns = pd.MultiIndex.from_tuples(table.columns)
    notes = (
        f"Counts of contests among {len(margin):,} general-election contests "
        "with a party runner-up. Votes owed to the name: each runner-up "
        "namesake's votes times 1 - exp(-b), b its tier's log premium in "
        "Table 1 (95\\% range from b's confidence interval)."
    )
    (TABS / "overturn.tex").write_text(mt.MTable(table, notes=notes).make("tex"))
    return rows, len(margin), third_over


def bihar_table(source):
    """Table 5: Bihar panchayats, candidates ranked below second place."""
    candidates = load_local(source)
    local_pairs = pd.read_parquet("data/release/name_pairs.parquet")
    people = contests_with_votes(candidates)
    people = people[people["state"] == "Bihar"].copy()
    people["like_winner"] = resemblance_to(people, local_pairs, "is_winner")
    people["place"] = people.groupby("row_id")["votes"].rank(
        ascending=False, method="first"
    )
    people["log_votes"] = np.log1p(people["votes"])
    freq = people["name_spelling"].value_counts()
    people["log_name_freq"] = np.log1p(people["name_spelling"].map(freq))
    d = people[people["place"] > 2].copy()
    d = d[d.groupby("row_id").row_id.transform("size") >= 2].copy()
    d["rank_pct"] = rank_pct(d["votes"], d["row_id"])
    d["Votes"] = d["votes"]
    d["constituency"] = d["row_id"]
    d["b_same"] = d["like_winner"].isin(["same name", "alias"]).astype(float)
    d["b_contained"] = (d["like_winner"] == "contained").astype(float)
    d["b_sim8"] = (d["like_winner"] == "similarity 0.8+").astype(float)
    d["b_sim6"] = (d["like_winner"] == "similarity 0.6-0.8").astype(float)
    regs = ["b_same", "b_contained", "b_sim8", "b_sim6", "log_name_freq"]
    fits = {o: _fit(d, o, regs, poisson=o == "Votes") for o in OUTCOMES}
    _etable(
        "bihar.tex",
        list(fits.values()),
        regs[:4],
        "Bihar panchayat candidates (2016, 2021, all six offices) placed third "
        "or lower, in contests with complete vote counts and at least two "
        "such candidates. Resemblance is to the contest's winner. All models "
        "control for log name frequency. Standard errors clustered by contest.",
        custom_model_stats={"Contests": [f"{d.row_id.nunique():,}"] * 3},
    )
    return fits, len(d), d.row_id.nunique()


def write_macros(usable, ind, d, conf, targets, photo, breaks, overturn, bihar):
    pr = pd.read_csv("data/release/tcpd/pair_rates.csv")
    pr = pr[pr["level"] == "exact"].set_index(["election", "pair"])["per_10000"]
    rows, n_margin, third_over = overturn
    b_fits, n_bihar, n_bihar_contests = bihar
    lg, rk, po = conf["log_votes"], conf["rank_pct"], conf["Votes"]
    es = conf["es"]["log_votes"]
    real = breaks[np.isclose(breaks["break"], PHOTO_YEAR)].set_index("outcome")
    fake = breaks[~np.isclose(breaks["break"], PHOTO_YEAR)]
    fake_log = fake[fake.outcome == "log_votes"]
    exact, look = rows[0], rows[2]
    leader = ind.like_leader != "unlike"
    maha = usable[
        (usable.election == "lok_sabha")
        & (usable.Year == 2014)
        & (usable.Constituency_Name.astype(str).str.upper() == "MAHASAMUND")
    ]
    maha_top = maha.sort_values("Position").Votes.to_numpy()
    maha_ns = ind[
        ind.row_id.isin(maha.row_id)
        & ind.like_winner.isin(["exact", "spelling", "alias"])
    ]

    def est(fit, key, digits=2):
        return f"{fit.coef()[key]:+.{digits}f}"

    def se(fit, key, digits=2):
        return f"{fit.se()[key]:.{digits}f}"

    def pct_more(fit, key):
        return f"{100 * (np.exp(fit.coef()[key]) - 1):.0f}"

    def ratio(election):
        lm = pr.loc[(election, "leader-minor")]
        mm = pr.loc[(election, "minor-minor")]
        return f"{lm:.1f}", f"{mm:.1f}", f"{lm / mm:.1f}"

    ls, ae = ratio("lok_sabha"), ratio("assembly")
    check = usable[usable["Year"].between(2014, 2023) & usable["Incumbent"].notna()]
    tcpd_inc = check["Incumbent"].astype(str).eq("True")
    ours = check["is_incumbent"]
    late = d["Year"] >= 2024
    macros = {
        "incAgree": f"{100 * (ours == tcpd_inc).mean():.1f}",
        "incRecall": f"{100 * ours[tcpd_inc].mean():.0f}",
        "incPrecision": f"{100 * tcpd_inc[ours].mean():.0f}",
        "nExanteLate": f"{int(((d.like_exante != 'unlike') & late).sum()):,}",
        "nLeaderLate": f"{int(((d.like_leader != 'unlike') & late).sum()):,}",
        "nTcpdCand": f"{len(usable):,}",
        "mahaMargin": f"{maha_top[0] - maha_top[1]:,.0f}",
        "mahaN": f"{len(maha_ns)}",
        "mahaVotes": f"{maha_ns.Votes.sum():,.0f}",
        "nInd": f"{len(d):,}",
        "nIndContests": f"{d.row_id.nunique():,}",
        "nTreated": f"{int((d.like_leader != 'unlike').sum()):,}",
        "nTreatedAll": f"{int(leader.sum()):,}",
        "nTreatedTopTwo": f"{int((leader & (ind.Position <= 2)).sum()):,}",
        "medIndShare": f"{(100 * d.Votes / d.Valid_Votes).median():.2f}",
        "medNamesakeVotes": f"{d.Votes[d.like_leader != 'unlike'].median():,.0f}",
        "lsLeaderExact": ls[0],
        "lsMinorExact": ls[1],
        "lsLeaderRatio": ls[2],
        "aeLeaderExact": ae[0],
        "aeMinorExact": ae[1],
        "aeLeaderRatio": ae[2],
        "rkExact": est(rk, "t_exact", 1),
        "rkExactSe": se(rk, "t_exact", 1),
        "rkInit": est(rk, "t_init", 1),
        "rkInitSe": se(rk, "t_init", 1),
        "rkLook": est(rk, "t_look", 1),
        "rkLookSe": se(rk, "t_look", 1),
        "rkPlExact": est(rk, "m_exact", 1),
        "rkPlExactSe": se(rk, "m_exact", 1),
        "rkPlLook": est(rk, "m_look", 1),
        "rkPlLookSe": se(rk, "m_look", 1),
        "lgExact": est(lg, "t_exact"),
        "lgExactSe": se(lg, "t_exact"),
        "lgExactPct": pct_more(lg, "t_exact"),
        "lgInit": est(lg, "t_init"),
        "lgInitSe": se(lg, "t_init"),
        "lgInitPct": pct_more(lg, "t_init"),
        "lgPlExact": est(lg, "m_exact"),
        "lgPlExactSe": se(lg, "m_exact"),
        "poExact": est(po, "t_exact"),
        "poExactSe": se(po, "t_exact"),
        "poInit": est(po, "t_init"),
        "poInitSe": se(po, "t_init"),
        "poLook": est(po, "t_look"),
        "poLookSe": se(po, "t_look"),
        "divExact": f"{100 * float(diverted_share(lg.coef()['t_exact'])):.0f}",
        "divInit": f"{100 * float(diverted_share(lg.coef()['t_init'])):.0f}",
        "tgWinRk": est(targets[1]["rank_pct"], "t_close", 1),
        "tgWinRkSe": se(targets[1]["rank_pct"], "t_close", 1),
        "tgExRk": est(targets[2]["rank_pct"], "t_close", 1),
        "tgExRkSe": se(targets[2]["rank_pct"], "t_close", 1),
        "tgAllRk": est(targets[3]["rank_pct"], "t_close", 1),
        "tgAllRkSe": se(targets[3]["rank_pct"], "t_close", 1),
        "tgAllPo": est(targets[3]["Votes"], "t_close"),
        "tgAllPoSe": se(targets[3]["Votes"], "t_close"),
        "tgLsLg": est(targets[4]["log_votes"], "t_close"),
        "tgLsLgSe": se(targets[4]["log_votes"], "t_close"),
        "tgAeLg": est(targets[5]["log_votes"], "t_close"),
        "tgAeLgSe": se(targets[5]["log_votes"], "t_close"),
        "phRkPost": est(photo[0], "t_close_post", 1),
        "phRkPostSe": se(photo[0], "t_close_post", 1),
        "phRkTrendPost": est(photo[1], "t_close_post", 1),
        "phRkTrendPostSe": se(photo[1], "t_close_post", 1),
        "phLgPost": est(photo[3], "t_close_post"),
        "phLgPostSe": se(photo[3], "t_close_post"),
        "phLgTrendPost": est(photo[4], "t_close_post"),
        "phLgTrendPostSe": se(photo[4], "t_close_post"),
        "phLgWin": est(photo[5], "t_close_post"),
        "phLgWinSe": se(photo[5], "t_close_post"),
        "brRealT": f"{real.loc['log_votes', 't']:.1f}",
        "brFakeMinT": f"{fake_log.t.min():.1f}",
        "brFakeMinYear": f"{int(fake_log.loc[fake_log.t.idxmin(), 'break'])}",
        "brFakeSig": f"{int((fake_log.t.abs() > 1.96).sum())}",
        "brFakeN": f"{len(fake_log)}",
        "esLate": est(es, "p2010_Apr2015"),
        "esPost": est(es, "pMay2015_2019"),
        "esEarly": est(es, "p2000_2004"),
        "esMid": est(es, "p2005_2009"),
        "esFirst": est(es, "p1962_1989"),
        "esNineties": est(es, "p1990_1999"),
        "esLast": est(es, "p2020_2026"),
        "nMarginContests": f"{n_margin:,}",
        "ovExactHas": f"{exact['contests']:,}",
        "ovExactBound": f"{exact['bound']:,}",
        "ovExactPoint": f"{exact['point']:,}",
        "ovExactLow": f"{exact['low']:,}",
        "ovExactHigh": f"{exact['high']:,}",
        "ovLookHas": f"{look['contests']:,}",
        "ovLookBound": f"{look['bound']:,}",
        "ovLookPoint": f"{look['point']:,}",
        "ovLookLow": f"{look['low']:,}",
        "ovLookHigh": f"{look['high']:,}",
        "ovLookPointPct": f"{100 * look['point'] / n_margin:.2f}",
        "thirdOver": f"{100 * third_over:.0f}",
        "nBiharCand": f"{n_bihar:,}",
        "nBiharContests": f"{n_bihar_contests:,}",
        "bhRk": est(b_fits["rank_pct"], "b_same", 1),
        "bhRkSe": se(b_fits["rank_pct"], "b_same", 1),
        "bhLg": est(b_fits["log_votes"], "b_same"),
        "bhLgSe": se(b_fits["log_votes"], "b_same"),
        "bhPo": est(b_fits["Votes"], "b_same"),
        "bhPoSe": se(b_fits["Votes"], "b_same"),
    }
    lines = [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in macros.items()]
    (TABS / "macros.tex").write_text("\n".join(lines) + "\n")


def main():
    TABS.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)
    source = json.loads(Path("data/source.json").read_text())
    usable, ind = _prepare_tcpd(source)
    d = _sample(ind[ind.Position > 2])
    conf, d = confusion_table(d)
    targets = targets_table(d, ind)
    photo = photo_table(d)
    breaks = placebo_breaks(d)
    conf["es"] = event_study(d)
    plot_photo(conf["es"], breaks)
    overturn = overturn_table(usable, ind, conf)
    bihar = bihar_table(source)
    write_macros(usable, ind, d, conf, targets, photo, breaks, overturn, bihar)
    print(breaks.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
