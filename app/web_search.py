import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import TAVILY_API_KEY


class WebSearchConfigurationError(RuntimeError):
    pass


def search_web(query: str, max_results: int = 5, search_depth: str = "basic") -> list[dict]:
    if not TAVILY_API_KEY:
        raise WebSearchConfigurationError("TAVILY_API_KEY yapılandırılmamış.")
    response = httpx.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
        json={
            "query": query,
            "topic": "general",
            "search_depth": search_depth,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        },
        timeout=25.0,
    )
    response.raise_for_status()
    payload = response.json()
    return [
        {
            "number": position,
            "title": result.get("title") or result.get("url") or f"Web sonucu {position}",
            "url": result.get("url", ""),
            "content": result.get("content", ""),
            "score": round(float(result.get("score", 0)), 4),
            "query": query,
        }
        for position, result in enumerate(payload.get("results", []), 1)
        if result.get("url")
    ]


def search_web_queries(queries: list[str], total_limit: int = 10) -> list[dict]:
    """Planlanan sorguları paralel çalıştırır, URL bazında birleştirip sıralar."""
    if not queries:
        return []
    merged: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(len(queries), 3)) as executor:
        futures = {
            executor.submit(search_web, query, 6 if position == 0 else 5, "advanced" if position == 0 else "basic"): query
            for position, query in enumerate(queries)
        }
        for future in as_completed(futures):
            for result in future.result():
                current = merged.get(result["url"])
                if current is None or result["score"] > current["score"]:
                    merged[result["url"]] = result
    ranked = sorted(merged.values(), key=lambda item: item["score"], reverse=True)[:total_limit]
    for number, result in enumerate(ranked, 1):
        result["number"] = number
    return ranked
