"""Split a printed candidate name into the name and everything else.

Candidate lists print more than a name in the name field. The inventory in
docs/names.md counts each kind by source. ``parse_name`` takes them out in a
fixed order and keeps each in its own field, so matching can compare names
and nothing else:

1. placeholders (VACANT, NOTA) are flagged and parsing stops;
2. typing slips are repaired: a zero for the letter O (M0HD, S/0), a Latin O
   or zero for the Devanagari abbreviation mark (मोO, मो0 for मो०);
3. a relation marker and the relative's name (KULDEEP S/O NARAIN SINGH,
   RAJU S/o LATE CHALUVASHETTY, पूसी देवी पत्नी सेवाराम);
4. bracketed text: an SEC number, the Tamil alias marker (எ), or a note
   (a nickname, a caste, an occupation: we keep it, unclassified);
5. alias markers URF, ALIAS, @, उर्फ, என்கிற, and slash alternates
   (KAMLA DEVI/KAMLI DEVI): the first form is the name, the rest are aliases;
6. the SEC's numbering of namesakes ("-1", "2", "II", "(१)"), only where the
   source numbers namesakes (``numbering=True``); elsewhere a trailing I or V
   is an initial (Kanuga Anwar I, K V);
7. other numbers (a leading serial "4. KISHORE", Tamil "தேவராஜன்.64") become
   notes;
8. titles at the start (DR, SHRI, SMT, KUMARI, श्रीमती, कु०) and degrees at
   the end (M.A., M.PHIL.);
9. a comma that reverses the name (SARGUNAM, C. = C. SARGUNAM).

What is left is upper-cased, split into words, and each word is marked as an
initial (one Latin letter, or one Tamil or Devanagari syllable) or not.
"""

import re
import unicodedata
from dataclasses import dataclass, field

PLACEHOLDERS = {"VACANT", "रिक्त", "NOTA", "NONE OF THE ABOVE", "NA", "N/A", "NIL"}

LATIN_TITLES = {
    "DR", "ADV", "ADVOCATE", "SMT", "SHRI", "SRI", "SHREE", "KUMARI", "KU", "KM",
    "PROF", "COL", "CAPT", "MAJ", "ER", "ENGR", "PT", "PANDIT", "SH", "MR",
    "MRS", "MS", "MISS", "HAJI", "SMTI", "TMT", "THIRU", "SELVI",
}  # fmt: skip
DEVANAGARI_TITLES = {
    "श्री",
    "श्रीमती",
    "सुश्री",
    "डॉ",
    "डा",
    "कु",
    "कुमारी",
    "पं",
    "प्रो",
    "एड",
}
_DEGREE = (
    r"(?:M\.?\s?A|B\.?\s?A|M\.?\s?PHIL|PH\.?\s?D|M\.?\s?B\.?\s?B\.?\s?S|LL\.?\s?B"
    r"|[BM]\.?\s?SC|B\.?\s?ED|M\.?\s?COM)\.?"
)
# An alias word just before a bracket: "RITA DEVI OR (REKHA KUMARI)".
ALIAS_BEFORE_BRACKET = re.compile(r"\s*(?:\bOR|\bURF|\bALIAS|@)\s*$", re.IGNORECASE)
DEGREE_TAIL = re.compile(rf"(?:[\s.,]+{_DEGREE})+[\s.,]*$", re.IGNORECASE)
UNAMBIGUOUS_DEGREE = re.compile(r"PHIL|PH\.?\s?D|B\.?\s?B|LL|SC|ED|COM", re.IGNORECASE)

RELATIONS = {"S": "son of", "D": "daughter of", "W": "wife of", "C": "care of"}
RELATION_LATIN = re.compile(
    r"[\s,]+(?:(?P<code>[SDWC])\s*/\s*[O0]\b\.?|(?P<word>SON|DAUGHTER|WIFE)\s+OF\b)"
    r"[\s.:-]*",
    re.IGNORECASE,
)
RELATION_DEVANAGARI = re.compile(r"\s+(?P<word>पुत्र|पुत्री|पत्नी)\s+")
LATE = re.compile(r"^(?:LATE|स्व[०.]?|स्वर्गीय)\s*", re.IGNORECASE)

BRACKET = re.compile(r"\(([^)]*)\)?|\[([^\]]*)\]")
ALIAS = re.compile(r"\s+(?:URF|ALIAS|उर्फ़?|என்கிற)\s+|\s*@\s*", re.IGNORECASE)
TAMIL_ALIAS = "எ"
ALIAS_IN_BRACKET = re.compile(r"^(?:URF|ALIAS|उर्फ़?)\s+", re.IGNORECASE)
# "मो०": the Devanagari zero after a letter marks an abbreviation.
ABBREVIATION_MARK = re.compile(r"(?<=[\u0900-\u097F])०")
SEC_NUMBER = re.compile(
    r"(?:\s*[-/]\s*|\s+)(?P<n>[0-9०-९]{1,2}|I{1,3}|IV)\s*$|"
    r"(?<=[^\s\d०-९])(?P<glued>[0-9०-९]{1,2})\s*$"
)
SEC_IN_BRACKET = re.compile(r"^\s*(?:[0-9०-९]{1,2}|I{1,3}|IV)\s*$")
NUMBER = re.compile(r"[0-9०-९௦-௯]+")
ZERO_AS_O = re.compile(r"(?<=[A-Za-z])0|0(?=[A-Za-z])")
LATIN_MARK = re.compile(r"(?<=[ऀ-ॿ])\s*[Oo0](?![A-Za-z])")
TAMIL_SYLLABLE = re.compile(r"^[அ-ஹ][ா-்]?(?:[க-ஹ]்)?$")


@dataclass(frozen=True)
class ParsedName:
    raw: object
    name: str | None = None
    words: tuple[str, ...] = ()
    initials: tuple[str, ...] = ()
    title: str | None = None
    relation: str | None = None
    relative: str | None = None
    aliases: tuple[str, ...] = ()
    sec_number: str | None = None
    notes: tuple[str, ...] = ()
    is_placeholder: bool = False
    repairs: tuple[str, ...] = field(default=())

    @property
    def full_words(self):
        """The words that are not initials."""
        return tuple(w for w in self.words if w not in self.initials)


def is_initial(word):
    if len(word) == 1 and word.isascii() and word.isalpha():
        return True
    return bool(TAMIL_SYLLABLE.match(word))


def tidy(text):
    """Upper case, punctuation and symbols to spaces, one space between words."""
    text = "".join(" " if unicodedata.category(c)[0] in "PS" else c for c in text)
    text = text.replace("०", " ")
    return re.sub(r"\s+", " ", text).strip().upper()


def _repair(text, repairs):
    fixed = ZERO_AS_O.sub("O", text)
    if fixed != text:
        repairs.append("zero read as O")
    marked = LATIN_MARK.sub("०", fixed)
    if marked != fixed:
        repairs.append("Latin O or zero read as ०")
    return marked


def _relation(text):
    for pattern in (RELATION_LATIN, RELATION_DEVANAGARI):
        match = pattern.search(text)
        if match:
            code = match.groupdict().get("code")
            word = match.group("word")
            if code:
                kind = RELATIONS[code.upper()]
            elif word in ("पुत्र",):
                kind = "son of"
            elif word in ("पुत्री",):
                kind = "daughter of"
            elif word in ("पत्नी",):
                kind = "wife of"
            else:
                kind = f"{word.lower()} of"
            relative = LATE.sub("", text[match.end() :].strip(" -,.:"))
            return text[: match.start()], kind, relative or None
    return text, None, None


def _brackets(text, numbering):
    notes, aliases, sec = [], [], None
    parts = []
    last = 0
    for match in BRACKET.finditer(text):
        inner = (match.group(1) or match.group(2) or "").strip()
        parts.append(text[last : match.start()])
        last = match.end()
        before = ALIAS_BEFORE_BRACKET.search(parts[-1])
        if inner == TAMIL_ALIAS:
            parts.append(" @ ")
        elif before and inner:
            parts[-1] = parts[-1][: before.start()]
            aliases.append(inner)
        elif ALIAS_IN_BRACKET.match(inner):
            aliases.append(ALIAS_IN_BRACKET.sub("", inner))
        elif numbering and SEC_IN_BRACKET.match(inner):
            sec = inner
        elif inner:
            notes.append(inner)
    parts.append(text[last:])
    return " ".join(parts), notes, aliases, sec


def _sec_number(text):
    match = SEC_NUMBER.search(text)
    if not match:
        return text, None
    return text[: match.start()], match.group("n") or match.group("glued")


def _titles(words):
    """Pop leading titles; keep them when nothing else is left (SHRI KUMARI)."""
    count = 0
    while count < len(words) and words[count] in LATIN_TITLES | DEVANAGARI_TITLES:
        count += 1
    if count == len(words):
        return None
    title = " ".join(words[:count]) or None
    del words[:count]
    return title


def _degrees(text, notes):
    """Strip a trailing run of degrees that includes an unambiguous one.

    M.A. alone could be initials (M.A. RAO); M.PHIL., PH.D., M.B.B.S. cannot.
    """
    match = DEGREE_TAIL.search(text)
    if match and UNAMBIGUOUS_DEGREE.search(match.group(0)):
        notes.append(match.group(0).strip(" .,"))
        return text[: match.start()]
    return text


def _unreverse(text, repairs):
    """ "SARGUNAM, C." -> "C. SARGUNAM" when only initials follow the comma."""
    if text.count(",") != 1:
        return text
    head, tail = (part.strip() for part in text.split(","))
    tail_words = tidy(tail).split()
    if head and tail_words and all(is_initial(w) for w in tail_words):
        repairs.append("comma-reversed order restored")
        return f"{tail} {head}"
    return text


def parse_name(raw, numbering=False):
    """Parse one printed name. ``numbering``: the source numbers namesakes."""
    if not isinstance(raw, str) or not raw.strip():
        return ParsedName(raw=raw, is_placeholder=True)
    text = unicodedata.normalize("NFC", raw)
    text = re.sub("[​-‍﻿]", "", text)
    if tidy(text) in PLACEHOLDERS or text.strip() in PLACEHOLDERS:
        return ParsedName(raw=raw, is_placeholder=True)
    repairs = []
    text = _repair(text, repairs)
    text, relation, relative = _relation(text)
    text, notes, aliases, sec = _brackets(text, numbering)
    forms = [form.strip() for form in ALIAS.split(text)]
    forms = [form for piece in forms for form in piece.split("/")]
    forms = [form.strip(" -,.") for form in forms if form.strip(" -,.")]
    if not forms:
        return ParsedName(raw=raw, is_placeholder=True, notes=tuple(notes))
    if numbering:
        numbered = [f for f in forms[1:] if SEC_IN_BRACKET.match(f)]
        sec = sec or (numbered[0] if numbered else None)
        forms = [forms[0], *(f for f in forms[1:] if not SEC_IN_BRACKET.match(f))]
    text, aliases = forms[0], [*aliases, *forms[1:]]
    if numbering and sec is None:
        text, sec = _sec_number(text)
    text = ABBREVIATION_MARK.sub(" ", text)
    numbers = NUMBER.findall(text)
    if numbers:
        notes.extend(numbers)
        text = NUMBER.sub(" ", text)
    text = _unreverse(_degrees(text, notes), repairs)
    words = tidy(text.replace("श्री मती", "श्रीमती")).split()
    title = _titles(words)
    aliases = [tidy(a) for a in aliases]
    aliases = [a for a in aliases if a]
    if words and all(is_initial(w) for w in words):
        # "E V ALIAS BALASAHEB VIKHE PATIL": the alias is the name in full.
        full = [a for a in aliases if not all(is_initial(w) for w in a.split())]
        if full:
            aliases = [" ".join(words), *(a for a in aliases if a != full[0])]
            words = full[0].split()
            repairs.append("initials-only name replaced by its full alias")
    initials = tuple(w for w in words if is_initial(w))
    return ParsedName(
        raw=raw,
        name=" ".join(words) or None,
        words=tuple(words),
        initials=initials,
        title=title,
        relation=relation,
        relative=tidy(relative) if relative else None,
        aliases=tuple(aliases),
        sec_number=sec,
        notes=tuple(notes),
        is_placeholder=not words,
        repairs=tuple(repairs),
    )
