import os
import serpapi
from dotenv import load_dotenv

load_dotenv()


class FlightSearchTool:
    """Tool to find flights between two locations"""

    def __init__(self):
        api_key = os.getenv("SERP_API_KEY")
        if not api_key:
            raise RuntimeError(
                "SERP_API_KEY is not set. Add it to your .env file. "
                "Get a key at https://serpapi.com"
            )
        self.client = serpapi.Client(api_key=api_key)

    def find_flights(
        self,
        departure_id: str,
        arrival_id: str,
        outbound_date: str,
        currency: str = "INR",
        flight_type: int = 2
    ):
        """
        flight_type:
        1 - Round trip
        2 - One way
        3 - Multi-city
        """
        try:
            results = self.client.search({
                "engine": "google_flights",
                "departure_id": departure_id,
                "arrival_id": arrival_id,
                "currency": currency,
                "type": flight_type,
                "outbound_date": outbound_date
            })

            flights = results.get("best_flights", [])

            cleaned_results = []

            for flight in flights[:5]:

                segments = flight.get("flights", [])

                if not segments:
                    continue

                first_leg = segments[0]
                last_leg = segments[-1]

                cleaned_results.append({
                    "airline": first_leg.get("airline"),
                    "price": flight.get("price"),
                    "total_duration": flight.get("total_duration"),
                    "departure_airport": first_leg.get("departure_airport", {}).get("id"),
                    "arrival_airport": last_leg.get("arrival_airport", {}).get("id"),
                    "stops": len(segments) - 1
                })

            if not cleaned_results:
                return {
                    "message": "No flights found for the given route and date. "
                               "Try different dates or check that departure_id and arrival_id "
                               "are valid IATA airport codes (e.g. 'BOM', 'DEL', 'JFK')."
                }

            return cleaned_results

        except Exception as e:
            return {"error": f"Flight search failed: {str(e)}"}