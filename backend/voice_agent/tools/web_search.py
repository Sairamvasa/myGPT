import httpx
from typing import Dict, List
from voice_agent.tools.base import Tool, ToolRegistry
from voice_agent.security.permissions import PermissionLevel

class WebSearchTool(Tool):
    def __init__(self):
        super().__init__(
            name='web_search',
            description='Perform a simple web search and return top result snippets.',
            permission=PermissionLevel.MEDIUM,
            parameters={
                'query': {'type': 'string', 'description': 'Search query'}
            }
        )
        self.client = httpx.AsyncClient(timeout=10)

    async def run(self, **kwargs) -> Dict[str, any]:
        query = kwargs.get('query')
        if not query:
            return {'error': 'Missing query'}
        try:
            resp = await self.client.get('https://duckduckgo.com/html/', params={'q': query})
            resp.raise_for_status()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            for a in soup.select('a.result__a')[:5]:
                results.append(a.get_text(strip=True))
            return {'result': results}
        except Exception as e:
            return {'error': str(e)}

ToolRegistry.register(WebSearchTool())
