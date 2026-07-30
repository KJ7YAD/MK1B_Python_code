# altimeter_python
Python code for the RP2040 altimeter

Copy the contents of the src folder onto the CIRCUIT_PY folder of the altimeter.

## Target hardware

Pin assignments in `src/pyro.py` and `src/code.py` match the Pyro MK1B flight
computer (RP2040, [pyro_fw](https://github.com/n9wxu/pyro_fw)). The pressure
sensor (MS5607-02BA03 or BMP280) is auto-detected at boot: `pyro.py` tries the
MS5607 I2C pins first, and falls back to the BMP280 I2C pins if that sensor
doesn't respond. `src/lib/ms5607.py` is a minimal driver written for this
project, since no ready-made CircuitPython MS5607 library exists.
