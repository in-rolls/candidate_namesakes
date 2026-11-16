"""House style for the repository's figures.

Grayscale estimates, intervals as light-gray bands or bars (never capped
whiskers), one red accent for the 2015 photo rule, a faint y grid, no top or
right spines, bold left-aligned titles, and direct labels instead of legends.
"""

import matplotlib.pyplot as plt

RULE = "#b2182b"
BAND = "0.85"
DOT = "0.55"
SECOND = "0.35"


def apply():
    plt.rcParams.update({"font.size": 10, "font.family": "sans-serif"})


def tidy(ax, title=None):
    ax.grid(axis="y", color="0.9", lw=0.6)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    if title:
        ax.set_title(title, loc="left", fontweight="bold")


def interval_bars(ax, x, est, se, color="black", width=7):
    """Point estimates with 95% intervals drawn as uncapped gray bars."""
    ax.vlines(x, est - 1.96 * se, est + 1.96 * se, color=BAND, lw=width, zorder=1)
    ax.scatter(x, est, color=color, s=22, zorder=3)
