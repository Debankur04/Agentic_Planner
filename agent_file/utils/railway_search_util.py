from dotenv import  load_dotenv
import os
import requests
from agent_file.utils.station_resolver.stations_revolver import StationResolver


load_dotenv()
StationResolver = StationResolver()

class RailwaySearchTool:
    def __init__(self):
        self.x_api_key = os.getenv("RAILWAY_RADAR_API_KEY")
        if not self.x_api_key:
            raise RuntimeError(
                "Railway Radar Api Key is not set. Add it to your .env file. "
                "Get a key at https://railradar.in/"
            )

    def find_routes(self, source,destination):
        try:
            response = requests.get(
            "https://api.railradar.org/api/v1/trains/between",
            headers={
                "Accept": "application/json",
                "X-API-Key": self.x_api_key
            },
            params={
                "from": source,
                "to": destination
            }
            )
            return response.json()
        except Exception as e:
            return {"error": f"Train search failed: {str(e)}"}

    def estimate_delay(self, train_id):
        try:
            response = requests.get(
                f"https://api.railradar.org/api/v1/trains/{train_id}/average-delay",
                headers = {
                "Accept": "application/json",
                "X-API-Key": self.x_api_key
                }
            )
            return response.json()

        except Exception as e:
            return {"error": f"Train delay search failed: {str(e)}"}


    def live_train_update(self, train_id):
        try:
            response = requests.get(
                f"https://api.railradar.org/api/v1/trains/{train_id}",
                headers={
                    "Accept": "application/json",
                    "X-API-Key" : self.x_api_key
                },
                params={
                    "journeyDate": "",
                    "dataType": "full",
                    "dataProvider": "railradar",
                    "userId": ""
                }
            )
            return response.json()
        except Exception as e:
            return {"error": f"Train live search failed: {str(e)}"}

    def get_schedule(self,train_id,journeyDate):
        try:
            response = requests.get(
            f"https://api.railradar.org/api/v1/trains/{train_id}/schedule",
                headers={
                    "Accept": "application/json",
                    "X-API-Key": self.x_api_key
                },
            params={
              "journeyDate": journeyDate
            }
        )
            return response.json()
        except Exception as e:
            return {"error": f"Train schedule search failed: {str(e)}"}

    def get_code_station(self,source,destination):
        try:
            from_code =StationResolver.get_code(source)
            to_code = StationResolver.get_code(destination)
            return from_code,to_code
        except Exception as e:
            return {"error": f"Station code search failed: {str(e)}"}