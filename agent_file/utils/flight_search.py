import os
import serpapi
from dotenv import load_dotenv

load_dotenv()


class FlightSearchTool:
    """Tool to find flights between two locations"""

    def __init__(self):
        self.client = serpapi.Client(
            api_key=os.getenv("SERP_API_KEY")
        )

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

            return cleaned_results

        except Exception as e:
            return {"error": str(e)}