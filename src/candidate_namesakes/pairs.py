"""Pairs of candidates in one contest whose names a voter might mix up.

Every pair of distinct candidates in a contest is scored; a pair is kept when
any signal says the names resemble each other:

- ``is_same_exact``: the same name once case, punctuation and SEC numbering go.
- ``is_same_spelling``: the same once spelling variants are folded and spaces
  are ignored (राज कुमार = राजकुमार).
- ``is_contained``: every word of one name is in the other (MADAN RAY, MADAN
  KISHOR RAY).
- ``differing_word_similarity``: 1 minus the normalized edit distance between
  the words the two names do not share, on the folded spelling. Shared words
  (a surname, Devi, Kumar) are set aside first, because they make whole-name
  similarity high for names no one would confuse (ANIL KUMAR SINGH, NIRMAL
  KUMAR SINGH).
- ``shares_a_word``: the names have a word in common, or both are one word.
  Without it, similarity can pair names with nothing alike (BEBY SINHA, SIMA
  DEVI).
"""

from collections import Counter
from itertools import combinations

import pandas as pd
from rapidfuzz.distance import Levenshtein

KEEP_SIMILARITY = 0.5


def compact(key):
    return key.replace(" ", "")


def differing_words(a, b):
    """The words of each name that the other lacks, as multisets."""
    count_a, count_b = Counter(a.split()), Counter(b.split())
    return count_a - count_b, count_b - count_a


def differing_word_similarity(a, b):
    """Edit similarity of the unshared words; None when one name has none."""
    only_a, only_b = differing_words(a, b)
    if not only_a or not only_b:
        return None
    text_a = " ".join(sorted(only_a.elements()))
    text_b = " ".join(sorted(only_b.elements()))
    return Levenshtein.normalized_similarity(text_a, text_b)


def shares_a_word(a, b):
    words_a, words_b = a.split(), b.split()
    if len(words_a) == 1 and len(words_b) == 1:
        return True
    return bool(set(words_a) & set(words_b))


def score(a, b):
    """(same spelling, contained, differing-word similarity, shares a word)."""
    if compact(a) == compact(b):
        return True, False, 1.0, True
    only_a, only_b = differing_words(a, b)
    contained = not only_a or not only_b
    return False, contained, differing_word_similarity(a, b), shares_a_word(a, b)


def is_kept(same_spelling, contained, similarity):
    return (
        same_spelling
        or contained
        or (similarity is not None and similarity >= KEEP_SIMILARITY)
    )


def build_pairs(candidates):
    """One row per kept pair of distinct candidates in the same contest."""
    people = candidates[
        ~candidates.is_duplicate_record & candidates.name_spelling.notna()
    ]
    columns = ["candidate_id", "candidate_name", "name_exact", "name_spelling"]
    scores = {}
    rows = []
    for row_id, group in people.groupby("row_id", sort=False):
        records = group[columns].itertuples(index=False)
        for one, two in combinations(records, 2):
            key = tuple(sorted((one.name_spelling, two.name_spelling)))
            if key not in scores:
                scores[key] = score(*key)
            same_spelling, contained, similarity, shared = scores[key]
            if not is_kept(same_spelling, contained, similarity):
                continue
            rows.append(
                (
                    row_id,
                    one.candidate_id,
                    two.candidate_id,
                    one.candidate_name,
                    two.candidate_name,
                    one.name_spelling,
                    two.name_spelling,
                    one.name_exact == two.name_exact,
                    same_spelling,
                    contained,
                    similarity,
                    shared,
                )
            )
    return pd.DataFrame(
        rows,
        columns=[
            "row_id",
            "candidate_id_a",
            "candidate_id_b",
            "candidate_name_a",
            "candidate_name_b",
            "name_spelling_a",
            "name_spelling_b",
            "is_same_exact",
            "is_same_spelling",
            "is_contained",
            "differing_word_similarity",
            "shares_a_word",
        ],
    )
