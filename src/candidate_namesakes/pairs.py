"""Pairs of candidates in one contest whose names a voter might mix up.

Every pair of distinct candidates in a contest is scored; a pair is kept when
any signal says the names resemble each other:

- ``is_same_exact``: the same name once case, punctuation and SEC numbering go.
- ``is_same_spelling``: the same once spelling variants are folded and spaces
  are ignored (राज कुमार = राजकुमार).
  Word order is ignored too (N. SUBRAMANIAN = SUBRAMANIAN N.).
- ``is_alias_match``: one name, or one of its printed aliases, is an alias of
  the other (MANOJ KUMAR URF MANOJ SAH beside MANOJ SAH).
- ``is_same_except_initials``: the same once one-letter words are dropped
  (K. MOORTHY, A. K. MOORTHY, S. MOORTHY). Where names carry the father's or
  village initial, this is the usual form a namesake takes.
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
    # Initials are compared by the initials rule, not by edit distance.
    full_a = sorted(w for w in only_a.elements() if len(w) > 1)
    full_b = sorted(w for w in only_b.elements() if len(w) > 1)
    if not full_a or not full_b:
        return None
    return Levenshtein.normalized_similarity(" ".join(full_a), " ".join(full_b))


def shares_a_word(a, b):
    """A shared word other than an initial, or each name has one full word."""
    full_a = {w for w in a.split() if len(w) > 1}
    full_b = {w for w in b.split() if len(w) > 1}
    if len(full_a) <= 1 and len(full_b) <= 1:
        return True
    return bool(full_a & full_b)


def without_initials(key):
    """The full words, joined without spaces (PANNIR SELVAM = PANNIRSELVAM)."""
    return "".join(sorted(word for word in key.split() if len(word) > 1))


def score(a, b):
    """(same spelling, same except initials, contained, similarity, shares a word)."""
    if compact(a) == compact(b) or Counter(a.split()) == Counter(b.split()):
        return True, False, False, 1.0, True
    full_a, full_b = without_initials(a), without_initials(b)
    initials = bool(full_a) and full_a == full_b
    only_a, only_b = differing_words(a, b)
    contained = not only_a or not only_b
    similarity = differing_word_similarity(a, b)
    return False, initials, contained, similarity, shares_a_word(a, b)


def alias_match(one, two):
    """Either name, or any alias of it, is an alias of the other."""
    keys_one = {compact(k) for k in (one.name_alias_keys or ()) if k}
    keys_two = {compact(k) for k in (two.name_alias_keys or ()) if k}
    if not keys_one and not keys_two:
        return False
    names_one = keys_one | {compact(one.name_spelling)}
    names_two = keys_two | {compact(two.name_spelling)}
    return bool(names_one & names_two)


def is_kept(same_spelling, initials, contained, similarity):
    return (
        same_spelling
        or initials
        or contained
        or (similarity is not None and similarity >= KEEP_SIMILARITY)
    )


def build_pairs(candidates):
    """One row per kept pair of distinct candidates in the same contest."""
    people = candidates[
        ~candidates.is_duplicate_record & candidates.name_spelling.notna()
    ]
    columns = ["candidate_id", "candidate_name", "name_exact", "name_spelling"]
    columns += ["name_alias_keys"]
    scores = {}
    rows = []
    for row_id, group in people.groupby("row_id", sort=False):
        records = group[columns].itertuples(index=False)
        for one, two in combinations(records, 2):
            key = tuple(sorted((one.name_spelling, two.name_spelling)))
            if key not in scores:
                scores[key] = score(*key)
            same_spelling, initials, contained, similarity, shared = scores[key]
            alias = not same_spelling and alias_match(one, two)
            if not (alias or is_kept(same_spelling, initials, contained, similarity)):
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
                    alias,
                    initials,
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
            "is_alias_match",
            "is_same_except_initials",
            "is_contained",
            "differing_word_similarity",
            "shares_a_word",
        ],
    )
