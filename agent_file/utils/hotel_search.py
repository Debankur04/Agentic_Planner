import os
import serpapi
from dotenv import load_dotenv

load_dotenv()


class HotelSearchTool:
    """Tool to find hotels for a region"""

    def __init__(self):
        api_key = os.getenv("SERP_API_KEY")
        if not api_key:
            raise RuntimeError(
                "SERP_API_KEY is not set. Add it to your .env file. "
                "Get a key at https://serpapi.com"
            )
        self.client = serpapi.Client(api_key=api_key)

    def find_properties(self, q: str, check_in_date: str, check_out_date: str):
        try:
            results = self.client.search({
                "engine": "google_hotels",
                "q": q,
                "check_in_date": check_in_date,
                "check_out_date": check_out_date
            })

            properties = results.get("properties", [])

            cleaned_results = []

            for hotel in properties[:5]:

                cleaned_results.append({
                    "name": hotel.get("name"),
                    "price_per_night": hotel.get("rate_per_night", {}).get("extracted_lowest"),
                    "rating": hotel.get("overall_rating"),
                    "type": hotel.get("type"),
                    "amenities": hotel.get("amenities", [])[:5]  # keep it small
                })

            if not cleaned_results:
                return {
                    "message": "No hotels found for the given location and dates. "
                               "Try a broader location name (e.g. 'Paris' instead of a specific address) "
                               "or different check-in/check-out dates."
                }

            return cleaned_results

        except Exception as e:
            return {"error": f"Hotel search failed: {str(e)}"}