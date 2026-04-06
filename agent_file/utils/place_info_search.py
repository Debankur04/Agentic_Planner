from langchain_tavily import TavilySearch

class TavilyPlaceSearchTool:
    """Simple place search using Tavily web search."""

    def __init__(self):
        self.tavily = TavilySearch(topic="general", include_answer="advanced")

    def search_attractions(self, place: str) -> str:
        result = self.tavily.invoke({"query": f"top attractive places in and around {place}"})
        if isinstance(result, dict) and result.get("answer"):
            return result["answer"]
        return str(result)

    def search_restaurants(self, place: str) -> str:
        result = self.tavily.invoke({"query": f"top restaurants and eateries in and around {place}"})
        if isinstance(result, dict) and result.get("answer"):
            return result["answer"]
        return str(result)

    def search_activities(self, place: str) -> str:
        result = self.tavily.invoke({"query": f"activities and things to do in and around {place}"})
        if isinstance(result, dict) and result.get("answer"):
            return result["answer"]
        return str(result)

    def search_transportation(self, place: str) -> str:
        result = self.tavily.invoke({"query": f"modes of transportation available in {place}"})
        if isinstance(result, dict) and result.get("answer"):
            return result["answer"]
        return str(result)
