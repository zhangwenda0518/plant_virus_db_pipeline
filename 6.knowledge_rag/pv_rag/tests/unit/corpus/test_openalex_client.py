from unittest.mock import MagicMock, patch

from neblab_rag.corpus.openalex_client import OpenAlexClient


def test_search_by_keywords_uses_pyalex():
    fake_works = MagicMock()
    fake_works.search.return_value = fake_works
    fake_works.filter.return_value = fake_works
    fake_works.paginate.return_value = iter(
        [
            [
                {
                    "id": "https://openalex.org/W1",
                    "doi": "10.1/x",
                    "title": "Sand control study",
                    "publication_year": 2020,
                    "language": "en",
                    "open_access": {"is_oa": True},
                    "cited_by_count": 7,
                    "abstract_inverted_index": {"sand": [0], "study": [1]},
                    "authorships": [{"author": {"display_name": "Alice"}}],
                    "primary_location": {"source": {"display_name": "Nature"}},
                }
            ]
        ]
    )

    with patch("neblab_rag.corpus.openalex_client.Works", return_value=fake_works):
        client = OpenAlexClient(email="a@b.com")
        results = list(
            client.search_by_keywords(
                keywords=["desertification"],
                language="en",
                max_results=10,
            )
        )

    assert len(results) == 1
    assert results[0].openalex_id == "W1"
    assert results[0].title == "Sand control study"
    assert results[0].abstract == "sand study"
