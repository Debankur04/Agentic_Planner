import json
import os

class StationResolver:
    def __init__(self, path=None):
        if path is None:
            base_dir = os.path.dirname(__file__)
            path = os.path.join(base_dir, "stations.json")

        with open(path, "r") as f:
            data = json.load(f)

        self.code_to_name = data["code_to_name"]
        self.name_to_code = data["name_to_code"]

    def get_code(self, name: str):
        return self.name_to_code.get(name.lower())

    def get_name(self, code: str):
        return self.code_to_name.get(code)