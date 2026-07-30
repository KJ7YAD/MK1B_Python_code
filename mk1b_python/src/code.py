# code.py -- flight firmware with test-mode jumper + status beeps + on-pad indicator.
#
# Hardware (Pyro MK1B, see https://github.com/n9wxu/pyro_fw README):
#   GP16  -> buzzer (GPIO on/off, external circuit produces tone).
#   GP8   -> test input. Dedicated active-low pin with internal pull-up
#            (shared pin function with I2C0 SDA, which is otherwise unused
#            by this firmware). Grounding it (jumper/switch to GND) reads
#            LOW. Unlike the previous board, this is not shared with the
#            buzzer output, so it can be sampled at any time.
#
# Boot dispatch:
#   jumper installed at boot  -> Quark-style pyro ground test, never returns.
#   jumper not installed      -> status beeps, then flight loop.
#
# Continuity paradigm (departs from Quark):
#   A channel that fails continuity at boot is flown DISARMED -- the flight
#   loop will not fire it. Both channels disarmed = data-only flight.
#   Supports single-pyro rocket configurations.

import time
import os
import gc
import board
from digitalio import DigitalInOut, Direction, Pull
from config import configuration
from altimeter import makeAltitude

import save
import pyro


# --- buzzer + jumper hardware ------------------------------------------------

buzzer = DigitalInOut(board.GP16)
buzzer.direction = Direction.OUTPUT
buzzer.value = False

jumper = DigitalInOut(board.GP8)
jumper.direction = Direction.INPUT
jumper.pull = Pull.UP


# --- blocking buzzer primitives ----------------------------------------------

def buzz_n(n, on_s=0.15, off_s=0.15, post_pause_s=0.5):
    for _ in range(n):
        buzzer.value = True
        time.sleep(on_s)
        buzzer.value = False
        time.sleep(off_s)
    if post_pause_s:
        time.sleep(post_pause_s)


def buzz_long(s=1.0):
    buzzer.value = True
    time.sleep(s)
    buzzer.value = False


def buzz_chirp(duration_s, on_s=0.03, off_s=0.03):
    end = time.monotonic() + duration_s
    while time.monotonic() < end:
        buzzer.value = True
        time.sleep(on_s)
        buzzer.value = False
        time.sleep(off_s)


# --- sustained on-pad ready indicator (non-blocking) --------------------------

ready_pattern = None
ready_pattern_total = 0.0
ready_start_time = 0.0


def make_ready_pattern(p1_armed, p2_armed):
    if p1_armed and p2_armed:
        # Both armed: rapid uniform blip.
        return [(0.05, True), (0.20, False)]

    pattern = []
    if p1_armed or p2_armed:
        # One armed: brief tease of the "ready" sound...
        for _ in range(4):
            pattern.append((0.05, True))
            pattern.append((0.20, False))
        pattern.append((0.40, False))

    # ...then the bad-channel code(s). Quark convention: 4 = drogue, 5 = main.
    if not p1_armed:
        for _ in range(4):
            pattern.append((0.15, True))
            pattern.append((0.15, False))
        pattern.append((0.50, False))
    if not p2_armed:
        for _ in range(5):
            pattern.append((0.15, True))
            pattern.append((0.15, False))
        pattern.append((0.50, False))

    pattern.append((0.80, False))
    return pattern


def init_ready_indicator(p1_armed, p2_armed):
    global ready_pattern, ready_pattern_total, ready_start_time
    ready_pattern = make_ready_pattern(p1_armed, p2_armed)
    ready_pattern_total = sum(d for d, _ in ready_pattern)
    ready_start_time = time.monotonic()


def update_ready_indicator():
    if ready_pattern is None:
        return
    elapsed = (time.monotonic() - ready_start_time) % ready_pattern_total
    acc = 0.0
    for duration, state in ready_pattern:
        acc += duration
        if elapsed < acc:
            buzzer.value = state
            return


def stop_ready_indicator():
    global ready_pattern
    ready_pattern = None
    buzzer.value = False


# --- jumper sense ------------------------------------------------------------

def jumper_installed():
    # Dedicated active-low test input (GP8) with internal pull-up; reads
    # LOW when the jumper/switch to GND is installed.
    return not jumper.value


def wait_for_jumper(target_installed):
    # Buzzer is idle-low during test-mode wait phases -- readings are valid.
    while True:
        time.sleep(0.05)
        if jumper_installed() == target_installed:
            time.sleep(0.05)
            if jumper_installed() == target_installed:
                return


# --- per-channel continuity ---------------------------------------------------
#
# Matches pyro_fw's src/pyro.c: energise the common enable, settle 10ms, then
# classify each channel's ADC reading into open / good / shorted zones (a
# HIGH reading is an open circuit -- no igniter -- not continuity). The C
# firmware's ADC is 12-bit (0-4095); CircuitPython's AnalogIn is 16-bit
# (0-65535), so its ADC_OPEN_THRESHOLD (3800) and ADC_SHORT_THRESHOLD (50)
# are scaled up by 16x here.

PYRO_ADC_OPEN_THRESHOLD = 3800 * 16  # above this = open circuit (no igniter)
PYRO_ADC_SHORT_THRESHOLD = 50 * 16  # below this = dead short


def per_channel_continuity(p):
    p.fire1.value = False
    p.fire2.value = False
    p.pyro_low.value = True
    time.sleep(0.01)
    s1 = p.sense1.value
    s2 = p.sense2.value
    p.pyro_low.value = False
    p1_ok = PYRO_ADC_SHORT_THRESHOLD <= s1 <= PYRO_ADC_OPEN_THRESHOLD
    p2_ok = PYRO_ADC_SHORT_THRESHOLD <= s2 <= PYRO_ADC_OPEN_THRESHOLD
    return p1_ok, p2_ok


# --- shared status report (used by test mode and flight mode entry) ----------

def beep_continuity(p1_ok, p2_ok):
    if p1_ok and p2_ok:
        print("continuity: both OK")
        buzz_n(2, post_pause_s=0.8)
    else:
        if not p1_ok:
            print("continuity: PYRO 1 BAD")
            buzz_n(4, on_s=0.2, off_s=0.2, post_pause_s=0.8)
        if not p2_ok:
            print("continuity: PYRO 2 BAD")
            buzz_n(5, on_s=0.2, off_s=0.2, post_pause_s=0.8)


def baro_fail(reason):
    # Shared by both detection points: pyroHw() failing to find any sensor
    # at all, and a later readPressure() failing after one was found. Same
    # failure category either way -- no reliable baro, don't fly.
    print("baro FAIL:", reason)
    while True:
        buzz_n(3, on_s=0.2, off_s=0.2, post_pause_s=1.0)


# --- test mode ---------------------------------------------------------------

def test_one_channel(label, fire_fn, safe_fn):
    print(label, ": remove jumper to arm")
    wait_for_jumper(False)
    print(label, ": armed, re-install jumper to fire")
    wait_for_jumper(True)
    print(label, ": countdown")
    for i in range(5, 0, -1):
        print("  T-", i)
        buzz_n(1, on_s=0.1, off_s=0.0, post_pause_s=0.9)
    print(label, ": FIRE")
    buzz_long(0.3)
    fire_fn()
    time.sleep(1.0)
    safe_fn()
    print(label, ": fired")
    for _ in range(3):
        buzz_n(2, on_s=0.1, off_s=0.1, post_pause_s=0.7)


def run_test_mode(p):
    print("=== TEST MODE ===")
    buzz_long(1.0)
    time.sleep(1.0)

    p1_ok, p2_ok = per_channel_continuity(p)
    beep_continuity(p1_ok, p2_ok)
    time.sleep(1.5)

    test_one_channel("pyro 1", p.firePyro1, p.safeAllPyros)
    test_one_channel("pyro 2", p.firePyro2, p.safeAllPyros)

    print("test complete -- heartbeat until power-off")
    while True:
        buzz_n(1, on_s=0.05, off_s=0.0, post_pause_s=1.95)


# --- flight-mode status beeps -------------------------------------------------

def run_status_beeps(p):
    print("=== STATUS CHECK ===")
    buzz_long(1.0)
    time.sleep(1.0)

    # Baro sensor sanity -- halt on failure (no pressure sensor = no flight).
    try:
        _ = p.readPressure()
        print("baro: OK")
    except Exception as e:
        baro_fail(e)

    # Per-channel continuity. Failed channels are flown disarmed -- the
    # flight loop checks these flags before firing.
    p1_ok, p2_ok = per_channel_continuity(p)
    beep_continuity(p1_ok, p2_ok)
    time.sleep(1.0)

    print("armed channels: pyro1=", p1_ok, " pyro2=", p2_ok)
    buzz_chirp(3.0)
    time.sleep(0.5)
    return p1_ok, p2_ok


# --- pyro hardware init + boot dispatch --------------------------------------

try:
    pyro = pyro.pyroHw()
except Exception as e:
    baro_fail(e)

# Buzzer starts idle-low; settle before sampling GP8 for the jumper check.
buzzer.value = False
time.sleep(0.01)

if jumper_installed():
    print("jumper installed at boot -> TEST MODE")
    run_test_mode(pyro)
    # run_test_mode never returns
else:
    print("jumper not installed -> FLIGHT MODE")
    pyro1_armed, pyro2_armed = run_status_beeps(pyro)


# === FLIGHT CODE (EMA scaffolding preserved from current code.py) ============

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

EmaCount = 0  # samples used in the EMA filter; reset at launch detect.
EmaFilterFactor = 0.


def getTimeMs() -> int:
    now = time.monotonic_ns() - startTime
    return now / 1000000


def ExponentialMovingAverage(latest_altitude_sample, emaAltitude, EmaCount, EmaFilterFactor=0.8):
    emaAltitude = (latest_altitude_sample * (EmaFilterFactor / (1 + EmaCount))) + (emaAltitude * (1 - (EmaFilterFactor / (1 + EmaCount))))
    return emaAltitude


print("starting the loop")

while logging:
    update_ready_indicator()
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
            # sit on the pad
            if not armed:
                if now > 100:
                    pyro.speak("call n9rgk")
                    if pyro1_armed and pyro2_armed:
                        pyro.speak("ready")
                    elif pyro1_armed:
                        pyro.speak("pyro1 only")
                    elif pyro2_armed:
                        pyro.speak("pyro2 only")
                    else:
                        pyro.speak("no pyros")
                    print("armed")
                    armed = True
                    lastTalk = now
                    init_ready_indicator(pyro1_armed, pyro2_armed)
            else:
                # launch detector
                # Debug code
                # launchDetectAltitude = 100
                # end Debug code
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
                    stop_ready_indicator()

                    # EmaCount = 0 # Two-part reset the average starting at launch altitude.
                    # emaAltitude = ExponentialMovingAverage(altitude, emaAltitude, EmaCount, EmaFilterFactor)
        else:
            # apogee detector.  peak is 10 ft higher than current altitude
            if not apogee and ((peakAboveGround - AboveGround) > 10):
                apogee = True
                print("Appogee Detected")
                pyroFireTime = now
                pyro.speak("apogee")
                pyro.speak("altitude " + str(int((AboveGround) / 100) * 100))
                if pyro1_armed:
                    print("altitude above ground:" + str(AboveGround), end="")
                    pyro.firePyro1()
                    pyro1Index = len(mission_data)
                else:
                    print("apogee detected, pyro1 disarmed")
                    pyro.speak("pyro1 disarmed")
                lastTalk = now
            else:
                if apogee and not noPyro2 and AboveGround < 500:
                    if pyro2_armed:
                        print("altitude " + str(AboveGround) + " : ", end="")
                        pyro.firePyro2()
                        pyro2Index = len(mission_data)
                    else:
                        print("main alt reached, pyro2 disarmed")
                        pyro.speak("pyro2 disarmed")
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
