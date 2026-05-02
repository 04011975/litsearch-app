import os


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def clamp_batch_size(value: int, default: int = 100, minimum: int = 1, maximum: int = 1000) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default

    if value < minimum:
        return default
    if value > maximum:
        return maximum
    return value


OPENALEX_EXPORT_BATCH_SIZE = _get_int("OPENALEX_EXPORT_BATCH_SIZE", 100)
PUBMED_EXPORT_EFETCH_BATCH_SIZE = _get_int("PUBMED_EXPORT_EFETCH_BATCH_SIZE", 200)
SEMANTIC_SCHOLAR_BULK_EXPORT_BATCH_SIZE = _get_int("SEMANTIC_SCHOLAR_BULK_EXPORT_BATCH_SIZE", 100)


def get_export_batch_size(source: str) -> int:
    source = (source or "").strip().lower()

    if source == "openalex":
        return clamp_batch_size(OPENALEX_EXPORT_BATCH_SIZE, default=100, minimum=1, maximum=200)

    if source == "pubmed":
        return clamp_batch_size(PUBMED_EXPORT_EFETCH_BATCH_SIZE, default=200, minimum=100, maximum=300)

    if source == "semantic_scholar_bulk":
        return clamp_batch_size(SEMANTIC_SCHOLAR_BULK_EXPORT_BATCH_SIZE, default=100, minimum=1, maximum=1000)

    return 100