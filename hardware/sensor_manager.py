"""
Sensor management module for wildfire detection.

Integrates multiple sensor types:
- MQ2 smoke sensors (via ADS1115 ADC)
- DHT11 temperature and humidity sensor
- KY-026 flame detection sensors
- HC-SR04 ultrasonic distance sensor
"""

from utils.config import (I2C_SCL, I2C_SDA, ADS1115_MQ2_1, ADS1115_MQ2_2, DHT11_DATA_PIN,
                         KY026_FRONT_LEFT_PIN, KY026_FRONT_RIGHT_PIN, KY026_LEFT_PIN, KY026_RIGHT_PIN,
                         HCSR04_TRIGGER_PIN, HCSR04_ECHO_PIN, ULTRASONIC_DISTANCE_MULTIPLIER,
                         SENSOR_READ_TIMEOUT, MQ2_SMOKE_THRESHOLD, TEMP_THRESHOLD, HUMIDITY_THRESHOLD)
from utils.logger import WildfireLogger

import time

try:
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
except ImportError:
    ADS = None
    AnalogIn = None

try:
    import adafruit_dht
except ImportError:
    adafruit_dht = None

try:
    import board
except ImportError:
    board = None

try:
    import Jetson.GPIO as GPIO
except ImportError:
    GPIO = None

try:
    import busio
except ImportError:
    busio = None

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
    - Temperature/humidity monitoring (DHT11)
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
        self._dht11_available = False
        self._gpio_available = False
        self._last_dht11_reading = None
        self._mq2_channels = []
        self.logger = WildfireLogger("SensorManager")

        # Initialize I2C bus for digital sensors
        if busio is None:
            self.logger.log_error("SensorManager.I2C_init", "busio module is not available")
        else:
            try:
                self._i2c = busio.I2C(I2C_SCL, I2C_SDA)
            except (ValueError, RuntimeError, OSError) as e:
                self.logger.log_error("SensorManager.I2C_init", str(e))

        # Initialize I2C-based sensors if bus is available
        if self._i2c is not None:
            if ADS is None or AnalogIn is None:
                self.logger.log_error("SensorManager.ADS1115_init", "ADS1115 modules are not available")
            else:
                self._init_mq2_adc(ADS1115_MQ2_1, "_ads1_1", "_mq2_chan1")
                self._init_mq2_adc(ADS1115_MQ2_2, "_ads1_2", "_mq2_chan2")
                self._ads_available = bool(self._mq2_channels)

        if adafruit_dht is None:
            self.logger.log_error("SensorManager.DHT11_init", "adafruit_dht module is not available")
        elif board is None:
            self.logger.log_error("SensorManager.DHT11_init", "board module is not available")
        else:
            try:
                self._dht11 = adafruit_dht.DHT11(self._get_dht11_board_pin(DHT11_DATA_PIN))
                self._dht11_available = True
            except (ValueError, RuntimeError, OSError, AttributeError) as e:
                self.logger.log_error("SensorManager.DHT11_init", str(e))

        # Setup GPIO for digital sensors
        if GPIO is None:
            self.logger.log_error("SensorManager.GPIO_setmode", "Jetson.GPIO module is not available")
        else:
            try:
                GPIO.setmode(GPIO.BOARD)
                self._gpio_available = True
            except (ValueError, RuntimeError, AttributeError) as e:
                self.logger.log_error("SensorManager.GPIO_setmode", str(e))

        # Setup KY-026 flame sensors (4 sensors for directional detection)
        self._ky026_pins = {
            "front_left": KY026_FRONT_LEFT_PIN,
            "front_right": KY026_FRONT_RIGHT_PIN,
            "left": KY026_LEFT_PIN,
            "right": KY026_RIGHT_PIN,
        }
        for pin in self._ky026_pins.values():
            if self._gpio_available and pin is not None:
                try:
                    GPIO.setup(pin, GPIO.IN)
                except (ValueError, RuntimeError, AttributeError) as e:
                    self.logger.log_error("SensorManager.GPIO_setup_KY026", str(e))

        # Setup HC-SR04 ultrasonic distance sensor
        if self._gpio_available and HCSR04_TRIGGER_PIN is not None and HCSR04_ECHO_PIN is not None:
            try:
                GPIO.setup(HCSR04_TRIGGER_PIN, GPIO.OUT)
                GPIO.setup(HCSR04_ECHO_PIN, GPIO.IN)
            except (ValueError, RuntimeError, AttributeError) as e:
                self.logger.log_error("SensorManager.GPIO_setup_HCSR04", str(e))

    def read_mq2(self):
        """
        Read smoke level from MQ2 sensors.

        Returns:
            Average reading from available MQ2 sensors (0-65535 range)
            Returns 0 if sensors unavailable or read fails
        """
        if not self._ads_available or not self._mq2_channels:
            return 0
        values = []
        for channel in self._mq2_channels:
            try:
                values.append(channel.value)
            except (ValueError, RuntimeError, OSError, AttributeError) as e:
                self.logger.log_error("SensorManager.read_mq2", str(e))
        if not values:
            return 0
        return int(sum(values) / len(values))

    def _init_mq2_adc(self, address, ads_attr, channel_attr):
        if address is None:
            return
        try:
            ads = ADS.ADS1115(self._i2c, address=address)
            channel = AnalogIn(ads, ADS.P0)
            setattr(self, ads_attr, ads)
            setattr(self, channel_attr, channel)
            self._mq2_channels.append(channel)
        except (ValueError, RuntimeError, OSError, AttributeError) as e:
            self.logger.log_error("SensorManager.ADS1115_init", str(e))

    def _get_dht11_board_pin(self, pin):
        supported_pins = {
            18: "D18",
        }
        pin_name = supported_pins.get(pin)
        if pin_name is None:
            raise ValueError(f"Unsupported DHT11 BOARD pin: {pin}")
        try:
            return getattr(board, pin_name)
        except AttributeError as e:
            raise AttributeError(f"board.{pin_name} is not available") from e

    def read_dht11(self):
        """
        Read temperature and humidity from DHT11 sensor.

        Returns:
            Tuple of (temperature in Celsius, relative humidity percentage)
            Returns the previous valid reading or (0.0, 0.0) if unavailable or all reads fail
        """
        if not self._dht11_available or not hasattr(self, '_dht11'):
            return self._last_dht11_reading or (0.0, 0.0)

        last_error = None
        for attempt in range(3):
            try:
                temperature = self._dht11.temperature
                humidity = self._dht11.humidity
                if temperature is not None and humidity is not None:
                    self._last_dht11_reading = (temperature, humidity)
                    return self._last_dht11_reading
            except (ValueError, RuntimeError, OSError, AttributeError) as e:
                last_error = e

            if attempt < 2:
                time.sleep(1.0)

        self.logger.warning(f"SensorManager.read_dht11 failed after retries: {last_error}")
        return self._last_dht11_reading or (0.0, 0.0)

    def read_ky026(self):
        """
        Read flame detection from KY-026 IR sensors.

        Returns:
            List of 4 boolean values indicating flame detection for each sensor
            True means flame detected in that direction
            Note: KY-026 outputs LOW when flame detected, so we invert the reading
        """
        flame_detected = FlameReadings()
        if not self._gpio_available:
            for position in self._ky026_pins:
                flame_detected[position] = False
            return flame_detected

        for position, pin in self._ky026_pins.items():
            if pin is not None:
                try:
                    # KY-026 is active LOW (outputs 0 when flame detected)
                    flame_detected[position] = not GPIO.input(pin)
                except (ValueError, RuntimeError, AttributeError) as e:
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
        if not self._gpio_available or HCSR04_TRIGGER_PIN is None or HCSR04_ECHO_PIN is None:
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
                time.sleep(0.0001)

            # Wait for echo to end with timeout protection
            timeout_start = time.time()
            pulse_end = time.time()
            while GPIO.input(HCSR04_ECHO_PIN) == 1:
                pulse_end = time.time()
                if time.time() - timeout_start > SENSOR_READ_TIMEOUT:
                    return 0.0
                time.sleep(0.0001)

            # Calculate distance from pulse duration
            pulse_duration = pulse_end - pulse_start
            distance = pulse_duration * ULTRASONIC_DISTANCE_MULTIPLIER

            return round(distance, 2)
        except (ValueError, RuntimeError, AttributeError) as e:
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
        temperature, humidity = self.read_dht11()
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

    def is_ads_available(self) -> bool:
        """Return True if the ADS1115 / MQ2 sensor path is available."""
        return self._ads_available

    def is_dht11_available(self) -> bool:
        """Return True if the DHT11 temperature/humidity sensor path is available."""
        return self._dht11_available

    def is_gpio_available(self) -> bool:
        """Return True if the GPIO / KY-026 flame sensor path is available."""
        return self._gpio_available

    def is_available(self) -> bool:
        """Return True if at least one sensor path is available."""
        return self._ads_available or self._dht11_available or self._gpio_available

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
            if self._gpio_available:
                GPIO.cleanup()
        except (ValueError, RuntimeError, AttributeError) as e:
            self.logger.log_error("SensorManager.cleanup_gpio", str(e))
