import pytest

from candidate_namesakes.pairs import differing_word_similarity, is_kept, score


def test_shared_words_are_set_aside():
    assert differing_word_similarity("ANIL KUMAR SINGH", "NIRMAL KUMAR SINGH") < 0.5
    assert differing_word_similarity("RANJU DEBI", "SANJU DEBI") == pytest.approx(0.8)


def test_spaces_do_not_make_two_names():
    assert score("राज कुमार सहनि", "राजकुमार सहनि")[0]


def test_a_name_inside_a_longer_one_is_contained():
    same, contained, similarity, _ = score("MADAN RAI", "MADAN KISOR RAI")
    assert not same and contained and similarity is None
    assert is_kept(same, contained, similarity)


def test_names_with_nothing_in_common_share_no_word():
    assert not score("BEBI SINA", "SIMA DEBI")[3]
    assert score("कलाम", "सलाम")[3]


def test_unlike_names_are_dropped():
    assert not is_kept(*score("RAM KUMAR", "SURES PRASAD")[:3])
