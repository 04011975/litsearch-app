import requests
from app.connectors import europe_pmc as epmc

def main():
    print("USING:", epmc.__file__)

    q = "cancer"
    n = 5

    # Bouw exact dezelfde params als in europe_pmc_search
    params = {
        "query": q,
        "resultType": "core",
        "format": "json",
        "pageSize": str(n),
        "sort": "relevance",
        "cursorMark": "*",
    }

    r = requests.get(epmc.EUROPE_PMC_SEARCH_URL, params=params, timeout=20)
    print("HTTP:", r.status_code)
    print("Final URL:", r.url)
    print("First 500 chars:", r.text[:500])

    try:
        data = r.json()
    except Exception:
        data = {}

    print("Keys:", list(data.keys()))
    print("hitCount:", data.get("hitCount"))
    rl = (data.get("resultList") or {}).get("result") or []
    print("results_len:", len(rl))
    print("nextCursorMark:", data.get("nextCursorMark"))

if __name__ == "__main__":
    main()
