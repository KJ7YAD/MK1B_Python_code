# port_beep_test.py -- hardware bring-up diagnostic, NOT part of the flight app.
#
# Cycles through the port(s) likely to carry the buzzer on this board and
# drives each one as a digital output for a short beep pattern, printing the
# port name to the serial console before each attempt.
#
# Candidate list source: the pyro_fw README pin assignment table
# (https://github.com/n9wxu/pyro_fw/blob/main/README.md), cross-checked
# against pyro.py/code.py in this project. The README documents exactly one
# pin for the buzzer, under "User Interface":
#   GPIO 16 -- Buzzer control ("GPIO on/off, external circuit produces tone")
# Every other GPIO the README lists is already assigned to a specific other
# function (UART0, the two pressure-sensor I2C options, the jumper test
# input, pyro enable/fault/continuity-sense, or the status LED), so none of
# those are plausible buzzer locations and they are not included here.
#
# How to run: copy this file onto the board as code.py (temporarily
# replacing the flight firmware), or paste it into the REPL over the
# board's serial port.

import board
import digitalio
import time

BEEP_ON_S = 0.12
BEEP_OFF_S = 0.12
BEEPS_PER_PORT = 2
PAUSE_BETWEEN_PORTS_S = 0.4
CYCLES = 5  # how many times to repeat the candidate list

# Ports likely to have the buzzer, per the pyro_fw README (see module docstring).
CANDIDATE_PORTS = (
    ("GP16", board.GP16),  # documented buzzer control pin
)


def beep_port(name, pin):
    print("Testing port: " + name)
    try:
        dio = digitalio.DigitalInOut(pin)
        dio.direction = digitalio.Direction.OUTPUT
    except Exception as e:
        print("  skipped (" + str(e) + ")")
        return
    try:
        for _ in range(BEEPS_PER_PORT):
            dio.value = True
            time.sleep(BEEP_ON_S)
            dio.value = False
            time.sleep(BEEP_OFF_S)
    except Exception as e:
        print("  error driving port: " + str(e))
    finally:
        dio.deinit()


def main():
    print("Candidate ports: " + ", ".join(name for name, _ in CANDIDATE_PORTS))
    for cycle in range(CYCLES):
        print("-- cycle " + str(cycle + 1) + " of " + str(CYCLES) + " --")
        for name, pin in CANDIDATE_PORTS:
            beep_port(name, pin)
            time.sleep(PAUSE_BETWEEN_PORTS_S)
    print("Done -- all candidate ports tested.")


main()
