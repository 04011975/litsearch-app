from typing import List, Protocol
from app.models.paper import Paper


class LiteratureConnector(Protocol):
    def search(self, query: str, **kwargs) -> List[Paper]:
        ...

    def fetch_detail(self, identifier: str) -> Paper | None:
        ...
