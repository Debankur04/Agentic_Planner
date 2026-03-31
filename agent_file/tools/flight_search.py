from agent_file.utils.flight_search import FlightSearchTool
from langchain.tools import tool

def get_flight_search_tool():
    """Return a list of hotel search tools"""
    search = FlightSearchTool()

    @tool
    def find_flights(departure_id,arrival_id,outbound_date):
        """
        Get flight details based on the parameters given:
        departure_id: short hand for departure place
        arrival_id short hand for arriaval place
        outbound_date: day of travelling
        Departure and arrival cant be same.
        """
        return search.find_flights(departure_id,arrival_id,outbound_date)
    
    return find_flights