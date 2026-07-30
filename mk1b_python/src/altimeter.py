def __init__(self):
    pass


# accepts hecaPascals and returns feet
def makeAltitude(p) -> float:
    # use the sea level and 15C to compute the current altitude
    seaLevelPressure = 1013.25
    temperature = 15.0 + 273.15
    altitude = ((((seaLevelPressure / p) ** (1 / 5.257)) - 1) * temperature) / 0.0065
    return altitude * 3.28084
