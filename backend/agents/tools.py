from ddgs import DDGS


def web_search(query, max_results=5):
    """
    Search the web using DuckDuckGo
    """

    results = []

    with DDGS() as ddgs:

        search_results = ddgs.text(
            query,
            max_results=max_results
        )

        for item in search_results:

            results.append({
                "title": item.get("title"),
                "body": item.get("body"),
                "link": item.get("href")
            })

    return results