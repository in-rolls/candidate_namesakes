import pytest

from candidate_namesakes.parse import parse_name


@pytest.mark.parametrize(
    "raw, name",
    [
        ("KULDEEP S/O NARAIN SINGH", "KULDEEP"),
        ("RAMPAL S/0 RAM JIYAWAN", "RAMPAL"),
        ("CHANDU LAL SAHU (CHANDU BHAIYA)", "CHANDU LAL SAHU"),
        ("RAJ KUMAR JAIN URF RAJU JAIN", "RAJ KUMAR JAIN"),
        ("JAY VARDHAN YADAV @ BACHCHA YADAV", "JAY VARDHAN YADAV"),
        ("KAMLA DEVI/KAMLI DEVI", "KAMLA DEVI"),
        ("DR. MAHESH SHARMA", "MAHESH SHARMA"),
        ("PROF: SUMATHI HARIDAS", "SUMATHI HARIDAS"),
        ("श्री मती ओमवती", "ओमवती"),
        ("SARGUNAM, C.", "C SARGUNAM"),
        ("M0HD. YOUSUF PARRAY", "MOHD YOUSUF PARRAY"),
        ("4. KISHORE", "KISHORE"),
        ("MINNAL SRINIVASAN. M.A.,M.PHIL.", "MINNAL SRINIVASAN"),
        ("SHRI KUMARI", "SHRI KUMARI"),
        ("Kanuga Anwar I", "KANUGA ANWAR I"),
    ],
)
def test_name(raw, name):
    assert parse_name(raw).name == name


def test_relation_and_relative():
    parsed = parse_name("RAJU S/o LATE CHALUVASHETTY")
    assert parsed.relation == "son of" and parsed.relative == "CHALUVASHETTY"
    parsed = parse_name("पूसी देवी पत्नी सेवाराम")
    assert parsed.name == "पूसी देवी" and parsed.relation == "wife of"


def test_pati_inside_a_name_is_not_a_husband():
    assert parse_name("कमला पति देवी").name == "कमला पति देवी"


def test_aliases_are_kept():
    assert parse_name("मनोज कुमार उर्फ मनोज साह").aliases == ("मनोज साह",)
    assert parse_name("தனலட்சுமி (எ) லட்சுமி.க").name == "தனலட்சுமி"
    assert parse_name("RAMLAL / NANDA").aliases == ("NANDA",)


def test_brackets_that_are_not_numbers_become_notes():
    parsed = parse_name("LALU RAM LAUR (BHEEL)")
    assert parsed.name == "LALU RAM LAUR" and parsed.notes == ("BHEEL",)


@pytest.mark.parametrize(
    "raw, number",
    [
        ("UMASHANKAR TIWARI-1", "1"),
        ("RAJESH KUMAR - (1)", "1"),
        ("अनीता देवी (१)", "१"),
        ("KANTI DEVI (II)", "II"),
        ("SHAMBHU  KUMAR I", "I"),
        ("SITA DEVI/1", "1"),
        ("SUNITA DEVI1", "1"),
    ],
)
def test_sec_numbering_where_the_source_numbers_namesakes(raw, number):
    parsed = parse_name(raw, numbering=True)
    assert parsed.sec_number == number and not parsed.name.endswith(number)


def test_john_ii_and_john_iii_keep_their_numbers():
    assert parse_name("JOHN II", numbering=True).sec_number == "II"
    assert parse_name("JOHN III", numbering=True).sec_number == "III"
    assert parse_name("JOHN II").name != parse_name("JOHN III").name


def test_initials_in_tamil_and_latin():
    parsed = parse_name("சாந்தா.கு")
    assert parsed.full_words == ("சாந்தா",) and parsed.initials == ("கு",)
    assert parse_name("P. V. NARSIMHA RAO").initials == ("P", "V")
    assert parse_name("JOSHY KUMAR K V").initials == ("K", "V")


def test_tamil_trailing_number_is_a_note():
    parsed = parse_name("தேவராஜன்.64")
    assert parsed.name == "தேவராஜன்" and parsed.notes == ("64",)


def test_devanagari_mark_repairs():
    assert parse_name("मो0 याकूब").name == parse_name("मो० याकूब").name
    assert parse_name("मोO साहब").name == parse_name("मो० साहब").name


@pytest.mark.parametrize(
    "raw", ["VACANT", "Vacant", "None of the Above", None, " ", "(1)", "- / -"]
)
def test_placeholders(raw):
    assert parse_name(raw).is_placeholder
    assert parse_name(raw, numbering=True).is_placeholder


def test_abbreviation_mark_is_not_a_number():
    assert parse_name("मो० सबरे इमाम").notes == ()


def test_initials_only_name_takes_its_full_alias():
    parsed = parse_name("E.V. ALIAS BALASAHEB VIKHE PATIL")
    assert parsed.name == "BALASAHEB VIKHE PATIL" and parsed.aliases == ("E V",)


def test_bracketed_alias():
    assert parse_name("RAM LAL (ALIAS RAMU)").aliases == ("RAMU",)


def test_alias_word_before_a_bracket():
    parsed = parse_name("RITA DEVI OR (REKHA KUMARI)")
    assert parsed.name == "RITA DEVI" and parsed.aliases == ("REKHA KUMARI",)
