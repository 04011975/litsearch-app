from datetime import datetime


def _get_value(p, *names):
    for name in names:
        if isinstance(p, dict):
            value = p.get(name)
        else:
            value = getattr(p, name, None)

        if value not in (None, ""):
            return value

    return None


def all_year_value(p):
    raw = _get_value(p, "year", "publication_year", "pub_year", "publication_date")

    if raw:
        try:
            return int(str(raw)[:4])
        except Exception:
            pass

    date_value = _get_value(p, "publication_date")

    if date_value:
        try:
            return datetime.fromisoformat(str(date_value)[:10]).year
        except Exception:
            return None

    return None


def all_title_value(p):
    return str(_get_value(p, "title") or "").strip().lower()


def all_source_value(p):
    return str(_get_value(p, "source") or "").strip().lower()


def interleave_by_source(items):
    source_order = [
        "pubmed",
        "openalex",
        "europe_pmc",
        "semantic_scholar",
    ]

    buckets = {src: [] for src in source_order}
    others = []

    for p in items:
        src = all_source_value(p)

        if src in buckets:
            buckets[src].append(p)
        else:
            others.append(p)

    result = []

    while any(buckets[src] for src in source_order):
        for src in source_order:
            if buckets[src]:
                result.append(buckets[src].pop(0))

    result.extend(others)
    return result