from datetime import datetime


def all_year_value(p):
    raw = p.get("year") or p.get("publication_year") or p.get("pub_year")

    if raw:
        try:
            y = int(str(raw).strip()[:4])

            current_year = datetime.utcnow().year

            if y < 1900 or y > current_year:
                return None

            return y

        except Exception:
            pass

    return None


def all_title_value(p):
    return str(p.get("title") or "").strip().lower()


def all_source_value(p):
    return str(p.get("source") or "").strip().lower()


def interleave_by_source(items):
    source_order = [
        "pubmed",
        "openalex",
        "europe_pmc",
        "semantic_scholar",
    ]

    buckets = {src: [] for src in source_order}

    for p in items:
        src = all_source_value(p)

        if src in buckets:
            buckets[src].append(p)

    mixed = []

    max_len = max(
        (len(v) for v in buckets.values()),
        default=0,
    )

    for i in range(max_len):
        for src in source_order:
            if i < len(buckets[src]):
                mixed.append(buckets[src][i])

    return mixed