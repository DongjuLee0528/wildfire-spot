"""
Wildfire robot main control interface.

Provides keyboard-based control for:
- Patrol zone calibration using GPS waypoints
- System state monitoring
- Manual robot control
"""

import sys
import termios
import tty
import select
import time
import re
import json
from pathlib import Path
from hardware.camera_control_manager import CameraControlManager
from hardware.gps_manager import GPSManager
from utils.config import PATROL_ZONE_MIN_POINTS
from utils.logger import WildfireLogger
import robot.robot_api as robot_api

class KeyboardInput:
    """
    Non-blocking keyboard input handler.

    Uses terminal raw mode to capture keystrokes without buffering.
    Restores original terminal settings on cleanup.
    """
    def __init__(self, logger):
        """
        Initialize keyboard input in raw mode.

        Args:
            logger: WildfireLogger instance for error logging

        Saves current terminal settings and switches to raw mode
        for immediate keystroke capture without Enter key.
        """
        self.logger = logger
        try:
            self.old_settings = termios.tcgetattr(sys.stdin)
            tty.setraw(sys.stdin.fileno())
        except (termios.error, OSError) as e:
            self.logger.log_error("KeyboardInput.__init__", str(e))
            print(f"Failed to initialize keyboard input: {e}")
            self.old_settings = None

    def get_key(self):
        """
        Non-blocking keyboard read.

        Returns:
            Single character if key pressed, None if no key available

        Uses select() to check if input is available without blocking.
        """
        try:
            if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
                key = sys.stdin.read(1)
                return key
            return None
        except (OSError, ValueError) as e:
            self.logger.log_error("KeyboardInput.get_key", str(e))
            return None

    def restore(self):
        """
        Restore terminal to original settings.

        Should be called on program exit to return terminal to normal mode.
        """
        if self.old_settings is not None:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
            except (termios.error, OSError) as e:
                self.logger.log_error("KeyboardInput.restore", str(e))
                print(f"Failed to restore terminal settings: {e}")

class PatrolZoneCalibrator:
    """
    GPS-based patrol zone boundary calibration.

    Allows operator to walk the robot around the patrol perimeter,
    recording GPS waypoints to define the patrol zone polygon.
    """

    def __init__(self, logger):
        """
        Initialize calibrator with GPS manager.

        Args:
            logger: WildfireLogger instance for logging calibration events
        """
        self._gps = GPSManager()
        self._calibration_mode = False
        self._collected_points = []
        self.logger = logger

    def start_calibration(self):
        """
        Begin patrol zone calibration mode.

        Checks GPS availability and enters calibration mode.
        Operator will press SPACE at each boundary point to record coordinates.
        """
        if not self._gps.is_available():
            self.logger.log_error("PatrolZoneCalibrator.start_calibration", "GPS not available")
            print("GPS not available for calibration")
            return

        self._calibration_mode = True
        self._collected_points = []
        self.logger.log_system_state("CALIBRATING")
        print(f"Calibration mode started. Press SPACE to record GPS coordinates (minimum {PATROL_ZONE_MIN_POINTS} required, press F to finish)")

    def handle_space_key(self):
        """
        Record current GPS position as a patrol zone waypoint.

        Called when SPACE key pressed during calibration.
        Validates GPS reading and adds to collected points list.
        """
        if not self._calibration_mode:
            return

        # Get current GPS coordinates with retry logic
        coordinates = self._gps.get_current_coordinates()
        if coordinates is None:
            self.logger.log_error("PatrolZoneCalibrator.handle_space_key", "GPS coordinates not available")
            print("GPS coordinates not available, try again")
            return

        # Validate coordinate format
        if not isinstance(coordinates, (tuple, list)) or len(coordinates) < 2:
            self.logger.log_error("PatrolZoneCalibrator.handle_space_key", f"Invalid GPS format: {coordinates}")
            print("Invalid GPS coordinates format, try again")
            return

        # Record waypoint
        self._collected_points.append(coordinates)
        point_number = len(self._collected_points)
        lat, lon = coordinates[0], coordinates[1]
        print(f"Point {point_number} recorded: ({lat:.6f}, {lon:.6f})")

    def handle_finish_key(self):
        """
        Complete calibration and save patrol zone.

        Called when F key pressed during calibration.
        Validates minimum point count before saving.
        """
        if not self._calibration_mode:
            return

        # Ensure minimum points for valid polygon
        if len(self._collected_points) < PATROL_ZONE_MIN_POINTS:
            self.logger.log_error("PatrolZoneCalibrator.handle_finish_key", f"Not enough points: {len(self._collected_points)} < {PATROL_ZONE_MIN_POINTS}")
            print(f"Need at least {PATROL_ZONE_MIN_POINTS} points, currently have {len(self._collected_points)}")
            return

        self._complete_calibration()

    def _complete_calibration(self):
        """
        Finalize calibration and save to config.

        Exits calibration mode and writes waypoints to config file.
        """
        self._calibration_mode = False
        self._update_config_file()
        self.logger.log_system_state("CALIBRATION_COMPLETE")
        print("Calibration completed. Patrol zone saved to config file.")

    def _update_config_file(self):
        """
        Write collected GPS waypoints to config file.

        Updates the PATROL_ZONE variable in utils/config.py
        with the collected GPS coordinates as a JSON array.
        """
        config_path = Path(__file__).parent / 'utils' / 'config.py'
        pattern = re.compile(r'^PATROL_ZONE\s*=')

        try:
            # Read current config file
            with open(config_path, 'r') as file:
                lines = file.readlines()

            # Find and replace PATROL_ZONE line
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

            # Write updated config back to file
            with open(config_path, 'w') as file:
                file.writelines(lines)
        except (IOError, OSError) as e:
            self.logger.log_error("PatrolZoneCalibrator._update_config_file", str(e))
            print(f"Failed to update config file: {e}")

    def is_calibration_mode(self):
        """Check if currently in calibration mode."""
        return self._calibration_mode

    def cleanup(self):
        """Release GPS resources."""
        if hasattr(self, '_gps') and self._gps is not None:
            self._gps.close()

def main():
    """
    Main control loop for wildfire robot.

    Provides keyboard interface for:
    - 'c': Start patrol zone calibration
    - SPACE: Record GPS waypoint (during calibration)
    - 'f': Finish calibration (during calibration)
    - 'q': Quit program
    """
    logger = None
    calibrator = None
    keyboard_input = None
    camera_control_manager = None

    # Initialize logger first
    try:
        logger = WildfireLogger("Main")
    except Exception as e:
        print(f"Failed to initialize logger: {e}")
        return

    # Initialize subsystems
    try:
        logger.log_system_state("STARTING")
        calibrator = PatrolZoneCalibrator(logger)
        keyboard_input = KeyboardInput(logger)

        try:
            camera_control_manager = CameraControlManager()
            robot_api.configure(camera_control_manager=camera_control_manager)
            logger.log_system_state(f"CAMERA_INIT available={camera_control_manager.is_available()}")
        except Exception as e:
            logger.log_error("Main.camera_init", str(e))
            print(f"Camera control manager unavailable: {e}")

        # Display control instructions
        print("Robot Control Interface")
        print("Press 'c' to start patrol zone calibration")
        print("Press 'f' to finish calibration (during calibration)")
        print("Press 'q' to quit")

        # Main control loop
        while True:
            try:
                key = keyboard_input.get_key()

                if key == 'c':
                    calibrator.start_calibration()
                    time.sleep(0.5)  # Debounce delay
                elif key == ' ' and calibrator.is_calibration_mode():
                    calibrator.handle_space_key()
                    time.sleep(0.5)  # Debounce delay
                elif key == 'f' and calibrator.is_calibration_mode():
                    calibrator.handle_finish_key()
                    time.sleep(0.5)  # Debounce delay
                elif key == 'q':
                    print("Exiting...")
                    break

                time.sleep(0.05)  # Main loop delay

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
        # Clean up resources in reverse initialization order
        if keyboard_input is not None:
            keyboard_input.restore()
        if calibrator is not None:
            calibrator.cleanup()
        if camera_control_manager is not None:
            camera_control_manager.close()
        if logger is not None:
            logger.log_system_state("STOPPED")
            logger.close()

if __name__ == "__main__":
    main()