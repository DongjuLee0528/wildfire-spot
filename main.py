import sys
import termios
import tty
import select
import time
import re
import json
from pathlib import Path
from hardware.gps_manager import GPSManager
from utils.config import PATROL_ZONE_MAX_POINTS
from utils.logger import WildfireLogger

class KeyboardInput:
    def __init__(self, logger):
        self.logger = logger
        try:
            self.old_settings = termios.tcgetattr(sys.stdin)
            tty.setraw(sys.stdin.fileno())
        except (termios.error, OSError) as e:
            self.logger.log_error("KeyboardInput.__init__", str(e))
            print(f"Failed to initialize keyboard input: {e}")
            self.old_settings = None

    def get_key(self):
        try:
            if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
                key = sys.stdin.read(1)
                return key
            return None
        except (OSError, ValueError) as e:
            self.logger.log_error("KeyboardInput.get_key", str(e))
            return None

    def restore(self):
        if self.old_settings is not None:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
            except (termios.error, OSError) as e:
                self.logger.log_error("KeyboardInput.restore", str(e))
                print(f"Failed to restore terminal settings: {e}")

class PatrolZoneCalibrator:

    def __init__(self, logger):
        self._gps = GPSManager()
        self._calibration_mode = False
        self._collected_points = []
        self.logger = logger

    def start_calibration(self):
        if not self._gps.is_available():
            self.logger.log_error("PatrolZoneCalibrator.start_calibration", "GPS not available")
            print("GPS not available for calibration")
            return

        self._calibration_mode = True
        self._collected_points = []
        self.logger.log_system_state("CALIBRATING")
        print(f"Calibration mode started. Press SPACE to record GPS coordinates ({PATROL_ZONE_MAX_POINTS} points required)")

    def handle_space_key(self):
        if not self._calibration_mode:
            return

        coordinates = self._gps.get_current_coordinates()
        if coordinates is None:
            self.logger.log_error("PatrolZoneCalibrator.handle_space_key", "GPS coordinates not available")
            print("GPS coordinates not available, try again")
            return

        if not isinstance(coordinates, (tuple, list)) or len(coordinates) < 2:
            self.logger.log_error("PatrolZoneCalibrator.handle_space_key", f"Invalid GPS format: {coordinates}")
            print("Invalid GPS coordinates format, try again")
            return

        self._collected_points.append(coordinates)
        point_number = len(self._collected_points)
        lat, lon = coordinates[0], coordinates[1]
        print(f"Point {point_number} recorded: ({lat:.6f}, {lon:.6f})")

        if point_number >= PATROL_ZONE_MAX_POINTS:
            self._complete_calibration()

    def _complete_calibration(self):
        self._calibration_mode = False
        self._update_config_file()
        self.logger.log_system_state("CALIBRATION_COMPLETE")
        print("Calibration completed. Patrol zone saved to config file.")

    def _update_config_file(self):
        config_path = Path(__file__).parent / 'utils' / 'config.py'
        pattern = re.compile(r'^PATROL_ZONE\s*=')

        try:
            with open(config_path, 'r') as file:
                lines = file.readlines()

            pattern_found = False
            for i, line in enumerate(lines):
                if pattern.match(line.strip()):
                    lines[i] = f'PATROL_ZONE = {json.dumps(self._collected_points)}\n'
                    pattern_found = True
                    break

            if not pattern_found:
                self.logger.log_error("PatrolZoneCalibrator._update_config_file", "PATROL_ZONE pattern not found in config")
                print("Failed to update config file: PATROL_ZONE pattern not found")
                return

            with open(config_path, 'w') as file:
                file.writelines(lines)
        except (IOError, OSError) as e:
            self.logger.log_error("PatrolZoneCalibrator._update_config_file", str(e))
            print(f"Failed to update config file: {e}")

    def is_calibration_mode(self):
        return self._calibration_mode

    def cleanup(self):
        if hasattr(self, '_gps') and self._gps is not None:
            self._gps.close()

def main():
    logger = None
    calibrator = None
    keyboard_input = None

    try:
        logger = WildfireLogger("Main")
    except Exception as e:
        print(f"Failed to initialize logger: {e}")
        return

    try:
        logger.log_system_state("STARTING")
        calibrator = PatrolZoneCalibrator(logger)
        keyboard_input = KeyboardInput(logger)

        print("Robot Control Interface")
        print("Press 'c' to start patrol zone calibration")
        print("Press 'q' to quit")

        while True:
            try:
                key = keyboard_input.get_key()

                if key == 'c':
                    calibrator.start_calibration()
                    time.sleep(0.5)
                elif key == ' ' and calibrator.is_calibration_mode():
                    calibrator.handle_space_key()
                    time.sleep(0.5)
                elif key == 'q':
                    print("Exiting...")
                    break

                time.sleep(0.05)

            except KeyboardInterrupt:
                logger.log_system_state("INTERRUPTED")
                print("Interrupted by user")
                break
            except Exception as e:
                logger.log_error("Main.loop", str(e))
                print(f"Error in main loop: {e}")
                break
    except Exception as e:
        logger.log_error("Main.init", str(e))
        print(f"Failed to initialize: {e}")
    finally:
        if keyboard_input is not None:
            keyboard_input.restore()
        if calibrator is not None:
            calibrator.cleanup()
        if logger is not None:
            logger.log_system_state("STOPPED")
            logger.close()

if __name__ == "__main__":
    main()