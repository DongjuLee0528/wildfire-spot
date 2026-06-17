from utils.config import (I2C_SCL, I2C_SDA, ADS1115_MQ2_1, ADS1115_MQ2_2, SHT31_ADDRESS,
                         KY026_PIN_1, KY026_PIN_2, KY026_PIN_3, KY026_PIN_4,
                         HCSR04_TRIGGER_PIN, HCSR04_ECHO_PIN, ULTRASONIC_DISTANCE_MULTIPLIER,
                         SENSOR_READ_TIMEOUT)
from utils.logger import WildfireLogger

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_sht31d
import Jetson.GPIO as GPIO
import busio
import board
import time

class SensorManager:
    def __init__(self):
        self._i2c = None
        self._ads_available = False
        self._sht31_available = False
        self.logger = WildfireLogger("SensorManager")

        try:
            self._i2c = busio.I2C(I2C_SCL, I2C_SDA)
        except (ValueError, RuntimeError, OSError) as e:
            self.logger.log_error("SensorManager.I2C_init", str(e))

        if self._i2c is not None:
            try:
                self._ads1_1 = ADS.ADS1115(self._i2c, address=ADS1115_MQ2_1)
                self._ads1_2 = ADS.ADS1115(self._i2c, address=ADS1115_MQ2_2)
                self._mq2_chan1 = AnalogIn(self._ads1_1, ADS.P0)
                self._mq2_chan2 = AnalogIn(self._ads1_2, ADS.P0)
                self._ads_available = True
            except (ValueError, RuntimeError, OSError) as e:
                self.logger.log_error("SensorManager.ADS1115_init", str(e))

            try:
                self._sht31 = adafruit_sht31d.SHT31D(self._i2c, address=SHT31_ADDRESS)
                self._sht31_available = True
            except (ValueError, RuntimeError, OSError) as e:
                self.logger.log_error("SensorManager.SHT31_init", str(e))

        try:
            GPIO.setmode(GPIO.BOARD)
        except (ValueError, RuntimeError) as e:
            self.logger.log_error("SensorManager.GPIO_setmode", str(e))

        self._ky026_pins = [KY026_PIN_1, KY026_PIN_2, KY026_PIN_3, KY026_PIN_4]
        for pin in self._ky026_pins:
            if pin is not None:
                try:
                    GPIO.setup(pin, GPIO.IN)
                except (ValueError, RuntimeError) as e:
                    self.logger.log_error("SensorManager.GPIO_setup_KY026", str(e))

        if HCSR04_TRIGGER_PIN is not None and HCSR04_ECHO_PIN is not None:
            try:
                GPIO.setup(HCSR04_TRIGGER_PIN, GPIO.OUT)
                GPIO.setup(HCSR04_ECHO_PIN, GPIO.IN)
            except (ValueError, RuntimeError) as e:
                self.logger.log_error("SensorManager.GPIO_setup_HCSR04", str(e))

    def read_mq2(self):
        if not self._ads_available or not hasattr(self, '_mq2_chan1') or not hasattr(self, '_mq2_chan2'):
            return 0
        try:
            value1 = self._mq2_chan1.value
            value2 = self._mq2_chan2.value
            return int((value1 + value2) / 2)
        except (ValueError, RuntimeError, OSError, AttributeError) as e:
            self.logger.log_error("SensorManager.read_mq2", str(e))
            return 0

    def read_sht31(self):
        if not self._sht31_available or not hasattr(self, '_sht31'):
            return (0.0, 0.0)
        try:
            temperature = self._sht31.temperature
            humidity = self._sht31.relative_humidity
            return (temperature, humidity)
        except (ValueError, RuntimeError, OSError, AttributeError) as e:
            self.logger.log_error("SensorManager.read_sht31", str(e))
            return (0.0, 0.0)

    def read_ky026(self):
        flame_detected = []
        for pin in self._ky026_pins:
            if pin is not None:
                try:
                    flame_detected.append(not GPIO.input(pin))
                except (ValueError, RuntimeError) as e:
                    self.logger.log_error("SensorManager.read_ky026", str(e))
                    flame_detected.append(False)
            else:
                flame_detected.append(False)
        return flame_detected

    def read_hcsr04(self):
        if HCSR04_TRIGGER_PIN is None or HCSR04_ECHO_PIN is None:
            return 0.0

        try:
            GPIO.output(HCSR04_TRIGGER_PIN, GPIO.LOW)
            time.sleep(0.000002)
            GPIO.output(HCSR04_TRIGGER_PIN, GPIO.HIGH)
            time.sleep(0.00001)
            GPIO.output(HCSR04_TRIGGER_PIN, GPIO.LOW)

            timeout_start = time.time()
            pulse_start = time.time()
            while GPIO.input(HCSR04_ECHO_PIN) == 0:
                pulse_start = time.time()
                if time.time() - timeout_start > SENSOR_READ_TIMEOUT:
                    return 0.0

            timeout_start = time.time()
            pulse_end = time.time()
            while GPIO.input(HCSR04_ECHO_PIN) == 1:
                pulse_end = time.time()
                if time.time() - timeout_start > SENSOR_READ_TIMEOUT:
                    return 0.0

            pulse_duration = pulse_end - pulse_start
            distance = pulse_duration * ULTRASONIC_DISTANCE_MULTIPLIER

            return round(distance, 2)
        except (ValueError, RuntimeError) as e:
            self.logger.log_error("SensorManager.read_hcsr04", str(e))
            return 0.0

    def read_all(self):
        smoke = self.read_mq2()
        temperature, humidity = self.read_sht31()
        flame = self.read_ky026()
        distance = self.read_hcsr04()

        sensor_data = {
            "smoke": smoke,
            "temperature": temperature,
            "humidity": humidity,
            "flame": flame,
            "distance": distance
        }

        self.logger.log_sensor_values(sensor_data)
        return sensor_data

    def cleanup(self):
        try:
            if self._i2c is not None:
                self._i2c.deinit()
        except (ValueError, RuntimeError, AttributeError) as e:
            self.logger.log_error("SensorManager.cleanup_i2c", str(e))

        try:
            GPIO.cleanup()
        except (ValueError, RuntimeError) as e:
            self.logger.log_error("SensorManager.cleanup_gpio", str(e))