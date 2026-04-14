from agent_file.utils.flight_search import FlightSearchTool
from langchain.tools import tool

def get_flight_search_tool():
    """Return a list of hotel search tools"""
    search = FlightSearchTool()

    @tool
    def find_flights(departure_id: str, arrival_id: str, outbound_date: str):
        """
        Search for available flights between two airports.

        Args:
            departure_id: IATA airport code for departure (e.g. 'BOM' for Mumbai,
                          'DEL' for Delhi, 'JFK' for New York, 'LHR' for London).
                          Must be a 3-letter uppercase IATA code — NOT a city name.
            arrival_id:   IATA airport code for arrival (same format as departure_id).
                          Must be different from departure_id.
            outbound_date: Date of travel in YYYY-MM-DD format (e.g. '2025-06-15').

        Returns a list of available flights with airline, price, duration, and stops.
        """
        return search.find_flights(departure_id, arrival_id, outbound_date)
    
    return find_flights