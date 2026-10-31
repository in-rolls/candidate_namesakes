# Candidate namesakes in Indian local elections

How often a local-election candidate faced a rival with the same name in the
same contest. Coverage so far: Bihar's 2016 and 2021 panchayat elections, every
seat in all six offices. Other states in the pooled
[local_elections](https://github.com/in-rolls/local_elections) candidate tables
(Rajasthan, Tamil Nadu, Uttar Pradesh, Uttarakhand) can be added as further
inputs; each output row carries `state`.

A **contest** is one seat in one election: a gram panchayat's mukhiya, a ward,
a panchayat samiti or zila parishad constituency, a gram kachahari's sarpanch or
member seat. A candidate has a **namesake** when another candidate in the same
contest has the same name. Two definitions of "same name" are counted side by
side:

- **exact**: identical once case, punctuation, spacing and the State Election
  Commission's numbering ("(1)", "2", "01", "(१)", "II") are removed.
- **spelling**: also identical once spellings of one spoken name are folded
  together: ी/ि, ू/ु, श/ष/स, व/ब, nukta, half-n/anusvara (सन्जय = संजय), and in
  Latin letters ee/i, oo/u, w/v/b, sh/s, aspirates, doubled letters, Md/Mohammad,
  Kr./Kumar. Suneel and Sunil, सुनील and सुनिल, Vinod and Binod count as one name.
  The full table is in [`names.py`](src/candidate_namesakes/names.py) and its
  tests in [`tests/test_names.py`](tests/test_names.py).

## Results: Bihar

<!-- summary:start -->

| Year | Office | Contests | Mean candidates | Mean namesakes, exact | Mean namesakes, spelling | Contests with a namesake, exact (%) | Contests with a namesake, spelling (%) | Repeated records dropped |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2016 | Mukhiya (`gp_head`) | 7,995 | 12.0 | 0.31 | 0.33 | 12.4 | 13.2 | 131 |
| 2016 | Ward member (`gp_ward`) | 98,088 | 2.8 | 0.02 | 0.02 | 0.8 | 0.8 | 107 |
| 2016 | Panchayat samiti (`block_member`) | 10,839 | 7.4 | 0.10 | 0.11 | 4.8 | 5.1 | 75 |
| 2016 | Zila parishad (`zp_member`) | 895 | 11.3 | 0.20 | 0.21 | 9.2 | 9.8 | 16 |
| 2016 | Sarpanch (`kachahari_head`) | 7,915 | 5.7 | 0.06 | 0.07 | 3.1 | 3.3 | 78 |
| 2016 | Panch (`kachahari_member`) | 93,019 | 1.5 | 0.00 | 0.00 | 0.1 | 0.1 | 41 |
| 2021 | Mukhiya (`gp_head`) | 8,062 | 8.2 | 0.13 | 0.18 | 6.1 | 7.8 | 0 |
| 2021 | Ward member (`gp_ward`) | 109,583 | 4.6 | 0.04 | 0.06 | 2.1 | 2.7 | 1 |
| 2021 | Panchayat samiti (`block_member`) | 11,075 | 6.7 | 0.07 | 0.09 | 3.5 | 4.3 | 0 |
| 2021 | Zila parishad (`zp_member`) | 1,158 | 11.2 | 0.18 | 0.24 | 7.6 | 9.9 | 0 |
| 2021 | Sarpanch (`kachahari_head`) | 8,056 | 6.2 | 0.06 | 0.08 | 3.1 | 4.0 | 1 |
| 2021 | Panch (`kachahari_member`) | 106,839 | 2.0 | 0.01 | 0.01 | 0.3 | 0.4 | 3 |

<!-- summary:end -->

"Mean namesakes" counts every candidate who has a namesake: a contest with two
Sunita Devis contributes 2. The table is written by `make build` from [`data/release/summary.csv`](data/release/summary.csv).

Most namesakes carry very common names: सुनीता देवी, रेखा देवी, गीता देवी and
SUNITA DEVI head the list. Women's seats gather many "X Devi" candidates.

## Files

| File | Rows | Each row is |
|---|---:|---|
| [`data/release/contests.parquet`](data/release/contests.parquet) | 463,524 | a contest |
| [`data/release/namesake_candidates.parquet`](data/release/namesake_candidates.parquet) | see `MANIFEST.json` | a candidate with a namesake under the spelling definition (a superset of exact) |
| [`data/release/summary.csv`](data/release/summary.csv) | 12 | a year and office |

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

`namesake_candidates.parquet` has `row_id`, `state`, `year`, `tier`, the candidate's
columns from the source (`candidate_id`, `candidate_name`, `relation_name`,
`candidate_age`, `candidate_woman`, `votes`, `elected`), the two keys
(`name_exact`, `name_spelling`) and the size of each namesake group. Join to the
pooled tables on `row_id` or `candidate_id`.

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
  column of the table above). Where relation name or age is blank, records are
  never merged. Vote totals for these candidates are unreliable upstream.
- **Close names that are not folded.** Names that differ by one letter after
  folding (Imtyaz/Imtiyaz, but also Kabita/Sabita, Rita/Rina) are not merged.
  `make build` lists these pairs, about 2,000 distinct ones, in
  `data/build/review_pairs.parquet` for a judgment step,
  [`judge_spellings.py`](src/candidate_namesakes/judge_spellings.py), which
  asks Muse Spark (`muse-spark-1.3-contributor`) whether each pair is one name.
  It has not been run: the provider refused the first pilot request on
  2026-10-31 (HTTP 403, account restricted). The spelling counts above therefore
  exclude these pairs.
- **Scripts.** 2016 lists are 88% Latin letters, 2021 lists all Devanagari. A
  Latin and a Devanagari spelling of one name are not matched; 64 contests mix
  scripts.

## Reproduce

```sh
uv sync --group dev
make fetch      # download the pinned input and print its SHA-256
make build      # write data/release/ and MANIFEST.json (about a minute)
make test
```

`MANIFEST.json` records the input and every output with row counts and SHA-256.
