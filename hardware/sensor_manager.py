"""
Sensor management module for wildfire detection.

Integrates multiple sensor types:
- MQ2 smoke sensors (via ADS1115 ADC)
- SHT31 temperature and humidity sensor
- KY-026 flame detection sensors
- HC-SR04 ultrasonic distance sensor
"""

from utils.config import (I2C_SCL, I2C_SDA, ADS1115_MQ2_1, ADS1115_MQ2_2, SHT31_ADDRESS,
                         KY026_FRONT_LEFT_PIN, KY026_FRONT_RIGHT_PIN, KY026_LEFT_PIN, KY026_RIGHT_PIN,
                         HCSR04_TRIGGER_PIN, HCSR04_ECHO_PIN, ULTRASONIC_DISTANCE_MULTIPLIER,
                         SENSOR_READ_TIMEOUT, MQ2_SMOKE_THRESHOLD, TEMP_THRESHOLD, HUMIDITY_THRESHOLD)
from utils.logger import WildfireLogger

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_sht31d
import Jetson.GPIO as GPIO
import busio
import board
import time

class FlameReadings(dict):
    def __iter__(self):
        return iter(self.values())

    def __bool__(self):
        return any(self.values())

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class SensorManager:
    """
    Manages all environmental sensors for fire detection.

    Handles initialization, reading, and error recovery for:
    - Smoke detection (MQ2 sensors)
    - Temperature/humidity monitoring (SHT31)
    - Flame detection (KY-026 IR sensors)
    - Obstacle distance measurement (HC-SR04)
    """
    def __init__(self):
        """
        Initialize all sensors with graceful degradation.

        If individual sensors fail to initialize, the system continues
        operation with available sensors. Failures are logged for debugging.
        """
        self._i2c = None
        self._ads_available = False
        self._sht31_available = False
        self.logger = WildfireLogger("SensorManager")

        # Initialize I2C bus for digital sensors
        try:
            self._i2c = busio.I2C(I2C_SCL, I2C_SDA)
        except (ValueError, RuntimeError, OSError) as e:
            self.logger.log_error("SensorManager.I2C_init", str(e))

        # Initialize I2C-based sensors if bus is available
        if self._i2c is not None:
            # Setup dual ADS1115 ADCs for two MQ2 smoke sensors
            try:
                self._ads1_1 = ADS.ADS1115(self._i2c, address=ADS1115_MQ2_1)
                self._ads1_2 = ADS.ADS1115(self._i2c, address=ADS1115_MQ2_2)
                self._mq2_chan1 = AnalogIn(self._ads1_1, ADS.P0)
                self._mq2_chan2 = AnalogIn(self._ads1_2, ADS.P0)
                self._ads_available = True
            except (ValueError, RuntimeError, OSError) as e:
                self.logger.log_error("SensorManager.ADS1115_init", str(e))

            # Setup SHT31 temperature and humidity sensor
            try:
                self._sht31 = adafruit_sht31d.SHT31D(self._i2c, address=SHT31_ADDRESS)
                self._sht31_available = True
            except (ValueError, RuntimeError, OSError) as e:
                self.logger.log_error("SensorManager.SHT31_init", str(e))

        # Setup GPIO for digital sensors
        try:
            GPIO.setmode(GPIO.BOARD)
        except (ValueError, RuntimeError) as e:
            self.logger.log_error("SensorManager.GPIO_setmode", str(e))

        # Setup KY-026 flame sensors (4 sensors for directional detection)
        self._ky026_pins = {
            "front_left": KY026_FRONT_LEFT_PIN,
            "front_right": KY026_FRONT_RIGHT_PIN,
            "left": KY026_LEFT_PIN,
            "right": KY026_RIGHT_PIN,
        }
        for pin in self._ky026_pins.values():
            if pin is not None:
                try:
                    GPIO.setup(pin, GPIO.IN)
                except (ValueError, RuntimeError) as e:
                    self.logger.log_error("SensorManager.GPIO_setup_KY026", str(e))

        # Setup HC-SR04 ultrasonic distance sensor
        if HCSR04_TRIGGER_PIN is not None and HCSR04_ECHO_PIN is not None:
            try:
                GPIO.setup(HCSR04_TRIGGER_PIN, GPIO.OUT)
                GPIO.setup(HCSR04_ECHO_PIN, GPIO.IN)
            except (ValueError, RuntimeError) as e:
                self.logger.log_error("SensorManager.GPIO_setup_HCSR04", str(e))

    def read_mq2(self):
        """
        Read smoke level from MQ2 sensors.

        Returns:
            Average reading from two MQ2 sensors (0-65535 range)
            Returns 0 if sensors unavailable or read fails
        """
        if not self._ads_available or not hasattr(self, '_mq2_chan1') or not hasattr(self, '_mq2_chan2'):
            return 0
        try:
            value1 = self._mq2_chan1.value
            value2 = self._mq2_chan2.value
            # Average readings from both sensors for better accuracy
            return int((value1 + value2) / 2)
        except (ValueError, RuntimeError, OSError, AttributeError) as e:
            self.logger.log_error("SensorManager.read_mq2", str(e))
            return 0

    def read_sht31(self):
        """
        Read temperature and humidity from SHT31 sensor.

        Returns:
            Tuple of (temperature in Celsius, relative humidity percentage)
            Returns (0.0, 0.0) if sensor unavailable or read fails
        """
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
        """
        Read flame detection from KY-026 IR sensors.

        Returns:
            List of 4 boolean values indicating flame detection for each sensor
            True means flame detected in that direction
            Note: KY-026 outputs LOW when flame detected, so we invert the reading
        """
        flame_detected = FlameReadings()
        for position, pin in self._ky026_pins.items():
            if pin is not None:
                try:
                    # KY-026 is active LOW (outputs 0 when flame detected)
                    flame_detected[position] = not GPIO.input(pin)
                except (ValueError, RuntimeError) as e:
                    self.logger.log_error("SensorManager.read_ky026", str(e))
                    flame_detected[position] = False
            else:
                flame_detected[position] = False
        return flame_detected

    def _check_hardware_confirmation(self, smoke, temperature, humidity, flame):
        flame_detected = any(flame.values()) if isinstance(flame, dict) else any(flame)
        sensor_conditions = {
            "flame": flame_detected,
            "gas": smoke > MQ2_SMOKE_THRESHOLD,
            "temperature": temperature > TEMP_THRESHOLD,
            "humidity": humidity < HUMIDITY_THRESHOLD
        }
        fire_detected = any(sensor_conditions.values())
        confirmed_fire = flame_detected and any(
            detected for condition, detected in sensor_conditions.items() if condition != "flame"
        )
        return fire_detected, confirmed_fire

    def read_hcsr04(self):
        """
        Read distance from HC-SR04 ultrasonic sensor.

        Returns:
            Distance in centimeters (rounded to 2 decimal places)
            Returns 0.0 if sensor unavailable, timeout, or read fails

        Uses timeout protection to prevent infinite loops if sensor fails.
        """
        if HCSR04_TRIGGER_PIN is None or HCSR04_ECHO_PIN is None:
            return 0.0

        try:
            # Send 10μs trigger pulse
            GPIO.output(HCSR04_TRIGGER_PIN, GPIO.LOW)
            time.sleep(0.000002)
            GPIO.output(HCSR04_TRIGGER_PIN, GPIO.HIGH)
            time.sleep(0.00001)
            GPIO.output(HCSR04_TRIGGER_PIN, GPIO.LOW)

            # Wait for echo to start with timeout protection
            timeout_start = time.time()
            pulse_start = time.time()
            while GPIO.input(HCSR04_ECHO_PIN) == 0:
                pulse_start = time.time()
                if time.time() - timeout_start > SENSOR_READ_TIMEOUT:
                    return 0.0

            # Wait for echo to end with timeout protection
            timeout_start = time.time()
            pulse_end = time.time()
            while GPIO.input(HCSR04_ECHO_PIN) == 1:
                pulse_end = time.time()
                if time.time() - timeout_start > SENSOR_READ_TIMEOUT:
                    return 0.0

            # Calculate distance from pulse duration
            pulse_duration = pulse_end - pulse_start
            distance = pulse_duration * ULTRASONIC_DISTANCE_MULTIPLIER

            return round(distance, 2)
        except (ValueError, RuntimeError) as e:
            self.logger.log_error("SensorManager.read_hcsr04", str(e))
            return 0.0

    def read_all(self):
        """
        Read all sensors and return consolidated data.

        Returns:
            Dictionary containing all sensor readings:
            - smoke: MQ2 smoke level
            - temperature: Temperature in Celsius
            - humidity: Relative humidity percentage
            - flame: List of 4 boolean flame detection values
            - distance: Ultrasonic distance in cm

        Logs the readings for monitoring and debugging.
        """
        smoke = self.read_mq2()
        temperature, humidity = self.read_sht31()
        flame = self.read_ky026()
        distance = self.read_hcsr04()
        fire_detected, confirmed_fire = self._check_hardware_confirmation(smoke, temperature, humidity, flame)

        sensor_data = {
            "smoke": smoke,
            "temperature": temperature,
            "humidity": humidity,
            "flame": flame,
            "flame_list": list(flame.values()),
            "gas": smoke,
            "fire_detected": fire_detected,
            "confirmed_fire": confirmed_fire,
            "distance": distance
        }

        self.logger.log_sensor_values(sensor_data)
        return sensor_data

    def cleanup(self):
        """
        Release hardware resources.

        Deinitializes I2C bus and cleans up GPIO pins.
        Should be called during system shutdown.
        """
        try:
            if self._i2c is not None:
                self._i2c.deinit()
        except (ValueError, RuntimeError, AttributeError) as e:
            self.logger.log_error("SensorManager.cleanup_i2c", str(e))

        try:
            GPIO.cleanup()
        except (ValueError, RuntimeError) as e:
            self.logger.log_error("SensorManager.cleanup_gpio", str(e))
