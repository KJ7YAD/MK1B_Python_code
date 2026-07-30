# ms5607.py -- minimal CircuitPython I2C driver for the TE Connectivity
# MS5607-02BA03 barometric pressure sensor.
#
# The Pyro MK1B board (https://github.com/n9wxu/pyro_fw) may be built with
# either an MS5607 or a BMP280 pressure sensor; the two are auto-detected at
# boot. No ready-made CircuitPython/MicroPython MS5607 driver exists, so this
# is a small from-scratch implementation of the datasheet formula, exposing
# the same `.pressure` (hPa) / `.temperature` (deg C) property interface used
# by adafruit_bmp280 so callers in pyro.py don't need to care which sensor is
# actually present.
#
# Reference: TE Connectivity MS5607-02BA03 datasheet, section
# "PRESSURE AND TEMPERATURE CALCULATION".

import time

_CMD_RESET = 0x1E
_CMD_ADC_READ = 0x00
_CMD_CONVERT_D1_OSR4096 = 0x48  # pressure conversion, max OSR
_CMD_CONVERT_D2_OSR4096 = 0x58  # temperature conversion, max OSR
_CMD_PROM_READ = 0xA0  # + 2 * coefficient index (0..7)

# OSR=4096 conversion takes up to 9.04ms per the datasheet; pad a little.
_CONVERT_DELAY_S = 0.010


class MS5607:
    def __init__(self, i2c, address=0x77):
        self._i2c = i2c
        self._address = address
        self.reset()
        time.sleep(0.003)  # reset sequence needs >=2.8ms before PROM is valid
        self._coeff = self._read_prom()

    # --- low level I2C helpers ------------------------------------------

    def _write_cmd(self, cmd):
        while not self._i2c.try_lock():
            pass
        try:
            self._i2c.writeto(self._address, bytes([cmd]))
        finally:
            self._i2c.unlock()

    def _read_after(self, cmd, nbytes):
        buf = bytearray(nbytes)
        while not self._i2c.try_lock():
            pass
        try:
            self._i2c.writeto_then_readfrom(self._address, bytes([cmd]), buf)
        finally:
            self._i2c.unlock()
        return buf

    def reset(self):
        self._write_cmd(_CMD_RESET)

    def _read_prom(self):
        coeff = [0] * 8
        for i in range(8):
            buf = self._read_after(_CMD_PROM_READ + 2 * i, 2)
            coeff[i] = (buf[0] << 8) | buf[1]
        # C1 (word 1) should never be 0x0000 or 0xFFFF on a real sensor.
        if coeff[1] in (0x0000, 0xFFFF):
            raise RuntimeError("MS5607 PROM read invalid (no sensor?)")
        return coeff

    def _read_raw(self, convert_cmd):
        self._write_cmd(convert_cmd)
        time.sleep(_CONVERT_DELAY_S)
        buf = self._read_after(_CMD_ADC_READ, 3)
        return (buf[0] << 16) | (buf[1] << 8) | buf[2]

    # --- datasheet compensation formula ----------------------------------

    def _measure(self):
        d1 = self._read_raw(_CMD_CONVERT_D1_OSR4096)  # raw pressure
        d2 = self._read_raw(_CMD_CONVERT_D2_OSR4096)  # raw temperature

        c1, c2, c3, c4, c5, c6 = self._coeff[1:7]

        dT = d2 - (c5 << 8)
        temp = 2000 + ((dT * c6) >> 23)

        off = (c2 << 17) + ((c4 * dT) >> 6)
        sens = (c1 << 16) + ((c3 * dT) >> 7)

        if temp < 2000:
            t2 = (dT * dT) >> 31
            off2 = (61 * (temp - 2000) ** 2) >> 4
            sens2 = 2 * (temp - 2000) ** 2
            if temp < -1500:
                off2 += 15 * (temp + 1500) ** 2
                sens2 += 8 * (temp + 1500) ** 2
        else:
            t2 = 0
            off2 = 0
            sens2 = 0

        temp -= t2
        off -= off2
        sens -= sens2

        p = (((d1 * sens) >> 21) - off) >> 15

        return p / 100.0, temp / 100.0  # hPa, deg C

    # --- public interface (mirrors adafruit_bmp280) ----------------------

    @property
    def pressure(self) -> float:
        p, _ = self._measure()
        return p

    @property
    def temperature(self) -> float:
        _, t = self._measure()
        return t
