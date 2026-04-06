import os
import serpapi
from dotenv import load_dotenv

load_dotenv()


class HotelSearchTool:
    """Tool to find hotels for a region"""

    def __init__(self):
        self.client = serpapi.Client(
            api_key=os.getenv("SERP_API_KEY")
        )

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

            return cleaned_results

        except Exception as e:
            return {"error": str(e)}