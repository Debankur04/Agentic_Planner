from agent_file.utils.hotel_search import HotelSearchTool
from langchain.tools import tool

def get_hotel_search_tool():
    """Return a list of hotel search tools"""
    search = HotelSearchTool()

    @tool
    def search_hotel( q: str, check_in_date: str, check_out_date: str):
        """Return the list of hotes based on:
        q:  name of the place
        check_in_date: day of checking in
        check_out_date: day of checking out
        """
        return search.find_properties(q, check_in_date,check_out_date)
    
    return search_hotel