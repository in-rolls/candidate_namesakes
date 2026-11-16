"""Econometric analysis of namesake vote stealing in Indian elections.

Estimates within-contest vote-share and log-vote differentials for minor
independent (IND) candidates whose names resemble leading party candidates,
exploiting the 1 May 2015 ECI rule placing candidate photographs on EVMs
(PHOTO_RULE = 201505) as a difference-in-differences shock. Also checks
Bihar local elections (2016, 2021) among candidates ranked below second place.

Writes LaTeX tables and macros to ``tabs/`` and figures to ``figs/``.

    python -m candidate_namesakes.econometrics
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

from candidate_namesakes.check_votes import contests_with_votes, resemblance_to
from candidate_namesakes.count_namesakes import load as load_local
from candidate_namesakes.tcpd import PHOTO_RULE, read_tcpd

TABS = Path("tabs")
FIGS = Path("figs")

TIER_ORDER = {"exact": 0, "spelling": 1, "alias": 2, "initials": 3, "lookalike": 4}
PERIODS = [
    ("1962-1989", "1962\u201389"),
    ("1990-1999", "1990\u201399"),
    ("2000-2004", "2000\u201304"),
    ("2005-2009", "2005\u201309"),
    ("2010-Apr2015", "2010\u2013Apr 15"),
    ("May2015-2019", "May 15\u201319"),
    ("2020-2026", "2020\u201326"),
]


def _period_bin(ym):
    year = ym // 100
    if year < 1990:
        return "1962-1989"
    if year < 2000:
        return "1990-1999"
    if year < 2005:
        return "2000-2004"
    if year < 2010:
        return "2005-2009"
    if ym < PHOTO_RULE:
        return "2010-Apr2015"
    if year < 2020:
        return "May2015-2019"
    return "2020-2026"


def _within_ols(df, outcome, regressors):
    """Within-contest OLS with standard errors clustered by contest (row_id)."""
    counts = df.groupby("row_id").size()
    sub = df[df["row_id"].isin(counts[counts >= 2].index)].copy()
    keep = [outcome] + regressors
    demeaned = sub[keep] - sub.groupby("row_id")[keep].transform("mean")
    groups = pd.factorize(sub["row_id"])[0]
    fit = sm.OLS(demeaned[outcome], demeaned[regressors]).fit(
        cov_type="cluster", cov_kwds={"groups": groups}
    )
    return fit, len(sub), int(sub["row_id"].nunique())


def _fit_did(df, match_col, outcome):
    """Fit pre/post-2015 within-contest DiD for a match column."""
    d = df.copy()
    d["is_exact_spell"] = (
        d[match_col].isin(["exact", "spelling", "alias"]).astype(float)
    )
    d["is_initials"] = (d[match_col] == "initials").astype(float)
    d["is_lookalike"] = (d[match_col] == "lookalike").astype(float)
    base = ["is_exact_spell", "is_initials", "is_lookalike"]
    cols = list(base)
    for col in base:
        d[f"{col}_post"] = d[col] * d["post2015"]
        cols.append(f"{col}_post")
    cols.append("log_name_freq")
    fit, n_obs, n_contests = _within_ols(d, outcome, cols)
    return fit, n_obs, n_contests


def _prepare_tcpd(source):
    tcpd = read_tcpd(source)
    pairs = pd.read_parquet("data/release/tcpd/name_pairs.parquet")
    usable = tcpd[
        (tcpd.Poll_No == 0)
        & (~tcpd.names_abbreviated)
        & (tcpd.Valid_Votes > 0)
        & tcpd.Votes.notna()
    ].copy()
    usable["vote_share_pct"] = 100.0 * usable["Votes"] / usable["Valid_Votes"]
    usable["log_votes"] = np.log1p(usable["Votes"])
    usable["ym"] = usable["Year"] * 100 + usable["month"].fillna(0)
    usable["post2015"] = (usable["ym"] >= PHOTO_RULE).astype(int)
    freq = usable["name_spelling"].value_counts()
    usable["log_name_freq"] = np.log1p(usable["name_spelling"].map(freq).fillna(0))
    last_pos = usable.groupby("row_id")["Position"].transform("max")
    usable["is_last"] = usable["Position"] == last_pos

    pairs = pairs[pairs.row_id.isin(usable.row_id.unique())].dropna(subset=["level"])
    pairs = pairs.assign(rank=pairs["level"].map(TIER_ORDER))
    p_sym = pd.concat(
        [
            pairs[
                ["row_id", "candidate_id_a", "candidate_id_b", "level", "rank"]
            ].rename(
                columns={"candidate_id_a": "ind_id", "candidate_id_b": "target_id"}
            ),
            pairs[
                ["row_id", "candidate_id_b", "candidate_id_a", "level", "rank"]
            ].rename(
                columns={"candidate_id_b": "ind_id", "candidate_id_a": "target_id"}
            ),
        ],
        ignore_index=True,
    )
    info = usable.set_index("candidate_id")[["Party", "Position"]]
    p_sym["target_party"] = p_sym["target_id"].map(info["Party"])
    p_sym["target_pos"] = p_sym["target_id"].map(info["Position"])

    ind = usable[usable["Party"] == "IND"].copy()
    last_ids = set(usable.loc[usable["is_last"], "candidate_id"])

    def attach(mask, col):
        sub = p_sym[mask].sort_values("rank").drop_duplicates("ind_id")
        ind[col] = (
            ind["candidate_id"].map(sub.set_index("ind_id")["level"]).fillna("unlike")
        )

    attach((p_sym["target_pos"] == 1) & (p_sym["target_party"] != "IND"), "like_winner")
    attach((p_sym["target_pos"] <= 2) & (p_sym["target_party"] != "IND"), "like_leader")
    attach(
        p_sym["target_id"].isin(last_ids) & (p_sym["ind_id"] != p_sym["target_id"]),
        "like_last",
    )
    return usable, ind


def _fmt_cell(fit, key, digits=2):
    est = fit.params[key]
    se = fit.bse[key]
    return f"${est:+.{digits}f}$ ({se:.{digits}f})"


def write_tcpd_did_table(ind_minor):
    """Write Table 1: Main TCPD/ECI DiD estimates."""
    mid = ind_minor[~ind_minor["is_last"]].copy()
    specs = [
        ("Winner", ind_minor, "like_winner", "vote_share_pct"),
        ("Top-2", ind_minor, "like_leader", "vote_share_pct"),
        ("Placebo", mid, "like_last", "vote_share_pct"),
        ("Winner", ind_minor, "like_winner", "log_votes"),
        ("Top-2", ind_minor, "like_leader", "log_votes"),
        ("Placebo", mid, "like_last", "log_votes"),
    ]
    fits = [_fit_did(df, col, out) for _, df, col, out in specs]
    terms = [
        ("is_exact_spell", "Exact / Spelling"),
        ("is_initials", "Initials differ"),
        ("is_lookalike", "Look-alike"),
        ("is_exact_spell_post", "Exact / Spelling $\\times$ Post-2015"),
        ("is_initials_post", "Initials differ $\\times$ Post-2015"),
        ("is_lookalike_post", "Look-alike $\\times$ Post-2015"),
        ("log_name_freq", "Log name frequency"),
    ]
    lines = [
        r"\begin{tabular}{lcccccc}",
        r"\toprule",
        (
            r" & \multicolumn{3}{c}{Vote Share (pct.\ pts.)}"
            r" & \multicolumn{3}{c}{Log(1 + Votes)} \\"
        ),
        r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}",
        r" & Winner & Top-2 & Placebo & Winner & Top-2 & Placebo \\",
        r"\midrule",
    ]
    for key, label in terms:
        vals = " & ".join(_fmt_cell(fit, key) for fit, _, _ in fits)
        lines.append(f"{label} & {vals} \\\\")
    lines.append(r"\midrule")
    obs = " & ".join(f"{n:,}" for _, n, _ in fits)
    cts = " & ".join(f"{c:,}" for _, _, c in fits)
    lines.append(f"Candidates & {obs} \\\\")
    lines.append(f"Contests (FE) & {cts} \\\\")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    (TABS / "tcpd_did.tex").write_text("\n".join(lines) + "\n")
    return fits


def write_heterogeneity_table(ind_minor):
    """Write Table 2: Lok Sabha vs State Assembly."""
    ls = ind_minor[ind_minor["election"] == "lok_sabha"]
    ae = ind_minor[ind_minor["election"] == "assembly"]
    specs = [
        (ls, "like_leader", "vote_share_pct"),
        (ae, "like_leader", "vote_share_pct"),
        (ls, "like_leader", "log_votes"),
        (ae, "like_leader", "log_votes"),
    ]
    fits = [_fit_did(df, col, out) for df, col, out in specs]
    terms = [
        ("is_exact_spell", "Exact / Spelling"),
        ("is_initials", "Initials differ"),
        ("is_lookalike", "Look-alike"),
        ("is_exact_spell_post", "Exact / Spelling $\\times$ Post-2015"),
        ("is_initials_post", "Initials differ $\\times$ Post-2015"),
        ("is_lookalike_post", "Look-alike $\\times$ Post-2015"),
    ]
    lines = [
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        (
            r" & \multicolumn{2}{c}{Vote Share (pct.\ pts.)}"
            r" & \multicolumn{2}{c}{Log(1 + Votes)} \\"
        ),
        r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}",
        r" & Lok Sabha & Assembly & Lok Sabha & Assembly \\",
        r"\midrule",
    ]
    for key, label in terms:
        vals = " & ".join(_fmt_cell(fit, key) for fit, _, _ in fits)
        lines.append(f"{label} & {vals} \\\\")
    lines.append(r"\midrule")
    obs = " & ".join(f"{n:,}" for _, n, _ in fits)
    cts = " & ".join(f"{c:,}" for _, _, c in fits)
    lines.append(f"Candidates & {obs} \\\\")
    lines.append(f"Contests (FE) & {cts} \\\\")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    (TABS / "tcpd_heterogeneity.tex").write_text("\n".join(lines) + "\n")
    return fits


def write_bihar_table(source):
    """Write Table 3: Bihar local elections (rank > 2)."""
    candidates = load_local(source)
    local_pairs = pd.read_parquet("data/release/name_pairs.parquet")
    people = contests_with_votes(candidates)
    people["like_winner"] = resemblance_to(people, local_pairs, "is_winner")
    people["like_last"] = resemblance_to(people, local_pairs, "is_last")
    people["rank"] = people.groupby("row_id")["votes"].rank(
        ascending=False, method="first"
    )
    people["log_votes"] = np.log1p(people["votes"])
    freq = people["name_spelling"].value_counts()
    people["log_name_freq"] = np.log1p(people["name_spelling"].map(freq).fillna(0))

    bihar = people[(people["state"] == "Bihar") & (people["rank"] > 2)].copy()
    mid = bihar[~bihar["is_last"]].copy()

    def fit_bihar(df, col, out):
        f = df.copy()
        f["is_same"] = f[col].isin(["same name", "alias"]).astype(float)
        f["is_contained"] = (f[col] == "contained").astype(float)
        f["is_sim8"] = (f[col] == "similarity 0.8+").astype(float)
        f["is_sim6"] = (f[col] == "similarity 0.6-0.8").astype(float)
        cols = ["is_same", "is_contained", "is_sim8", "is_sim6", "log_name_freq"]
        return _within_ols(f, out, cols)

    fits = [
        fit_bihar(bihar, "like_winner", "vote_share_pct"),
        fit_bihar(mid, "like_last", "vote_share_pct"),
        fit_bihar(bihar, "like_winner", "log_votes"),
        fit_bihar(mid, "like_last", "log_votes"),
    ]
    terms = [
        ("is_same", "Same name / alias"),
        ("is_contained", "Contained"),
        ("is_sim8", "Similarity 0.8+"),
        ("is_sim6", "Similarity 0.6--0.8"),
        ("log_name_freq", "Log name frequency"),
    ]
    lines = [
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        (
            r" & \multicolumn{2}{c}{Vote Share (pct.\ pts.)}"
            r" & \multicolumn{2}{c}{Log(1 + Votes)} \\"
        ),
        r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}",
        r" & Winner & Placebo & Winner & Placebo \\",
        r"\midrule",
    ]
    for key, label in terms:
        vals = " & ".join(_fmt_cell(fit, key) for fit, _, _ in fits)
        lines.append(f"{label} & {vals} \\\\")
    lines.append(r"\midrule")
    obs = " & ".join(f"{n:,}" for _, n, _ in fits)
    cts = " & ".join(f"{c:,}" for _, _, c in fits)
    lines.append(f"Candidates & {obs} \\\\")
    lines.append(f"Contests (FE) & {cts} \\\\")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    (TABS / "bihar_robustness.tex").write_text("\n".join(lines) + "\n")
    return fits


def write_margin_flips_table():
    """Write Table 4: Contests where runner-up namesake votes exceed the margin."""
    contests = pd.read_parquet("data/release/tcpd/contests.parquet")
    uc = contests[
        (~contests.by_election)
        & (~contests.names_abbreviated)
        & (contests.margin.notna())
    ]
    tiers = [
        ("exact", "Exact"),
        ("spelling", "Spelling"),
        ("initials", "Initials differ"),
        ("lookalike", "Look-alike"),
    ]
    subsets = [
        ("Lok Sabha", uc[uc.election == "lok_sabha"]),
        ("Assembly", uc[uc.election == "assembly"]),
        ("Combined", uc),
    ]
    lines = [
        r"\begin{tabular}{lccc}",
        r"\toprule",
        r"Match tier & Lok Sabha & Assembly & Combined \\",
        r"\midrule",
    ]
    for key, label in tiers:
        col = f"runner_up_namesake_votes_{key}"
        cells = []
        for _, sub in subsets:
            has = int((sub[col] > 0).sum())
            flips = int((sub[col] > sub["margin"]).sum())
            pct = 100.0 * flips / has if has else 0.0
            cells.append(f"{flips:,} / {has:,} ({pct:.1f}\\%)")
        lines.append(f"{label} & " + " & ".join(cells) + r" \\")
    lines.append(r"\midrule")
    counts = " & ".join(f"{len(sub):,}" for _, sub in subsets)
    lines.append(f"All contests & {counts} \\\\")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    (TABS / "margin_flips.tex").write_text("\n".join(lines) + "\n")


def plot_event_study(ind_minor):
    """Plot event study of close-name premium in log(1 + Votes) across periods."""
    d = ind_minor.copy()
    d["is_close"] = (
        d["like_leader"].isin(["exact", "spelling", "alias", "initials"]).astype(float)
    )
    d["period"] = d["ym"].map(_period_bin)
    cols = []
    for key, _ in PERIODS:
        col = f"close_{key}"
        d[col] = d["is_close"] * (d["period"] == key).astype(float)
        cols.append(col)
    cols.append("log_name_freq")
    fit, _, _ = _within_ols(d, "log_votes", cols)

    ests = [fit.params[f"close_{k}"] for k, _ in PERIODS]
    ses = [fit.bse[f"close_{k}"] for k, _ in PERIODS]
    labels = [lbl for _, lbl in PERIODS]

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    x = np.arange(len(PERIODS))
    ax.axhline(0, color="#666666", linewidth=0.8, linestyle="-")
    ax.axvline(4.5, color="#b22222", linewidth=1.2, linestyle="--")
    ax.errorbar(
        x,
        ests,
        yerr=1.96 * np.array(ses),
        fmt="o-",
        color="#1f4e79",
        ecolor="#1f4e79",
        elinewidth=1.5,
        capsize=3,
        markersize=6,
    )
    ax.text(
        4.58,
        0.43,
        "May 2015\nEVM photo rule",
        color="#b22222",
        fontsize=9,
        va="top",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Log(1 + votes) differential", fontsize=10)
    ax.set_title(
        "Close-name differential for minor independents, 1962–2026",
        fontsize=11,
        pad=10,
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIGS / "event_study.png", dpi=220)
    plt.close(fig)
    return fit


def plot_did_coef(fits_did):
    """Plot Pre-2015 vs Post-2015 DiD shift in log(1 + Votes) across targets."""
    # fits_did[3]: Winner log_votes, fits_did[4]: Top-2 log_votes, fits_did[5]: Placebo
    targets = [
        ("Eventual winner", fits_did[3][0], "#1f4e79"),
        ("Top-2 leader", fits_did[4][0], "#2e7d32"),
        ("Last-placed (placebo)", fits_did[5][0], "#888888"),
    ]
    tiers = [
        ("is_exact_spell", "Exact / Spelling"),
        ("is_initials", "Initials differ"),
        ("is_lookalike", "Look-alike"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.6), sharey=True)
    y_base = np.arange(len(tiers))[::-1]
    offsets = [0.18, 0.0, -0.18]

    for panel_idx, (title, suffix) in enumerate(
        [("Pre-2015 baseline", ""), ("Post-2015 change (DiD)", "_post")]
    ):
        ax = axes[panel_idx]
        ax.axvline(0, color="#666666", linewidth=0.8)
        for (label, fit, color), off in zip(targets, offsets):
            ests = [fit.params[k + suffix] for k, _ in tiers]
            ses = [fit.bse[k + suffix] for k, _ in tiers]
            ax.errorbar(
                ests,
                y_base + off,
                xerr=1.96 * np.array(ses),
                fmt="o",
                color=color,
                label=label if panel_idx == 0 else None,
                capsize=3,
                markersize=5.5,
            )
        ax.set_title(title, fontsize=10.5)
        ax.set_xlabel("Log(1 + votes) differential", fontsize=9.5)
        ax.set_xlim(-0.75, 0.55)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    axes[0].set_yticks(y_base)
    axes[0].set_yticklabels([lbl for _, lbl in tiers], fontsize=9.5)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=3,
        frameon=False,
        fontsize=9,
        bbox_to_anchor=(0.54, 1.0),
    )
    fig.tight_layout(rect=[0, 0, 1, 0.91])
    fig.savefig(FIGS / "did_coef.png", dpi=220)
    plt.close(fig)


def write_style_and_macros(usable, ind_minor, fits_did, fits_het, fits_bihar, es_fit):
    """Write tabs/style.tex and tabs/macros.tex with all manuscript numbers."""
    (TABS / "style.tex").write_text(
        "\\newcommand{\\TableStyle}{\\small\\setlength{\\tabcolsep}{5pt}}\n"
    )
    contests_tcpd = pd.read_parquet("data/release/tcpd/contests.parquet")
    pr = pd.read_csv("data/release/tcpd/pair_rates.csv")
    pr_exact = pr[pr["level"] == "exact"].set_index(["election", "pair"])["per_10000"]
    ls_lm = float(pr_exact.loc[("lok_sabha", "leader-minor")])
    ls_mm = float(pr_exact.loc[("lok_sabha", "minor-minor")])
    ae_lm = float(pr_exact.loc[("assembly", "leader-minor")])
    ae_mm = float(pr_exact.loc[("assembly", "minor-minor")])
    uc = contests_tcpd[
        (~contests_tcpd.by_election)
        & (~contests_tcpd.names_abbreviated)
        & (contests_tcpd.margin.notna())
    ]
    n_contests_all = len(uc)
    flip_exact = int((uc["runner_up_namesake_votes_exact"] > uc["margin"]).sum())
    has_exact = int((uc["runner_up_namesake_votes_exact"] > 0).sum())
    flip_look = int((uc["runner_up_namesake_votes_lookalike"] > uc["margin"]).sum())
    has_look = int((uc["runner_up_namesake_votes_lookalike"] > 0).sum())

    w_vs, t2_vs, p_vs, w_lv, t2_lv, p_lv = [f[0] for f in fits_did]
    ls_vs, ae_vs, ls_lv, ae_lv = [f[0] for f in fits_het]
    b_vs, bp_vs, b_lv, bp_lv = [f[0] for f in fits_bihar]

    macros = {
        "nTcpdCand": f"{len(usable):,}",
        "nIndMinor": f"{fits_did[0][1]:,}",
        "nIndContests": f"{fits_did[0][2]:,}",
        "medIndShare": f"{ind_minor['vote_share_pct'].median():.2f}",
        "nBiharCand": f"{fits_bihar[0][1]:,}",
        "nBiharContests": f"{fits_bihar[0][2]:,}",
        "nAllContestsMargin": f"{n_contests_all:,}",
        "flipExact": f"{flip_exact:,}",
        "hasExact": f"{has_exact:,}",
        "pctFlipExact": f"{100 * flip_exact / has_exact:.1f}",
        "flipLook": f"{flip_look:,}",
        "hasLook": f"{has_look:,}",
        "pctFlipLook": f"{100 * flip_look / has_look:.1f}",
        "wLogExact": f"{w_lv.params['is_exact_spell']:+.2f}",
        "wLogExactSe": f"{w_lv.bse['is_exact_spell']:.2f}",
        "wPctExact": f"{100 * (np.exp(w_lv.params['is_exact_spell']) - 1):.0f}",
        "wLogInit": f"{w_lv.params['is_initials']:+.2f}",
        "wLogInitSe": f"{w_lv.bse['is_initials']:.2f}",
        "wLogInitPost": f"{w_lv.params['is_initials_post']:+.2f}",
        "wLogInitPostSe": f"{w_lv.bse['is_initials_post']:.2f}",
        "tLogExact": f"{t2_lv.params['is_exact_spell']:+.2f}",
        "tLogExactSe": f"{t2_lv.bse['is_exact_spell']:.2f}",
        "tLogInit": f"{t2_lv.params['is_initials']:+.2f}",
        "tLogInitSe": f"{t2_lv.bse['is_initials']:.2f}",
        "tLogInitPost": f"{t2_lv.params['is_initials_post']:+.2f}",
        "tLogInitPostSe": f"{t2_lv.bse['is_initials_post']:.2f}",
        "pLogExact": f"{p_lv.params['is_exact_spell']:+.2f}",
        "pLogExactSe": f"{p_lv.bse['is_exact_spell']:.2f}",
        "lsVsInitPost": f"{ls_vs.params['is_initials_post']:+.2f}",
        "lsVsInitPostSe": f"{ls_vs.bse['is_initials_post']:.2f}",
        "esPreLast": f"{es_fit.params['close_2010-Apr2015']:+.2f}",
        "esPreLastSe": f"{es_fit.bse['close_2010-Apr2015']:.2f}",
        "esPostFirst": f"{es_fit.params['close_May2015-2019']:+.2f}",
        "esPostFirstSe": f"{es_fit.bse['close_May2015-2019']:.2f}",
        "biharVsSame": f"{b_vs.params['is_same']:+.2f}",
        "biharVsSameSe": f"{b_vs.bse['is_same']:.2f}",
        "biharLogSame": f"{b_lv.params['is_same']:+.2f}",
        "biharLogSameSe": f"{b_lv.bse['is_same']:.2f}",
        "lsLeaderExact": f"{ls_lm:.1f}",
        "lsMinorExact": f"{ls_mm:.1f}",
        "lsLeaderRatio": f"{ls_lm / ls_mm:.1f}",
        "aeLeaderExact": f"{ae_lm:.1f}",
        "aeMinorExact": f"{ae_mm:.1f}",
        "aeLeaderRatio": f"{ae_lm / ae_mm:.1f}",
    }
    lines = [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in macros.items()]
    (TABS / "macros.tex").write_text("\n".join(lines) + "\n")


def main():
    TABS.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)
    source = json.loads(Path("data/source.json").read_text())
    usable, ind = _prepare_tcpd(source)
    ind_minor = ind[ind["Position"] > 2].copy()
    fits_did = write_tcpd_did_table(ind_minor)
    fits_het = write_heterogeneity_table(ind_minor)
    fits_bihar = write_bihar_table(source)
    write_margin_flips_table()
    es_fit = plot_event_study(ind_minor)
    plot_did_coef(fits_did)
    write_style_and_macros(usable, ind_minor, fits_did, fits_het, fits_bihar, es_fit)
    print("Wrote tables to tabs/ and figures to figs/.")


if __name__ == "__main__":
    main()
