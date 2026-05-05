import requests
import json
import os
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("RAILWAY_RADAR_API_KEY")

def fetch_and_save_stations():
    response = requests.get(
        "https://api.railradar.org/api/v1/stations",
        headers={
            "x-api-key": API_KEY,
            "Accept": "application/json"
        }
    )

    res_json = response.json()

    # ✅ Handle both possible formats
    if isinstance(res_json, dict) and "data" in res_json:
        data = res_json["data"]
    else:
        data = res_json  # fallback if API returns raw list

    code_to_name = {}
    name_to_code = {}

    for item in data:
        if isinstance(item, list) and len(item) >= 2:
            code, name = item[0], item[1]

            code_to_name[code] = name
            name_to_code[name.lower()] = code

    station_data = {
        "code_to_name": code_to_name,
        "name_to_code": name_to_code
    }

    with open("agent_file/utils/station_resolver/stations.json", "w") as f:
        json.dump(station_data, f, indent=2)

    print("✅ Station data saved successfully")


fetch_and_save_stations()