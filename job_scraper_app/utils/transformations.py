# transformations.py
def normalize_location(city):
    for transform in TRANSFORMATIONS:
        city = transform(city)
    return city.strip()

def saint_to_st(city):
    return city.replace("Saint", "St").replace("SAINT", "St").replace("saint", "St")

def mount_to_mt(city):
    return city.replace("Mount", "Mt").replace("MOUNT", "Mt").replace("mount", "Mt")

def fort_to_ft(city):
    return city.replace("Fort", "Ft").replace("FORT", "Ft").replace("fort", "Ft")

def remove_punctuation(city):
    return city.replace(".", "").replace("-", " ")

def remove_city_suffix(city):
    if city.lower().endswith(" city"):
        return city[:-5]
    return city

TRANSFORMATIONS = [
    saint_to_st,
    mount_to_mt,
    fort_to_ft,
    remove_punctuation,
    remove_city_suffix,
]
