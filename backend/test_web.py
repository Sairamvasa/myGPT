from agents.tools import web_search

results = web_search("Latest AI News")

for r in results:

    print("=" * 60)

    print("TITLE:", r["title"])

    print("BODY :", r["body"])

    print("LINK :", r["link"])