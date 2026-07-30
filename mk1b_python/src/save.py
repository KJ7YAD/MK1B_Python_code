import os


# simple function to test if a file is present
def exists(f) -> bool:
    os.sync()
    if f in os.listdir("/"):
        print("found " + f)
        return True
    else:
        return False


def write(
    filename,
    mission_data,
    mission_time,
    peakAGL,
    pyro1Index,
    pyro2Index,
    temperature,
    dT,
):
    file = open(filename, "wt")
    print("Log File Created")
    file.write("mission time = " + str(mission_time) + "\n")
    file.write("Maximum Altitude = " + str(peakAGL) + "\n")
    file.write("temp," + str(temperature) + "\n")
    file.write("dt," + str(dT) + "\n")
    file.write("sample number, pressure\n")
    count = 0
    for d in mission_data:
        file.write(str(count) + "," + str(d))
        if count == pyro1Index:
            file.write(", fire pyro 1")
        if count == pyro2Index:
            file.write(", fire pyro 2")
        file.write("\n")
        count += 1
    file.flush()
    file.close()
