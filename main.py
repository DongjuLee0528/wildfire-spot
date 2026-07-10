"""
Wildfire robot main control interface.

Provides keyboard-based control for:
- Patrol zone calibration using GPS waypoints
- System state monitoring
- Manual robot control
"""

import os
import sys
import termios
import tty
import select
import time
import re
import json
import threading
from pathlib import Path
from hardware.camera_control_manager import CameraControlManager
from utils.config import PATROL_ZONE_MIN_POINTS, SPRING_TELEMETRY_ENABLED, SPRING_API_BASE_URL, DEVICE_SERIAL_NUMBER, DEVICE_KEY
from utils.logger import WildfireLogger
import robot.robot_api as robot_api


def _start_keyboard_controller(logger):
    """
    Create RobotKeyboardController and return it.

    Only creates the controller and its robot_commands queue.
    monitor_commands is intentionally NOT started here — gait-loop is the
    sole consumer of robot_commands, and a competing monitor_commands thread
    would race against it and hold the queue for KB_TEST_SLEEP_TIME per cycle.

    Returns the controller instance so robot_commands queue can be shared
    with ManualControlManager and the gait-loop, or None if startup fails.
    """
    try:
        from Common.multiprocess_kb import RobotKeyboardController
        controller = RobotKeyboardController()
        logger.log_system_state("ROBOT_KEYBOARD_CONTROLLER_INIT ok")
        print("RobotKeyboardController initialised (robot_commands queue ready)")
        return controller
    except Exception as e:
        logger.log_error("Main.keyboard_controller_start", str(e))
        print(f"RobotKeyboardController unavailable: {e}")
        return None


def _init_servo_hardware(logger):
    """
    Initialise QuadrupedServoManager (I2C bus + both PCA9685 boards).

    Must be called before CameraControlManager so the front PCA9685 driver
    at 0x41 can be shared via get_front_driver() instead of opening a second
    I2C connection to the same bus.

    Returns:
        QuadrupedServoManager instance on success, else None.
    """
    try:
        from hardware.servo_controller import QuadrupedServoManager
        servo_manager = QuadrupedServoManager()
        logger.log_system_state("SERVO_HARDWARE_INIT ok")
        print("Servo hardware initialised (front=0x41 rear=0x42)")
        return servo_manager
    except Exception as e:
        logger.log_error("Main.servo_hardware_init", str(e))
        print(f"Servo hardware unavailable: {e}")
        return None


def _start_gait_loop(logger, servo_manager, kb_controller, mode_control_manager):
    """
    Start the gait execution daemon thread.

    Reads KB_CONTROL_OFFSET dicts from kb_controller.robot_commands, runs
    QuadrupedGaitPattern → DHParameterSolver → servo_manager, then re-puts
    the command back so it remains available for the next iteration.

    Args:
        logger: WildfireLogger instance
        servo_manager: Already-initialised QuadrupedServoManager
        kb_controller: RobotKeyboardController whose robot_commands queue to consume
        mode_control_manager: ModeControlManager used to gate stepping on MANUAL mode
    """
    try:
        from kinematicMotion import QuadrupedGaitPattern
        from Kinematics.kinematics import DHParameterSolver
        from utils.config import GAIT_BODY_POS, GAIT_BODY_ROT

        gait = QuadrupedGaitPattern()
        kinematics = DHParameterSolver()
    except Exception as e:
        logger.log_error("Main.gait_loop_start", str(e))
        print(f"Gait loop unavailable: {e}")
        return

    command_queue = kb_controller.robot_commands

    def _loop():
        # Import config inside thread to ensure values are read at runtime
        from utils.config import GAIT_BODY_POS, GAIT_BODY_ROT
        while True:
            command_data = None
            try:
                # Block until a command is available (up to 0.1 s timeout)
                command_data = command_queue.get(timeout=0.1)
            except Exception:
                # Timeout or queue error — just retry
                continue

            try:
                # Skip movement if StartStepping is False (STOP / RESET command)
                if not command_data.get("StartStepping", False):
                    command_queue.put(command_data)
                    time.sleep(0.02)
                    continue

                # Only execute physical movement when the robot is in MANUAL mode
                if mode_control_manager is not None and not mode_control_manager.is_manual():
                    command_queue.put(command_data)
                    time.sleep(0.02)
                    continue

                # Full pipeline: gait trajectory → inverse kinematics → servo output
                foot_positions = gait.calculate_leg_positions(time.time(), command_data)
                joint_angles = kinematics.solve_complete_inverse_kinematics(
                    foot_positions, GAIT_BODY_POS, GAIT_BODY_ROT
                )
                servo_manager.execute_servo_motion(joint_angles)

                # Re-insert command so the next loop iteration can read it
                command_queue.put(command_data)
            except Exception as e:
                logger.log_error("GaitLoop", str(e))
                # Always restore the command to avoid starving the queue
                if command_data is not None:
                    try:
                        command_queue.put(command_data)
                    except Exception:
                        pass
            # ~50 Hz max update rate
            time.sleep(0.02)

    thread = threading.Thread(target=_loop, daemon=True, name="gait-loop")
    thread.start()
    logger.log_system_state("GAIT_LOOP_STARTED")
    print("Gait loop started (servo motion active)")


def _start_robot_api_server(logger):
    # Read host/port from environment so they can be overridden without code changes
    host = os.environ.get("ROBOT_API_HOST", "0.0.0.0")
    port = int(os.environ.get("ROBOT_API_PORT", "8000"))
    try:
        import uvicorn
        config = uvicorn.Config(
            app=robot_api.app,
            host=host,
            port=port,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        # Daemon thread: server stops automatically when the main process exits
        thread = threading.Thread(target=server.run, daemon=True, name="robot-api")
        thread.start()
        logger.log_system_state(f"ROBOT_API_STARTED host={host} port={port}")
        print(f"Robot API server started on {host}:{port}")
    except Exception as e:
        logger.log_error("Main.robot_api_start", str(e))
        print(f"Robot API server failed to start: {e}")


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

    def __init__(self, logger, gps_manager):
        """
        Initialize calibrator with a shared GPSManager from RobotRuntimeContext.

        Args:
            logger: WildfireLogger instance for logging calibration events
            gps_manager: GPSManager instance owned by RobotRuntimeContext
        """
        self._gps = gps_manager
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

    def get_gps_manager(self):
        """Return the shared GPSManager instance."""
        return self._gps

    def cleanup(self):
        """GPS resources are owned by RobotRuntimeContext; nothing to release here."""
        pass

def main():
    """
    Main control loop for wildfire robot.

    Provides keyboard interface for:
    - 'c': Start patrol zone calibration
    - SPACE: Record GPS waypoint (during calibration)
    - 'f': Finish calibration (during calibration)
    - 'q': Quit program
    """
    # Pre-declare all subsystem handles so the finally block can safely check them
    logger = None
    runtime = None
    calibrator = None
    keyboard_input = None
    camera_control_manager = None
    camera_vision = None
    spring_telemetry = None
    manual_control_manager = None
    mode_control_manager = None
    patrol_zone_manager = None
    _kb_controller = None
    _servo_manager = None

    # Initialize logger first
    try:
        logger = WildfireLogger("Main")
    except Exception as e:
        print(f"Failed to initialize logger: {e}")
        return

    # Initialize subsystems
    try:
        logger.log_system_state("STARTING")

        from robot.robot_runtime_context import RobotRuntimeContext
        runtime = RobotRuntimeContext()

        calibrator = PatrolZoneCalibrator(logger, gps_manager=runtime.gps_manager)
        keyboard_input = KeyboardInput(logger)

        # Servo hardware must be initialised first so the front PCA9685 driver
        # (0x41) can be shared with CameraControlManager without opening a
        # second I2C handle on the same bus.
        _servo_manager = _init_servo_hardware(logger)

        try:
            # Pass the already-open front driver so CameraControlManager does
            # not create its own I2C connection to 0x41.
            front_driver = _servo_manager.get_front_driver() if _servo_manager is not None else None
            camera_control_manager = CameraControlManager(front_driver=front_driver)
            logger.log_system_state(f"CAMERA_INIT available={camera_control_manager.is_available()} shared_driver={front_driver is not None}")
        except Exception as e:
            logger.log_error("Main.camera_init", str(e))
            print(f"Camera control manager unavailable: {e}")

        try:
            from vision.camera_vision import CameraVision
            camera_vision = CameraVision()
            logger.log_system_state(f"CAMERA_VISION available={camera_vision.is_camera_available()}")
        except Exception as e:
            logger.log_error("Main.camera_vision_init", str(e))
            print(f"CameraVision unavailable: {e}")

        from robot.robot_core_data_collector import RobotCoreDataCollector
        _collector = RobotCoreDataCollector.from_runtime_context(runtime)

        # Start the keyboard controller; its robot_commands queue is shared
        # with ManualControlManager and the gait loop.
        _kb_controller = _start_keyboard_controller(logger)

        try:
            from robot.manual_control_manager import ManualControlManager
            from robot.mode_control_manager import ModeControlManager
            mode_control_manager = ModeControlManager(state_machine=runtime.state_machine)
            manual_control_manager = ManualControlManager(
                command_queue=_kb_controller.robot_commands if _kb_controller is not None else None,
                mode_manager=mode_control_manager,
            )
            queue_status = "connected to robot_commands" if _kb_controller is not None else "no movement loop"
            logger.log_system_state(f"MANUAL_CONTROL_INIT ok ({queue_status})")
        except Exception as e:
            logger.log_error("Main.manual_control_init", str(e))
            print(f"ManualControlManager unavailable: {e}")

        try:
            from navigation.patrol_zone_manager import PatrolZoneManager
            patrol_zone_manager = PatrolZoneManager()
            logger.log_system_state("PATROL_ZONE_MANAGER_INIT ok")
        except Exception as e:
            logger.log_error("Main.patrol_zone_manager_init", str(e))
            print(f"PatrolZoneManager unavailable: {e}")

        # Start the gait execution loop only when both the keyboard queue and
        # servo hardware are available; otherwise movement commands are rejected.
        if _kb_controller is not None and _servo_manager is not None:
            _start_gait_loop(logger, _servo_manager, _kb_controller, mode_control_manager)

        # Propagate gait availability to ManualControlManager so movement
        # commands return accepted=false when hardware is unavailable.
        gait_available = _servo_manager is not None
        if manual_control_manager is not None:
            manual_control_manager.set_movement_available(gait_available)
        logger.log_system_state(f"GAIT_LOOP_AVAILABLE={gait_available}")
        print(f"Gait loop available: {gait_available}")

        robot_api.configure(
            state_machine=runtime.state_machine,
            collector=_collector,
            manual_control_manager=manual_control_manager,
            mode_control_manager=mode_control_manager,
            patrol_zone_manager=patrol_zone_manager,
            camera_control_manager=camera_control_manager,
            camera_vision=camera_vision,
        )

        _start_robot_api_server(logger)

        if SPRING_TELEMETRY_ENABLED:
            print("SpringTelemetry: enabled")
            try:
                from robot.spring_api_client import SpringApiClient
                from robot.spring_telemetry import SpringTelemetry

                if not DEVICE_SERIAL_NUMBER or not DEVICE_KEY:
                    print("SpringTelemetry: DEVICE_SERIAL_NUMBER or DEVICE_KEY not set — skipping")
                    logger.log_error("Main.spring_telemetry", "Missing DEVICE_SERIAL_NUMBER or DEVICE_KEY")
                else:
                    _spring_client = SpringApiClient(
                        serial_number=DEVICE_SERIAL_NUMBER,
                        device_key=DEVICE_KEY,
                        base_url=SPRING_API_BASE_URL,
                    )
                    if _spring_client.login():
                        spring_telemetry = SpringTelemetry(_spring_client, data_collector=_collector)
                        spring_telemetry.start()
                        print(f"SpringTelemetry: started (url={SPRING_API_BASE_URL})")
                        logger.log_system_state("SPRING_TELEMETRY_STARTED")
                    else:
                        print("SpringTelemetry: device login failed — telemetry disabled")
                        logger.log_error("Main.spring_telemetry", "Device login failed")
            except Exception as e:
                print(f"SpringTelemetry: failed to start — {e}")
                logger.log_error("Main.spring_telemetry", str(e))
        else:
            print("SpringTelemetry: disabled (set SPRING_TELEMETRY_ENABLED=true to enable)")

        # Display control instructions
        print("Robot Control Interface")
        print("Press 'c' to start patrol zone calibration")
        print("Press 'f' to finish calibration (during calibration)")
        print("Press 'q' to quit")

        # Main control loop — runs at ~20 Hz, handles keyboard input only
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
        # Clean up resources in reverse initialization order.
        # camera_control_manager.close() must precede _servo_manager.shutdown_servos()
        # because the camera uses the shared front PCA9685 driver owned by servo_manager.
        if camera_control_manager is not None:
            camera_control_manager.close()
        if _servo_manager is not None:
            try:
                _servo_manager.shutdown_servos()
            except Exception:
                pass
        if _kb_controller is not None:
            try:
                _kb_controller.stop()
                _kb_controller.cleanup()
            except Exception:
                pass
        if spring_telemetry is not None:
            try:
                spring_telemetry.stop()
            except Exception:
                pass
        if keyboard_input is not None:
            keyboard_input.restore()
        if camera_vision is not None:
            try:
                camera_vision.release()
            except Exception:
                pass
        if runtime is not None:
            try:
                runtime.close()
            except Exception:
                pass
        if logger is not None:
            logger.log_system_state("STOPPED")
            logger.close()

if __name__ == "__main__":
    main()
