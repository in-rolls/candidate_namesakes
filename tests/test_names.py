import pytest

from candidate_namesakes.names import exact_key, spelling_key


@pytest.mark.parametrize(
    "a, b",
    [
        ("SUNIL KUMAR", "Suneel Kumar"),
        ("सुनील कुमार", "सुनिल कुमार"),
        ("VINOD SAH", "BINOD SAH"),
        ("विनोद साह", "बिनोद साह"),
        ("संजय यादव", "सन्जय यादव"),
        ("प्रदीप ठाकुर (2)", "परदीप ठाकुर"),
        ("MD. ISLAM", "MOHAMMAD ISLAM"),
        ("मो० इस्लाम", "मोहम्मद इस्लाम"),
        ("SANJAY KR. SINGH", "SANJAY KUMAR SINGH"),
        ("RAKESH", "RAKESH (1)"),
        ("ANIL KUMAR I", "ANIL KUMAR II"),
        ("SITA DEVI (II)", "SITA DEVI 2"),
        ("सीता देवी (१)", "सीता देवी"),
        ("अंजु देवी -2", "अंजू देवी -१"),
        ("RAJ KUMAR-II", "RAJ KUMAR -I"),
        ("SUNITA DEVI1", "SUNITA DEVI 2"),
        ("सुनीता देवी2", "सुनीता देवी"),
    ],
)
def test_same_spoken_name_shares_spelling_key(a, b):
    assert spelling_key(a) == spelling_key(b)


@pytest.mark.parametrize(
    "a, b",
    [
        ("REKHA DEVI", "REENA DEVI"),
        ("SUNITA DEVI", "SANITA DEVI"),
        ("रेखा देवी", "रीना देवी"),
        ("सुनीता देवी", "सुनैना देवी"),
        ("RAM KUMAR", "SHYAM KUMAR"),
    ],
)
def test_different_names_keep_different_keys(a, b):
    assert spelling_key(a) != spelling_key(b)


def test_sec_number_needs_its_own_word():
    assert exact_key("RAVI") == "RAVI"
    assert exact_key("SUNITA KUMARI") == "SUNITA KUMARI"


def test_exact_key_keeps_spelling():
    assert exact_key("Sunil  Kumar (1)") == "SUNIL KUMAR"
    assert exact_key("SUNIL KUMAR") != exact_key("SUNEEL KUMAR")


def test_missing_name():
    assert exact_key(None) is None
    assert spelling_key("  ") is None


def test_spaces_inside_a_name_do_not_split_it():
    joined = spelling_key("राजकुमार सहनी").replace(" ", "")
    assert spelling_key("राज कुमार सहनी").replace(" ", "") == joined


def test_nicknames_and_parents_are_not_part_of_the_name():
    assert exact_key("CHANDU LAL SAHU (CHANDU BHAIYA)") == "CHANDU LAL SAHU"
    assert exact_key("KULDEEP S/O NARAIN SINGH") == "KULDEEP"
    assert exact_key("KULDEEP SINGH S/O SHISHPAL") == "KULDEEP SINGH"
    assert exact_key("SITA W/O RAM") == "SITA"
    assert exact_key("RAMESH CHANDRA URF RAMESH YADAV") == "RAMESH CHANDRA"
