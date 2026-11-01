# Candidate namesakes in Indian local elections

How often a local-election candidate faced a rival whose name a voter could
mistake for theirs, in the same contest. Coverage so far: Bihar's 2016 and 2021
panchayat elections, every seat in all six offices. Other states in the pooled
[local_elections](https://github.com/in-rolls/local_elections) candidate tables
(Rajasthan, Tamil Nadu, Uttar Pradesh, Uttarakhand) can be added as further
inputs; each output row carries `state`.

A **contest** is one seat in one election: a gram panchayat's mukhiya, a ward,
a panchayat samiti or zila parishad constituency, a gram kachahari's sarpanch or
member seat. The quantity of interest is voter confusion, so names are compared
in three widening tiers:

- **exact namesake**: identical once case, punctuation, spacing and the State
  Election Commission's numbering are removed. The SEC writes it many ways:
  "(1)", "2", "01", "(१)", "II", "(II)", "-2", "-II", "DEVI1".
- **spelling namesake**: also identical once spellings of one spoken name are
  folded together: ी/ि, ू/ु, श/ष/स, व/ब, nukta, half-n/anusvara (सन्जय = संजय), and
  in Latin letters ee/i, oo/u, w/v/b, sh/s, aspirates, doubled letters,
  Md/Mohammad, Kr./Kumar; spaces inside a name are ignored (राज कुमार =
  राजकुमार). Suneel and Sunil, सुनील and सुनिल, Vinod and Binod count as one
  name. The fold table is in [`names.py`](src/candidate_namesakes/names.py), with
  tests in [`tests/test_names.py`](tests/test_names.py).
- **look-alike**: a spelling namesake, or one name contained in the other
  (MADAN RAY, MADAN KISHOR RAY), or names that share a word and whose remaining
  words are at least 0.7 similar by edit distance (गीता/सीता देवी, MANJU/SANJU
  DEVI, KANTI/SANTI DEVI). Shared words are set aside before measuring, because
  a common surname or "Devi" makes whole names look alike when the given names
  are nothing alike (ANIL KUMAR SINGH, NIRMAL KUMAR SINGH). See
  [Look-alike names](#look-alike-names) for how 0.7 was chosen.

## Results: Bihar

<!-- summary:start -->

| Year | Office | Contests | Mean candidates | Mean namesakes, exact | Mean namesakes, spelling | Contests with a namesake, exact (%) | Contests with a namesake, spelling (%) | Contests with a look-alike (%) | Repeated records dropped |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2016 | Mukhiya (`gp_head`) | 7,995 | 12.0 | 0.34 | 0.37 | 13.8 | 14.5 | 26.4 | 131 |
| 2016 | Ward member (`gp_ward`) | 98,088 | 2.8 | 0.02 | 0.02 | 0.9 | 0.9 | 2.2 | 107 |
| 2016 | Panchayat samiti (`block_member`) | 10,839 | 7.4 | 0.11 | 0.12 | 5.3 | 5.7 | 13.2 | 75 |
| 2016 | Zila parishad (`zp_member`) | 895 | 11.3 | 0.21 | 0.22 | 9.7 | 10.4 | 19.8 | 16 |
| 2016 | Sarpanch (`kachahari_head`) | 7,915 | 5.7 | 0.07 | 0.07 | 3.4 | 3.6 | 8.4 | 78 |
| 2016 | Panch (`kachahari_member`) | 93,019 | 1.5 | 0.00 | 0.00 | 0.1 | 0.2 | 0.4 | 41 |
| 2021 | Mukhiya (`gp_head`) | 8,062 | 8.2 | 0.13 | 0.18 | 6.2 | 7.9 | 14.0 | 0 |
| 2021 | Ward member (`gp_ward`) | 109,583 | 4.6 | 0.04 | 0.06 | 2.1 | 2.7 | 5.7 | 1 |
| 2021 | Panchayat samiti (`block_member`) | 11,075 | 6.7 | 0.07 | 0.09 | 3.5 | 4.3 | 9.7 | 0 |
| 2021 | Zila parishad (`zp_member`) | 1,158 | 11.2 | 0.18 | 0.24 | 7.6 | 10.0 | 17.8 | 0 |
| 2021 | Sarpanch (`kachahari_head`) | 8,056 | 6.2 | 0.06 | 0.08 | 3.1 | 4.1 | 8.4 | 1 |
| 2021 | Panch (`kachahari_member`) | 106,839 | 2.0 | 0.01 | 0.01 | 0.3 | 0.4 | 1.0 | 3 |

<!-- summary:end -->

"Mean namesakes" counts every candidate who has a namesake: a contest with two
Sunita Devis contributes 2. A contest has a look-alike when any two of its
candidates are look-alikes. The table is written by `make build` from
[`data/release/summary.csv`](data/release/summary.csv).

Most namesakes carry very common names: सुनीता देवी, रेखा देवी, गीता देवी and
SUNITA DEVI head the list. Women's seats gather many "X Devi" candidates.

## Look-alike names

Two ways of judging whether a voter could mix up two names were compared on
180 within-contest pairs spread across similarity levels: edit similarity of
the words the names do not share, and a 0-3 rating from Muse Spark
(`muse-spark-1.3-contributor`; 0 clearly different, 2 easily confused at a
glance, 3 the same name). Muse rated 48 of 51 pairs above 0.7 similarity as
easily confused or the same, 11 of 16 between 0.6 and 0.7, and 10 of 70 below
0.4.
The two measures largely agree, and 0.7 is where Muse's ratings turn.

Muse also catches cases edit distance cannot: a name inside a longer one
(KRISHNA KUMAR, KRISHNA KUMAR GUPTA), now its own tier, and names split by a
space, now folded. But its ratings did not repeat well enough to replace edit
distance: re-rating 80 pairs in different batches gave the same 0-3 rating 70%
of the time (99% within one point), below the 80% set in advance.
[`rate_confusion.py`](src/candidate_namesakes/rate_confusion.py) rates the
uncertain band (similarity 0.5-0.8 and contained names; about 50,000 distinct
pairs, about $1.10); it was stopped after 2,000 pairs on that gate, and its
output is not published.

## Do look-alikes draw votes?

If voters mix up names, some votes meant for a strong candidate should land on
the rival whose name resembles it. [`check_votes.py`](src/candidate_namesakes/check_votes.py)
compares candidates in the same contest: among those who did not win, how much
higher is the vote share of those whose name resembles the winner's, at each
level of resemblance, than of those whose name does not? Contest fixed effects
absorb everything a contest shares; standard errors are clustered by contest.
As a placebo the same comparison is made against the last-placed candidate,
whose votes are too few for confusion to matter.

<!-- votes:start -->

232,232 contests with every vote count recorded and one clear winner and last-placed candidate.

| Resembles | Resemblance | Candidates | Vote-share gap (points) | Standard error |
|---|---|---:|---:|---:|
| winner | same name | 2,578 | -0.06 | 0.18 |
| winner | contained | 375 | -0.42 | 0.51 |
| winner | similarity 0.8+ | 1,005 | +0.28 | 0.31 |
| winner | similarity 0.6-0.8 | 9,331 | -0.05 | 0.10 |
| winner | similarity 0.5-0.6 | 17,169 | -0.20 | 0.07 |
| last-placed (placebo) | same name | 1,918 | +0.02 | 0.19 |
| last-placed (placebo) | contained | 280 | -0.29 | 0.56 |
| last-placed (placebo) | similarity 0.8+ | 782 | -0.54 | 0.27 |
| last-placed (placebo) | similarity 0.6-0.8 | 7,425 | -0.30 | 0.10 |
| last-placed (placebo) | similarity 0.5-0.6 | 13,728 | -0.22 | 0.07 |

<!-- votes:end -->

No level of resemblance to the winner, including an exact namesake, comes with
a detectable gain in vote share. This does not show that voters are never
confused. Namesakes planted to split a vote are likely weak candidates, while
the comparison group includes serious runners-up, so a gain of a point or two
could be hidden by that difference. By office, in
[`data/release/vote_check.csv`](data/release/vote_check.csv).

## Files

| File | Rows | Each row is |
|---|---:|---|
| [`data/release/contests.parquet`](data/release/contests.parquet) | 463,524 | a contest |
| [`data/release/namesake_candidates.parquet`](data/release/namesake_candidates.parquet) | see `MANIFEST.json` | a candidate with a spelling namesake or a look-alike |
| [`data/release/name_pairs.parquet`](data/release/name_pairs.parquet) | see `MANIFEST.json` | a pair of candidates in one contest whose names resemble each other (spelling namesakes, contained names, or similarity at least 0.5) |
| [`data/release/summary.csv`](data/release/summary.csv) | 12 | a year and office |
| [`data/release/vote_check.csv`](data/release/vote_check.csv) | 70 | an office, comparison and resemblance level |

`contests.parquet` keeps the pooled seat columns (`row_id`, `state`, `year`, `tier`,
`tier_local`, `district`, `block`, `gp_no`, `gram_panchayat`, `ward_no`,
`reserved_caste`, `reserved_woman`) and adds:

| Column | Meaning |
|---|---|
| `candidate_count` | distinct candidates, after removing repeated records |
| `duplicate_record_count` | records dropped as repeats of a candidate (see below) |
| `namesake_exact_count`, `namesake_spelling_count` | candidates who have a namesake |
| `namesake_exact_group_count`, `namesake_spelling_group_count` | distinct shared names (two Sunitas and two Rekhas = 2) |
| `has_namesake_exact`, `has_namesake_spelling` | any namesake in the contest |
| `lookalike_count`, `has_lookalike` | candidates with a look-alike; any in the contest |

`name_pairs.parquet` has `row_id`, `state`, `year`, `tier`, both candidates'
`candidate_id` and printed name (`_a`, `_b`), their spelling keys, and the
signals: `is_same_exact`, `is_same_spelling`, `is_contained`,
`differing_word_similarity` (0-1; blank when one name contains the other) and
`shares_a_word`.

`namesake_candidates.parquet` has `row_id`, `state`, `year`, `tier`, the
candidate's columns from the source (`candidate_id`, `candidate_name`,
`relation_name`, `candidate_age`, `candidate_woman`, `votes`, `elected`), the
keys (`name_exact`, `name_spelling`), the size of each namesake group and
`has_lookalike`. Join to the pooled tables on `row_id` or `candidate_id`.

## Source

One input, pinned in [`data/source.json`](data/source.json):
`data/master/candidates_bihar.parquet` from
[in-rolls/local_elections](https://github.com/in-rolls/local_elections) at commit
`112e86b7`, SHA-256 `98df872c…6698b`, 1,569,245 candidate rows. That table pools
the 2016 and 2021 candidate lists in
[in-rolls/local_elections_bihar](https://github.com/in-rolls/local_elections_bihar)
(commit `ff9c616`). Earlier Bihar elections (2001, 2006, 2011) are published as
winners only, so they cannot be counted here.

## Limitations

- **Repeated records in 2016.** The 2016 release repeats some candidates inside
  a contest, sometimes with their vote totals crossed between two people of the
  same name. A record with the same name, relation name and age as an earlier
  one in the contest is counted once (`duplicate_record_count`, and the last
  column of the results table). Where relation name or age is blank, records are
  never merged. Vote totals for these candidates are unreliable upstream.
- **Scripts.** Voters saw names in Devanagari. 2016 lists are 88% Latin
  transliterations, so 2016 similarity is measured on a spelling voters did not
  see. A Latin and a Devanagari spelling of one name are not matched; 64
  contests mix scripts.
- **The 0.7 threshold** rests on 180 rated pairs and one rater. The pair table
  keeps the similarity, so other cut-offs can be applied.

## Reproduce

```sh
uv sync --group dev
make fetch        # download the pinned input and print its SHA-256
make build        # write data/release/ and MANIFEST.json (about 3 minutes)
make check-votes  # write data/release/vote_check.csv and its README table
make test
```

`MANIFEST.json` records the input and every output of `make build` with row
counts and SHA-256.
