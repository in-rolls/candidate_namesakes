"""Keys that decide when two candidates in one contest share a name.

``exact_key`` ignores only case, punctuation, spacing and the SEC's "(1)", "(2)"
markers. ``spelling_key`` also folds spellings that write the same spoken name
(Suneel/Sunil, सुनील/सुनिल, Vinod/Binod).

The fold table is written here rather than taken from a library: the phonetic
codes on PyPI (Soundex, Metaphone, libindic-soundex, last released 2019) drop
vowels, so they merge different names such as Sunita and Sanita. Each fold below
is a spelling choice the candidate lists make both ways (checked on Bihar).
"""

import re
import unicodedata

# The SEC numbers namesakes after the name: "(1)", "2", "01", "(१)", "II", "(II)".
SEC_NUMBER = re.compile(r"(?:\s+|\s*\()\s*(?:[0-9०-९]+|I{1,3}|IV)\s*\)?\s*$")
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


def _clean(name):
    # "०" after a word is an abbreviation mark (मो०, स्व०), not a digit.
    name = SEC_NUMBER.sub("", unicodedata.normalize("NFC", name))
    name = "".join(
        " " if unicodedata.category(ch)[0] in "PS" or ch == "०" else ch for ch in name
    )
    return re.sub(r"\s+", " ", name).strip().upper()


def exact_key(name):
    """Name with case, punctuation, spacing and SEC numbering removed."""
    if not isinstance(name, str):
        return None
    return _clean(name) or None


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


def spelling_key(name):
    """Exact key with spelling variants of the same spoken name folded."""
    key = exact_key(name)
    if key is None:
        return None
    fold = _fold_devanagari if DEVANAGARI.search(key) else _fold_latin
    return " ".join(fold(token) for token in key.split())
