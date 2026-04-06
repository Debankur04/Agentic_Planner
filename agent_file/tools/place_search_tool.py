from agent_file.utils.place_info_search import TavilyPlaceSearchTool
from langchain.tools import tool

def get_place_search_tools():
    """Return a list of place search tools."""
    search = TavilyPlaceSearchTool()

    @tool
    def search_attractions(place: str) -> str:
        """Search for tourist attractions in a place"""
        return search.search_attractions(place)

    @tool
    def search_restaurants(place: str) -> str:
        """Search for restaurants in a place"""
        return search.search_restaurants(place)

    @tool
    def search_activities(place: str) -> str:
        """Search for activities and things to do in a place"""
        return search.search_activities(place)

    @tool
    def search_transportation(place: str) -> str:
        """Search for transportation options in a place"""
        return search.search_transportation(place)

    return [search_attractions, search_restaurants, search_activities, search_transportation]