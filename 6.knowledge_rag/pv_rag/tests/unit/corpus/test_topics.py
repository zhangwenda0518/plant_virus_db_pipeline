from neblab_rag.corpus.topics import TOPICS


def test_seven_topics_defined():
    assert len(TOPICS) == 7


def test_each_topic_has_keywords_in_both_languages():
    for t in TOPICS:
        assert t.zh_keywords, f"{t.id} missing zh"
        assert t.en_keywords, f"{t.id} missing en"


def test_topic_quotas_sum_to_2500():
    assert sum(t.fulltext_quota for t in TOPICS) == 2500
