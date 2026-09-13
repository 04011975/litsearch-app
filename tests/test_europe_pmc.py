from app.connectors.europe_pmc import _map_result_json_to_paper


def test_map_result_normalizes_escaped_subscript_markup_in_abstract():
    item = {
        "pmid": "12345678",
        "title": "Test paper",
        "abstractText": r"Measured T\<sub>1\</sub> values in the study.",
    }

    paper = _map_result_json_to_paper(item)

    assert paper.abstract == "Measured T1 values in the study."


def test_map_result_normalizes_plain_subscript_markup_in_abstract():
    item = {
        "pmid": "12345678",
        "title": "Test paper",
        "abstractText": "Measured T<sub>1</sub> values in the study.",
    }

    paper = _map_result_json_to_paper(item)

    assert paper.abstract == "Measured T1 values in the study."


def test_map_result_normalizes_superscript_markup_in_abstract():
    item = {
        "pmid": "12345678",
        "title": "Test paper",
        "abstractText": r"CO\<sup>2\</sup> concentration increased.",
    }

    paper = _map_result_json_to_paper(item)

    assert paper.abstract == "CO2 concentration increased."


def test_map_result_preserves_plain_abstract_text():
    item = {
        "pmid": "12345678",
        "title": "Test paper",
        "abstractText": "Plain abstract text without markup.",
    }

    paper = _map_result_json_to_paper(item)

    assert paper.abstract == "Plain abstract text without markup."
