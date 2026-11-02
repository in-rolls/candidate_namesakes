import pytest

from candidate_namesakes.pairs import differing_word_similarity, is_kept, score


def test_shared_words_are_set_aside():
    assert differing_word_similarity("ANIL KUMAR SINGH", "NIRMAL KUMAR SINGH") < 0.5
    assert differing_word_similarity("RANJU DEBI", "SANJU DEBI") == pytest.approx(0.8)


def test_spaces_do_not_make_two_names():
    assert score("राज कुमार सहनि", "राजकुमार सहनि")[0]


def test_a_name_inside_a_longer_one_is_contained():
    same, initials, contained, similarity, _ = score("MADAN RAI", "MADAN KISOR RAI")
    assert not same and not initials and contained and similarity is None
    assert is_kept(same, initials, contained, similarity)


def test_word_order_does_not_matter():
    assert score("N SUBRAMANIAN", "SUBRAMANIAN N")[0]


def test_names_that_differ_only_in_initials():
    assert score("K MURTI", "S MURTI")[1]
    assert score("A K MURTI", "MURTI")[1]
    assert not score("K MURTI", "K RAMES")[1]


def test_names_with_nothing_in_common_share_no_word():
    assert not score("BEBI SINA", "SIMA DEBI")[4]
    assert score("कलाम", "सलाम")[4]


def test_unlike_names_are_dropped():
    assert not is_kept(*score("RAM KUMAR", "SURES PRASAD")[:4])


def test_an_initial_is_not_a_shared_word():
    assert not score("K MURALIDARAN", "M K SASIDARAN")[4]


def test_alias_match():
    from types import SimpleNamespace as Row

    from candidate_namesakes.pairs import alias_match

    one = Row(name_spelling="MANOJ KUMAR", name_alias_keys=["MANOJ SAH"])
    two = Row(name_spelling="MANOJ SAH", name_alias_keys=[])
    three = Row(name_spelling="RAJU SAH", name_alias_keys=[])
    assert alias_match(one, two) and not alias_match(one, three)
