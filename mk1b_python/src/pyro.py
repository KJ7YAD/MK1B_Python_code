import board
from digitalio import DigitalInOut, Direction, Pull
import analogio
import busio
import adafruit_bmp280
from ms5607 import MS5607
import time

SENSOR_POWERUP_DELAY_S = 0.5  # settle time for sensor supply rail before I2C probing


class pyroHw:
    # Hardware pin map for the Pyro MK1B flight computer (RP2040).
    # See https://github.com/n9wxu/pyro_fw README "Pin Assignments".
    def __init__(self):
        # Communication
        self.tx_pin = board.GP0  # UART0 TX (telemetry output)
        self.rx_pin = board.GP1  # UART0 RX

        # Pressure sensor I2C: SCL is shared between both sensor options;
        # SDA depends on which sensor is populated. Auto-detected below.
        self.scl_pin = board.GP7
        self.ms5607_sda_pin = board.GP10
        self.bmp280_sda_pin = board.GP6

        # Pyrotechnic control (AP2192 dual channel power switch)
        self.pyro_low_pin = board.GP15  # common enable (master switch)
        self.fire1_pin = board.GP21  # pyro 1 enable (AP2192 EN1)
        self.fire2_pin = board.GP22  # pyro 2 enable (AP2192 EN2)
        self.sense1_pin = board.A0  # GPIO26 (ADC0), pyro 1 continuity sense
        self.sense2_pin = board.A1  # GPIO27 (ADC1), pyro 2 continuity sense

        # User interface
        self.led_pin = board.GP25  # onboard LED (status)

        # Setup LED
        self.led = DigitalInOut(self.led_pin)
        self.led.switch_to_output()

        self.sense1 = analogio.AnalogIn(self.sense1_pin)
        self.sense2 = analogio.AnalogIn(self.sense2_pin)
        self.pyro_low = DigitalInOut(self.pyro_low_pin)
        self.pyro_low.switch_to_output(value=False)
        self.fire1 = DigitalInOut(self.fire1_pin)
        self.fire1.switch_to_output(value=False)
        self.fire2 = DigitalInOut(self.fire2_pin)
        self.fire2.switch_to_output(value=False)
        self.uart = busio.UART(self.tx_pin, self.rx_pin, baudrate=115200)

        self.i2c = None
        self.sensor = None
        self.sensor_name = None
        # Let the sensor's supply rail settle after board power-up before
        # the first I2C probe -- detection was unreliable without this.
        time.sleep(SENSOR_POWERUP_DELAY_S)
        self._init_pressure_sensor()

    # --- pressure sensor auto-detect --------------------------------------
    # The board may be built with either an MS5607 or a BMP280 (auto-detected
    # at boot per the pyro_fw README). Both share SCL; try each sensor's SDA
    # pin in turn, releasing the I2C bus between attempts.

    def _try_ms5607(self, i2c, address):
        sensor = MS5607(i2c, address=address)
        _ = sensor.pressure  # sanity read; raises if the sensor isn't there
        return sensor

    def _try_bmp280(self, i2c, address):
        sensor = adafruit_bmp280.Adafruit_BMP280_I2C(i2c, address)
        sensor.sea_level_pressure = 1013.25
        sensor.mode = adafruit_bmp280.MODE_NORMAL
        sensor.standby_period = adafruit_bmp280.STANDBY_TC_500
        sensor.iir_filter = adafruit_bmp280.IIR_FILTER_X16
        sensor.overscan_pressure = adafruit_bmp280.OVERSCAN_X16
        sensor.overscan_temperature = adafruit_bmp280.OVERSCAN_X2
        _ = sensor.pressure  # sanity read
        return sensor

    def _init_pressure_sensor(self):
        attempts = (
            ("MS5607", self.ms5607_sda_pin, self._try_ms5607),
            ("BMP280", self.bmp280_sda_pin, self._try_bmp280),
        )
        # CSB/SDO pin strapping varies by board, so each sensor may respond
        # on either address; matches pyro_fw's ms5607_detect()/bmp280_detect().
        addresses = (0x76, 0x77)
        last_error = None
        for name, sda_pin, try_fn in attempts:
            i2c = None
            try:
                i2c = busio.I2C(self.scl_pin, sda_pin)
                sensor = None
                for address in addresses:
                    try:
                        sensor = try_fn(i2c, address)
                        print(name + (" @ 0x%02x: OK" % address))
                        break
                    except Exception as e:
                        last_error = e
                        print(name + (" @ 0x%02x: FAIL (" % address) + str(e) + ")")
                if sensor is None:
                    raise last_error
            except Exception as e:
                last_error = e
                if i2c is not None:
                    try:
                        i2c.deinit()
                    except Exception:
                        pass
                continue
            else:
                self.i2c = i2c
                self.sensor = sensor
                self.sensor_name = name
                print("pressure sensor detected: " + name)
                return
        raise RuntimeError(
            "no pressure sensor responded (tried MS5607, BMP280): " + str(last_error)
        )

    def ledOn(self):
        self.led.value = True

    def ledOff(self):
        self.led.value = False

    def firePyro1(self):
        print("pyro 1 fire")
        self.uart.write("ignite 1\n".encode())
        self.pyro_low.value = True
        self.fire1.value = True

    def firePyro2(self):
        print("pyro 2 fire")
        self.uart.write("ignite 2\n".encode())
        self.pyro_low.value = True
        self.fire2.value = True

    def safeAllPyros(self):
        print("pyro safe")
        self.pyro_low.value = False
        self.fire1.value = False
        self.fire2.value = False

    def readPressure(self) -> float:
        return self.sensor.pressure

    def speak(self, msg):
        self.uart.write((msg + "\n").encode())

    def readTemperature(self) -> float:
        return self.sensor.temperature

    def finish(self):
        print("finished")
        while True:
            self.ledOn()
            time.sleep(0.25)
            self.ledOff()
            time.sleep(0.25)
