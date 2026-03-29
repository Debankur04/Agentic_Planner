from agent_file.utils.flight_search import FlightSearchTool
from langchain.tools import tool

def get_flight_search_tool():
    """Return a list of hotel search tools"""
    search = FlightSearchTool()

    @tool
    def find_flights(departure_id,arrival_id,outbound_date,currency,flight_type):
        """
        Get flight details based on the parameters given:
        departure_id: short hand for departure place
        arrival_id short hand for arriaval place
        outbound_date: day of travelling
        currency: shorthand for preffered currency default indian
        flight_type: 1: round trip 2: single trip
        """
        return search.find_flights(departure_id,arrival_id,outbound_date,currency,flight_type)
    
    return find_flights