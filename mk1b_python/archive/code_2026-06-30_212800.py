import time
import os
import gc
from config import configuration
from altimeter import makeAltitude

import save
import pyro

pyro = pyro.pyroHw()

config = configuration()

loopTime = 0

pyro.ledOn()

history = config.getHistory()
launchDetectAltitude = config.getLaunchDetection()

ramLimit = False
flying = False
logging = True
launchTime = 0
pyroFireTime = 0
apogee = False
temperature = pyro.readTemperature()

# 200 data points to seed the pressure sum
mission_data = []
for i in range(0, history):
    p = pyro.readPressure()
    mission_data.append(p)
    print(str(p) + " : " + str(makeAltitude(p)) + " : " + str(len(mission_data)))
    time.sleep(0.050)

launchAltitude = makeAltitude(sum(mission_data[-history:]) / history)
emaAltitude = launchAltitude
peakAboveGround = 0

startTime = time.monotonic_ns()
armed = False
noPyro2 = False
previousSample = 0
lastTalk = 0
pyro1Index = 0
pyro2Index = 0

EmaCount = 0 #this counter counds samples used in the EMA filter. This will be reset when launch is detected.
EmaFilterFactor = 0.

def getTimeMs() -> int:
    now = time.monotonic_ns() - startTime
    return now / 1000000

def ExponentialMovingAverage(latest_altitude_sample, emaAltitude, EmaCount, EmaFilterFactor=0.8):
    emaAltitude = (latest_altitude_sample * (EmaFilterFactor / (1 + EmaCount))) + (emaAltitude * (1 - (EmaFilterFactor / (1 + EmaCount))))
    return emaAltitude


print("starting the loop")

while logging:
    now = getTimeMs()
    if now - previousSample > 50:
        previousSample = now

        try:
            p = pyro.readPressure()
            mission_data.append(p)
        except Exception as e:
            print("exception : " + str(e))
            ramLimit = True
            logging = False

        # avgAltitude = makeAltitude(sum(mission_data[-history:]) / history) // This version is a basic average.
        # Exponential Moving Agerage
        # avgAltitude = ExponentialMovingAverage(altitude, emaAltitude, EmaCount, EmaFilterFactor)
        # print(emaAltitude)
        # EmaCount = EmaCount + 1

        avgAltitude = makeAltitude(sum(mission_data[-history:]) / history)
        altitude = makeAltitude(sum(mission_data[-3:]) / 3)

        print(altitude)
        # print(avgAltitude)

        AboveGround = altitude - launchAltitude
        avgAboveGround = avgAltitude - launchAltitude

        if AboveGround > peakAboveGround:
            peakAboveGround = AboveGround

        if not flying:
            while len(mission_data) > history:
                mission_data.pop(0)
            # sit on the pad for 1 seconds
            if not armed:
                if now > 100:
                    pyro.speak("call n9rgk")
                    if pyro.pyroTest():
                        pyro.speak("ready")
                        print("armed")
                        armed = True
                    else:
                        pyro.speak("fail")
                        print("pyro fail")
                    lastTalk = now
                    armed = True
            else:
                # launch detector
                # Debug code
                # launchDetectAltitude = 100
                #end Debug code
                if abs(avgAboveGround) > launchDetectAltitude and flying == False:
                    launchTime = now
                    pyro.speak("launch")
                    lastTalk = now
                    print("Launch")
                    print("Altitude : " + str(AboveGround))
                    print("avgAltitude : " + str(avgAboveGround))
                    print("Launch Altitide : " + str(launchAltitude))
                    print("Launch Time Set To: ", launchTime)
                    flying = True

                    # EmaCount = 0 # This line and the next is a two part reset the average starting at launch altitude. This may not be neccisary.
                    # emaAltitude = ExponentialMovingAverage(altitude, emaAltitude, EmaCount, EmaFilterFactor)#Repriming the average with the launch altitude
        else:
            # apogee detector.  peak is 10 ft higher than current altitude
            if not apogee and ((peakAboveGround - AboveGround) > 10):
                apogee = True
                print("Appogee Detected")
                pyroFireTime = now
                pyro.speak("apogee")
                pyro.speak("altitude " + str(int((AboveGround) / 100) * 100))
                print("altitude above ground:" + str(AboveGround), end="")
                pyro.firePyro1()
                pyro1Index = len(mission_data)
                lastTalk = now
            else:
                if apogee and AboveGround < 500:
                    print("altitude " + str(AboveGround) + " : ", end="")
                    pyro.firePyro2()
                    pyro2Index = len(mission_data)
                    noPyro2 = True
                    pyroFireTime = now

                if pyroFireTime and now - pyroFireTime > 500000000:
                    pyro.safeAllPyros()
                    pyroFireTime = 0

                if now - lastTalk > 2000:
                    print("Sking altitude above ground: " + str(int((AboveGround) / 100) * 100))
                    pyro.speak("altitude " + str(int((AboveGround) / 100) * 100))
                    lastTalk = now
            # landing detector
            if avgAboveGround < 5.0:
                logging = False
                pyro.safeAllPyros()

            # maximum flight detector 10 minutes
            if now - launchTime > 600000:
                print("out of time")
                logging = False

flying = False
mission_time = float((now - launchTime)) / 1000.0
if len(mission_data):
    dT = mission_time / len(mission_data)
else:
    dT = 0.05

pyro.speak("touchdown")
print(".")
print("landed")
print("Altitude : " + str(AboveGround))
print("avgAltitude : " + str(avgAboveGround))
print("mission elapsed time : " + str(mission_time))
print("maximum Altitude : " + str(peakAboveGround))
print("saving the data")

save.write(
    "data.csv",
    mission_data,
    mission_time,
    peakAboveGround,
    pyro1Index,
    pyro2Index,
    temperature,
    dT,
)

pyro.ledOff()

pyro.finish()
