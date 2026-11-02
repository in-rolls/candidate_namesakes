"""Keys that decide when two candidates in one contest share a name.

Names are parsed first (``parse.parse_name``): titles, relations, aliases,
bracketed notes and the SEC's numbering come out of the name before any
comparison. ``exact_key`` is the parsed name itself. ``spelling_key`` also
folds spellings that write the same spoken name (Suneel/Sunil, सुनील/सुनिल,
Vinod/Binod); ``alias_keys`` folds each alias the same way.

The fold table is written here rather than taken from a library: the phonetic
codes on PyPI (Soundex, Metaphone, libindic-soundex, last released 2019) drop
vowels, so they merge different names such as Sunita and Sanita. Each fold below
is a spelling choice the candidate lists make both ways (checked on Bihar).
"""

import re

import pandas as pd

from candidate_namesakes.parse import parse_name

DEVANAGARI = re.compile(r"[ऀ-ॿ]")

# Applied in order, after NFC normalization.
DEVANAGARI_FOLDS = [
    ("़", ""),  # nukta: ड़ -> ड, ज़ -> ज
    ("न्", "ं"),  # half n and anusvara: सन्जय = संजय
    ("म्", "ं"),
    ("ँ", "ं"),  # chandrabindu
    ("्", ""),  # remaining virama: प्रदीप = परदीप
    ("ी", "ि"),  # long and short i
    ("ू", "ु"),  # long and short u
    ("ई", "इ"),
    ("ऊ", "उ"),
    ("ॉ", "ो"),
    ("ऑ", "ओ"),
    ("ृ", "ि"),
    ("ऋ", "रि"),
    ("श", "स"),
    ("ष", "स"),
    ("व", "ब"),  # Binod/Vinod
    ("ण", "न"),
]
DEVANAGARI_TOKENS = {"मोहम्मद": "मो", "मोहमद": "मो", "मुहम्मद": "मो", "मो": "मो"}

LATIN_TOKENS = {
    "MD": "MD",
    "MOHD": "MD",
    "MOHAMMAD": "MD",
    "MOHAMMED": "MD",
    "MOHAMAD": "MD",
    "MOHAMED": "MD",
    "MUHAMMAD": "MD",
    "KR": "KUMAR",
}
# Applied in order to each upper-case Latin token.
LATIN_FOLDS = [
    ("EE", "I"),
    ("OO", "U"),
    ("PH", "F"),
    ("SH", "S"),
    ("W", "V"),
    ("V", "B"),
    ("Y", "I"),
    ("Z", "J"),
    ("Q", "K"),
    ("CK", "K"),
]
ASPIRATE = re.compile(r"([BCDGJKPT])H")
DOUBLE = re.compile(r"(.)\1+")


def exact_key(name, numbering=True):
    """The parsed name: case, punctuation, titles, relations, aliases and SEC
    numbering removed. ``numbering``: the source numbers its namesakes."""
    return parse_name(name, numbering).name


def _fold_devanagari(token):
    token = DEVANAGARI_TOKENS.get(token, token)
    for old, new in DEVANAGARI_FOLDS:
        token = token.replace(old, new)
    return token


def _fold_latin(token):
    token = LATIN_TOKENS.get(token, token)
    for old, new in LATIN_FOLDS:
        token = token.replace(old, new)
    token = ASPIRATE.sub(r"\1", token)
    return DOUBLE.sub(r"\1", token)


def fold(key):
    """Fold spelling variants of a parsed name, word by word."""
    if not key:
        return None
    folder = _fold_devanagari if DEVANAGARI.search(key) else _fold_latin
    return " ".join(folder(token) for token in key.split())


def spelling_key(name, numbering=True):
    """Exact key with spelling variants of the same spoken name folded."""
    return fold(exact_key(name, numbering))


def alias_keys(name, numbering=True):
    """Spelling keys of the aliases printed with a name."""
    return tuple(fold(a) for a in parse_name(name, numbering).aliases)


def add_name_columns(frame, column, numbering):
    """Parse each distinct name once and add the keys and parsed fields.

    ``numbering`` is a per-row boolean: whether that row's source numbers
    namesakes. Adds ``name_exact``, ``name_spelling``,
    ``name_spelling_compact`` (spaces removed, so राज कुमार = राजकुमार),
    ``name_alias_keys`` (folded aliases), and the parsed extras:
    ``name_title``, ``name_relation``, ``name_relative``, ``name_aliases``,
    ``sec_number``, ``name_notes``, ``name_repairs``, ``is_placeholder``.
    """
    rows = pd.DataFrame({"raw": frame[column], "numbering": numbering})
    distinct = rows.drop_duplicates().reset_index(drop=True)
    parsed = [parse_name(r, bool(n)) for r, n in zip(distinct.raw, distinct.numbering)]
    distinct["name_exact"] = [p.name for p in parsed]
    distinct["name_spelling"] = [fold(p.name) for p in parsed]
    distinct["name_spelling_compact"] = distinct.name_spelling.str.replace(" ", "")
    distinct["name_alias_keys"] = [[fold(a) for a in p.aliases] for p in parsed]
    distinct["name_title"] = [p.title for p in parsed]
    distinct["name_relation"] = [p.relation for p in parsed]
    distinct["name_relative"] = [p.relative for p in parsed]
    distinct["name_aliases"] = [list(p.aliases) for p in parsed]
    distinct["sec_number"] = [p.sec_number for p in parsed]
    distinct["name_notes"] = ["; ".join(p.notes) or None for p in parsed]
    distinct["name_repairs"] = ["; ".join(p.repairs) or None for p in parsed]
    distinct["is_placeholder"] = [p.is_placeholder for p in parsed]
    added = rows.merge(distinct, on=["raw", "numbering"], how="left")
    added.index = frame.index
    return frame.join(added.drop(columns=["raw", "numbering"]))
