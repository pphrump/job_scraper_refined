import requests
from datetime import date, timedelta
from urllib.parse import quote

LOCATION_CACHE = {}

def query_nominatim(city, state):
    city_encoded = quote(city)
    state_encoded = quote(state)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'application/json',
        'Referer': 'https://www.openstreetmap.org'
    }
    url = (
        f"https://nominatim.openstreetmap.org/search?"
        f"city={city_encoded}&state={state_encoded}&country=USA&format=json"
    )
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    return res.json()

def get_lat_lon(city, state, logger=print):
    cache_key = (city.lower(), state.lower())
    if cache_key in LOCATION_CACHE:
        logger(f"[CACHE HIT] {city}, {state}")
        return LOCATION_CACHE[cache_key]

    # 1. Try original city name
    logger(f"[TRY] {city}, {state}")
    data = query_nominatim(city, state)
    if data:
        lat, lon = float(data[0]['lat']), float(data[0]['lon'])
        LOCATION_CACHE[cache_key] = (lat, lon)
        logger(f"[SUCCESS] Found using original name: {city}")
        return lat, lon

    # 2. If  fail
    logger(f"[FAIL] Could not find location for {city}, {state}")
    raise Exception(f"Location not found for {city}, {state}")

def get_climate_data(city, state):
    today = date.today()
    start_date = today - timedelta(days=365)
    lat, lon = get_lat_lon(city, state)
    climate_url = (
        f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
        f"&start_date={start_date}&end_date={today}"
        "&daily=temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum"
        "&temperature_unit=fahrenheit&precipitation_unit=inch&timezone=auto"
    )
    res = requests.get(climate_url)
    res.raise_for_status()
    data = res.json()
    return process_climate_data(data, city, state)

# job_scraper_app/utils/climate.py
def safe_avg(data):
    valid_data = [x for x in data if x is not None]
    return sum(valid_data) / len(valid_data) if valid_data else 0

def safe_max(data):
    valid_data = [x for x in data if x is not None]
    return max(valid_data) if valid_data else 0

def safe_min(data):
    valid_data = [x for x in data if x is not None]
    return min(valid_data) if valid_data else 0

def safe_count_min(data, threshold=31):
    return len([x for x in data if x is not None and x < threshold])

def safe_count_max(data, threshold=85):
    return len([x for x in data if x is not None and x >= threshold])

def process_climate_data(weather_data, city, state):
    if 'daily' not in weather_data:
        raise ValueError("Missing 'daily' data in weather API response.")

    daily = weather_data['daily']
    temps_mean = daily.get('temperature_2m_mean', [])
    temps_max = daily.get('temperature_2m_max', [])
    temps_min = daily.get('temperature_2m_min', [])
    precip_sum = daily.get('precipitation_sum', [])
    num_days = len(daily.get('time', []))

    total_hdd = total_cdd = total_precip = 0

    for i in range(num_days):
        mean_temp = temps_mean[i] if i < len(temps_mean) else None
        precip = precip_sum[i] if i < len(precip_sum) else None

        if mean_temp is not None:
            total_hdd += max(0, 65 - mean_temp)
            total_cdd += max(0, mean_temp - 65)
        if precip is not None:
            total_precip += precip

    return {
        "city": city,
        "state": state,
        "total_hdd": round(total_hdd, 2),
        "total_cdd": round(total_cdd, 2),
        "total_precipitation": round(total_precip, 2),
        "avg_max_temp": round(safe_max(temps_max), 2),
        "avg_min_temp": round(safe_min(temps_min), 2),
        "avg_mean_temp": round(safe_avg(temps_mean), 2),
        "days_below_30": safe_count_min(temps_min, threshold=31),
        "days_above_85": safe_count_max(temps_max, threshold=85)
    }
