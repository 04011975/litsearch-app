
import csv
import io

from openpyxl import load_workbook

from app.core.ris_export import papers_to_ris
from app.main import _papers_to_csv, _papers_to_xlsx_bytes
from app.models.paper import Paper


def test_export_formats_preserve_paper_order():
    papers = [
        Paper(
            id=f"paper-{i}",
            source="openalex",
            title=f"Test Paper {i}",
            authors=["Test Author"],
            journal="Test Journal",
            year=2024,
            doi=f"10.1234/test-{i}",
            pmcid=None,
            url=f"https://example.org/paper-{i}",
            mesh_terms=[],
            has_full_text=False,
        )
        for i in range(1, 4)
    ]

    expected_ids = ["paper-1", "paper-2", "paper-3"]

    csv_content = _papers_to_csv(papers)
    csv_rows = list(csv.DictReader(io.StringIO(csv_content)))
    csv_ids = [row["ID"] for row in csv_rows]

    ris_content = papers_to_ris(papers)
    ris_ids = [
        line.removeprefix("ID  - ")
        for line in ris_content.splitlines()
        if line.startswith("ID  - ")
    ]

    xlsx_content = _papers_to_xlsx_bytes(papers)
    workbook = load_workbook(io.BytesIO(xlsx_content), read_only=True)
    try:
        xlsx_ids = [
            row[0]
            for row in workbook.active.iter_rows(
                min_row=2, values_only=True
            )
        ]
    finally:
        workbook.close()

    assert csv_ids == expected_ids
    assert ris_ids == expected_ids
    assert xlsx_ids == expected_ids


def test_export_formats_preserve_shared_metadata():
    paper = Paper(
        id="metadata-1",
        source="openalex",
        title="Metadata Consistency Test",
        authors=["Alice Smith", "Bob Jones"],
        journal="Journal of Testing",
        year=2025,
        doi="10.1234/metadata-test",
        pmcid="PMC123456",
        url="https://example.org/metadata",
        mesh_terms=[],
        has_full_text=False,
    )

    csv_content = _papers_to_csv([paper])
    csv_row = next(csv.DictReader(io.StringIO(csv_content)))

    xlsx_content = _papers_to_xlsx_bytes([paper])
    workbook = load_workbook(io.BytesIO(xlsx_content), read_only=True)

    try:
        xlsx_row = next(
            workbook.active.iter_rows(
                min_row=2,
                values_only=True,
            )
        )
    finally:
        workbook.close()

    ris_content = papers_to_ris([paper])

    assert csv_row["ID"] == xlsx_row[0] == paper.id
    assert csv_row["Title"] == xlsx_row[1] == paper.title
    assert csv_row["Authors"] == xlsx_row[2] == "Alice Smith; Bob Jones"
    assert csv_row["Journal"] == xlsx_row[3] == paper.journal
    assert csv_row["Year"] == str(xlsx_row[4]) == str(paper.year)
    assert csv_row["DOI"] == xlsx_row[5] == paper.doi
    assert csv_row["PMCID"] == xlsx_row[6] == paper.pmcid
    assert csv_row["URL"] == xlsx_row[7] == paper.url

    for field in [
        "TI  - Metadata Consistency Test",
        "AU  - Alice Smith",
        "AU  - Bob Jones",
        "JO  - Journal of Testing",
        "PY  - 2025",
        "DO  - 10.1234/metadata-test",
        "AN  - PMC123456",
        "UR  - https://example.org/metadata",
        "ID  - metadata-1",
    ]:
        assert field in ris_content.splitlines()



def test_all_sources_search_and_csv_export_are_consistent(
    client, monkeypatch
):
    papers = [
        Paper(
            id=f"consistent-{i}",
            source="openalex",
            title=f"Consistency Paper {i}",
            authors=["Test Author"],
            journal="Test Journal",
            year=2024,
            doi=f"10.1234/consistent-{i}",
            pmcid=None,
            url=f"https://example.org/consistent-{i}",
            mesh_terms=[],
            has_full_text=False,
        )
        for i in range(1, 4)
    ]

    calls = []

    async def fake_build_all_source_results(**kwargs):
        calls.append(kwargs)
        return {
            "papers": papers,
            "all_papers": papers,
            "total_count": len(papers),
            "duplicates_removed": 1,
            "source_counts": {"openalex": len(papers)},
            "failed_sources": [],
            "snapshot_id": "snapshot-consistency-123",
        }

    monkeypatch.setattr(
        "app.main.build_all_source_results",
        fake_build_all_source_results,
    )

    params = {
        "q": "consistency",
        "source": "all",
        "page": 1,
        "n": 10,
        "sort": "relevance",
        "snapshot_id": "snapshot-consistency-123",
    }

    search_response = client.get("/search", params=params)

    export_response = client.get(
        "/export/csv",
        params={**params, "scope": "page"},
    )

    assert search_response.status_code == 200
    assert export_response.status_code == 200

    csv_rows = list(
        csv.DictReader(io.StringIO(export_response.text))
    )

    expected_ids = [paper.id for paper in papers]
    exported_ids = [row["ID"] for row in csv_rows]

    assert exported_ids == expected_ids

    html = search_response.text
    positions = [
        html.index(f"Consistency Paper {i}")
        for i in range(1, 4)
    ]

    assert positions == sorted(positions)

    assert len(calls) == 2

    for call in calls:
        assert call["q"] == "consistency"
        assert call["page"] == 1
        assert call["n"] == 10
        assert call["sort"] == "relevance"
        assert call["snapshot_id"] == "snapshot-consistency-123"



def test_all_sources_search_and_export_reuse_deduplicated_snapshot(
    client, monkeypatch
):
    from app.main import app

    class FakeRedis:
        def __init__(self):
            self.data = {}

        async def get(self, key):
            return self.data.get(key)

        async def set(self, key, value, ex=None):
            self.data[key] = value
            return True

    redis = FakeRedis()
    monkeypatch.setattr(app.state, "redis", redis, raising=False)

    papers = [
        Paper(
            id=pid,
            source=source,
            title=title,
            authors=["Test Author"],
            journal="Test Journal",
            year=2024,
            doi=doi,
            pmcid=None,
            url=f"https://example.org/{pid}",
            mesh_terms=[],
            has_full_text=False,
        )
        for pid, source, title, doi in [
            ("p1", "pubmed", "First Paper", "10.1234/first"),
            ("p2", "openalex", "Duplicate Paper", "10.1234/first"),
            ("p3", "crossref", "Third Paper", "10.1234/third"),
        ]
    ]

    calls = []

    async def fake_fetch_all_source_candidates(**kwargs):
        calls.append(kwargs)
        return {
            "combined_raw": papers,
            "source_counts": {
                "pubmed": 1,
                "openalex": 1,
                "crossref": 1,
            },
            "failed_sources": [],
        }

    monkeypatch.setattr(
        "app.all_sources.fetch_all_source_candidates",
        fake_fetch_all_source_candidates,
    )

    params = {
        "q": "snapshot consistency",
        "source": "all",
        "page": 1,
        "n": 10,
        "sort": "relevance",
    }

    search_response = client.get("/search", params=params)

    assert search_response.status_code == 200
    assert "First Paper" in search_response.text
    assert "Third Paper" in search_response.text

    assert search_response.text.count("<h3") >= 2

    assert "1 duplicates removed" in search_response.text

    assert len(redis.data) > 0

    # Gebruik de snapshot die door /search is aangemaakt.
    # De test verwacht precies één opgeslagen snapshot.
    assert len(redis.data) == 1

    import json

    snapshot = json.loads(next(iter(redis.data.values())))
    assert isinstance(snapshot, dict)

    # De snapshot-ID staat in de HTML-exportlink.
    import re
    from html import unescape
    from urllib.parse import parse_qs, urlparse

    export_urls = re.findall(
        r'[^"\']*/export/csv[^"\']*',
        unescape(search_response.text),
    )

    assert export_urls

    export_url = export_urls[0]
    snapshot_id = parse_qs(
        urlparse(export_url).query
    ).get("snapshot_id", [None])[0]

    assert snapshot_id

    export_response = client.get(
        "/export/csv",
        params={
            **params,
            "scope": "page",
            "snapshot_id": snapshot_id,
        },
    )

    assert export_response.status_code == 200

    rows = list(
        csv.DictReader(io.StringIO(export_response.text))
    )

    html_titles = [
        title
        for title in re.findall(
            r"<h3[^>]*>\s*(.*?)\s*</h3>",
            search_response.text,
        )
        if title in {"First Paper", "Third Paper"}
    ]

    exported_titles = [row["Title"] for row in rows]

    assert html_titles == exported_titles
    assert set(exported_titles) == {"First Paper", "Third Paper"}
    assert len(rows) == 2
    assert len(calls) == 1
