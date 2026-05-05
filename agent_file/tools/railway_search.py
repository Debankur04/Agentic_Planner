from agent_file.utils.railway_search_util import RailwaySearchTool
from langchain.tools import tool


def get_railway_search_tool():
    search = RailwaySearchTool()

    @tool
    def find_routes(source: str, destination: str):
        """
        Find available trains between two stations.

        Args:
            source (str): Source station name (e.g., "Kolkata", "Sealdah")
            destination (str): Destination station name (e.g., "Delhi", "Mumbai")

        Returns:
            JSON containing list of trains with trainNumber, trainName, timings, etc.
            This output is used to extract train_id (trainNumber) for further queries.
        """
        return search.find_routes(source, destination)

    @tool
    def estimate_delay(train_id: str):
        """
        Get the average delay information for a specific train.

        Args:
            train_id (str): Train number (e.g., "12301")

        Returns:
            JSON containing average delay statistics for the train.
            Useful for deciding reliability of a train.
        """
        return search.estimate_delay(train_id)

    @tool
    def live_train_update(train_id: str):
        """
        Get real-time live status of a train.

        Args:
            train_id (str): Train number

        Returns:
            JSON containing live location, current status, delays, and running information.
        """
        return search.live_train_update(train_id)

    @tool
    def get_schedule(train_id: str, journeyDate: str):
        """
        Get the full schedule of a train for a given date.

        Args:
            train_id (str): Train number
            journeyDate (str): Date in format YYYY-MM-DD

        Returns:
            JSON containing station-wise schedule including arrival and departure times.
        """
        return search.get_schedule(train_id, journeyDate)

    @tool
    def get_code_station(source: str, destination: str):
        """
        Convert station names into station codes.

        Args:
            source (str): Source station name (e.g., "Kolkata")
            destination (str): Destination station name (e.g., "Delhi")

        Returns:
            Tuple (from_code, to_code) like ("HWH", "NDLS").
            Used internally before calling train search APIs.
        """
        return search.get_code_station(source, destination)

    return [
        find_routes,
        estimate_delay,
        live_train_update,
        get_schedule,
        get_code_station,
    ]