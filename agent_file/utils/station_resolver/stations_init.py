import requests
import json
import os
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("RAILWAY_RADAR_API_KEY")  # ✅ FIXED

def fetch_and_save_stations():
    response = requests.get(
        "https://api.railradar.org/api/v1/stations/all-kvs",
        headers={
            "X-API-Key": API_KEY,
            "Accept": "application/json"
        }
    )

    print("STATUS:", response.status_code)
    print("RAW RESPONSE:", response.text[:500])

    res_json = response.json()

    if isinstance(res_json, dict) and "data" in res_json:
        data = res_json["data"]
    else:
        data = res_json

    print("Parsed data:", data[:5] if isinstance(data, list) else data)

    code_to_name = {}
    name_to_code = {}

    for item in data:
        if isinstance(item, list) and len(item) >= 2:
            code, name = item[0], item[1]
            code_to_name[code] = name
            name_to_code[name.lower()] = code

    with open("stations.json", "w") as f:
        json.dump({
            "code_to_name": code_to_name,
            "name_to_code": name_to_code
        }, f, indent=2)

    print("✅ Station data saved")


fetch_and_save_stations()