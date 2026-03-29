import os
from agent_file.utils.weather_info import WeatherForecastTool
from langchain.tools import tool
from dotenv import load_dotenv

load_dotenv()

def get_weather_tools():
    """Return a list of weather tools."""
    api_key = os.environ.get("OPENWEATHERMAP_API_KEY")
    weather_service = WeatherForecastTool(api_key)

    @tool
    def get_current_weather(city: str) -> str:
        """Get current weather for a city"""
        weather_data = weather_service.get_current_weather(city)
        if weather_data:
            temp = weather_data.get('main', {}).get('temp', 'N/A')
            desc = weather_data.get('weather', [{}])[0].get('description', 'N/A')
            return f"Current weather in {city}: {temp}°C, {desc}"
        return f"Could not fetch weather for {city}"

    @tool
    def get_weather_forecast(city: str) -> str:
        """Get 5-day weather forecast for a city"""
        forecast_data = weather_service.get_forecast_weather(city)
        if forecast_data and 'list' in forecast_data:
            forecast_summary = []
            for item in forecast_data['list']:
                date = item['dt_txt'].split(' ')[0]
                temp = item['main']['temp']
                desc = item['weather'][0]['description']
                forecast_summary.append(f"{date}: {temp}°C, {desc}")
            return f"Weather forecast for {city}:\n" + "\n".join(forecast_summary)
        return f"Could not fetch forecast for {city}"

    return [get_current_weather, get_weather_forecast]