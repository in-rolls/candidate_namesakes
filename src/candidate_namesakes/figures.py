"""Within-state trend in leaders facing namesakes, Lok Sabha and assemblies.

For each general-election contest the outcome is 1 if the winner or the
runner-up faces at least one lower-placed namesake (exact, or look-alike).
A linear probability model with state fixed effects and a natural cubic
spline in election year (patsy ``cr``, as in mgcv) gives the within-state
trend; a second model adds log(number of candidates), because more candidates
mean more chances of a shared name. The line is the predicted share averaged
over all contests (their states and sizes as observed) with the year set to
each value; the band is a 95% interval from standard errors clustered by
state. Dots are yearly shares after removing each state's mean.

    python -m candidate_namesakes.figures
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import patsy  # noqa: E402
import statsmodels.api as sm  # noqa: E402

CONTESTS = Path("data/release/tcpd/contests.parquet")
FIGURE = Path("docs/figures/namesake_trends.png")
TREND = Path("data/release/tcpd/trend.csv")
SPLINE_DF = {"lok_sabha": 5, "assembly": 6}
TIERS = {"exact": "Exact namesake", "lookalike": "Look-alike (any level)"}
ELECTIONS = {"lok_sabha": "Lok Sabha", "assembly": "State assemblies"}
PHOTO_RULE_YEAR = 2015.4
MIN_CONTESTS_FOR_DOT = 100


def universe(contests):
    general = contests[~contests.by_election & ~contests.names_abbreviated].copy()
    general["log_candidates"] = np.log(general.candidates)
    return general


def fit(frame, outcome, df, with_candidates):
    """OLS with state dummies and a year spline; cluster-robust by state."""
    spline = patsy.dmatrix(
        f"cr(year, df={df}, constraints='center') - 1", frame, return_type="dataframe"
    )
    states = pd.get_dummies(frame.state, drop_first=True, dtype=float)
    parts = [pd.Series(1.0, index=frame.index, name="const"), spline, states]
    if with_candidates:
        parts.append(frame.log_candidates)
    X = pd.concat(parts, axis=1)
    groups = pd.factorize(frame.state)[0]
    model = sm.OLS(frame[outcome].astype(float), X).fit(
        cov_type="cluster", cov_kwds={"groups": groups}
    )
    return model, spline.design_info, X


def average_prediction(model, info, X, frame, years):
    """Mean prediction over all contests with year set to each value."""
    rows = []
    spline_columns = info.column_names
    for year in years:
        spline = patsy.build_design_matrices(
            [info], pd.DataFrame({"year": np.full(len(frame), year)})
        )[0]
        X_year = X.copy()
        X_year[spline_columns] = np.asarray(spline)
        mean_row = X_year.mean(axis=0).to_numpy()
        estimate = float(mean_row @ model.params.to_numpy())
        se = float(np.sqrt(mean_row @ model.cov_params().to_numpy() @ mean_row))
        rows.append((year, estimate, se))
    return pd.DataFrame(rows, columns=["year", "share", "se"])


def within_state_dots(frame, outcome):
    y = frame[outcome].astype(float)
    adjusted = y - y.groupby(frame.state).transform("mean") + y.mean()
    dots = adjusted.groupby(frame.year).agg(["mean", "size"])
    return dots[dots["size"] >= MIN_CONTESTS_FOR_DOT]


def build(contests):
    frame = universe(contests)
    trends, dots = [], {}
    for election in ELECTIONS:
        subset = frame[frame.election == election]
        years = np.linspace(subset.year.min(), subset.year.max(), 120)
        for tier in TIERS:
            outcome = f"has_{tier}"
            subset = subset.assign(**{outcome: subset[f"namesakes_{tier}"] > 0})
            dots[(election, tier)] = within_state_dots(subset, outcome)
            for with_candidates in (False, True):
                model, info, X = fit(
                    subset, outcome, SPLINE_DF[election], with_candidates
                )
                line = average_prediction(model, info, X, subset, years)
                line["election"], line["tier"] = election, tier
                line["holds_candidates_fixed"] = with_candidates
                trends.append(line)
    return pd.concat(trends, ignore_index=True), dots


def draw(trend, dots):
    plt.rcParams.update({"font.size": 10, "font.family": "sans-serif"})
    fig, axes = plt.subplots(2, 2, figsize=(9, 6.2), sharex=True, sharey="col")
    for row, election in enumerate(ELECTIONS):
        for col, tier in enumerate(TIERS):
            ax = axes[row, col]
            d = dots[(election, tier)]
            ax.scatter(d.index, 100 * d["mean"], s=12, color="0.55", zorder=2)
            for fixed, style in ((False, "-"), (True, "--")):
                line = trend[
                    (trend.election == election)
                    & (trend.tier == tier)
                    & (trend.holds_candidates_fixed == fixed)
                ]
                low = 100 * (line.share - 1.96 * line.se)
                high = 100 * (line.share + 1.96 * line.se)
                if not fixed:
                    ax.fill_between(line.year, low, high, color="0.85", lw=0)
                ax.plot(
                    line.year,
                    100 * line.share,
                    style,
                    color="black" if not fixed else "0.35",
                    lw=1.6 if not fixed else 1.2,
                )
            ax.axvline(PHOTO_RULE_YEAR, color="#b2182b", lw=1)
            ax.set_ylim(bottom=0)
            ax.grid(axis="y", color="0.9", lw=0.6)
            ax.spines[["top", "right"]].set_visible(False)
            if row == 0:
                ax.set_title(TIERS[tier], loc="left", fontweight="bold")
            if col == 0:
                ax.set_ylabel(f"{ELECTIONS[election]}\ncontests (%)")
    first = axes[0, 0]
    top = first.get_ylim()[1]
    first.text(PHOTO_RULE_YEAR - 1, top * 0.95, "photos on\nEVMs, 2015",
               color="#b2182b", ha="right", va="top", fontsize=8.5)  # fmt: skip
    last = axes[0, 1]
    line = trend[(trend.election == "lok_sabha") & (trend.tier == "lookalike")]
    for fixed, label in ((False, "state effects"), (True, "+ no. of candidates")):
        end = line[line.holds_candidates_fixed == fixed].iloc[-1]
        last.annotate(label, (end.year, 100 * end.share), xytext=(4, 0),
                      textcoords="offset points", va="center", fontsize=8.5,
                      color="black" if not fixed else "0.35")  # fmt: skip
    for ax in axes[1]:
        ax.set_xlabel("Election year")
    fig.suptitle(
        "Share of contests where the winner or runner-up faces a namesake",
        x=0.06, ha="left", fontweight="bold",
    )  # fmt: skip
    fig.tight_layout(rect=(0, 0, 0.95, 0.96))
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE, dpi=160)


def main():
    contests = pd.read_parquet(CONTESTS)
    trend, dots = build(contests)
    trend.round(5).to_csv(TREND, index=False)
    draw(trend, dots)
    print(f"wrote {FIGURE} and {TREND}")


if __name__ == "__main__":
    main()
