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
from utils.config import PATROL_ZONE_MIN_POINTS, SPRING_TELEMETRY_ENABLED, SPRING_API_BASE_URL, DEVICE_SERIAL_NUMBER, DEVICE_KEY, FIRE_DETECTION_INTERVAL_SECONDS
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

    from utils.config import GAIT_DIAGNOSTIC_REACH_WARNING_RATIO
    from utils.gait_diagnostics import GaitDiagnosticLogger
    import numpy as np

    diag_logger = GaitDiagnosticLogger()
    leg_names = ("FL", "FR", "BL", "BR")
    servo_channels = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (9, 10, 11))

    def _command_name(command_data):
        _sl = command_data.get('IDstepLength', 0.0)
        _sw = command_data.get('IDstepWidth', 0.0)
        if _sl < 0:
            return "FORWARD"
        if _sl > 0:
            return "BACKWARD"
        if _sw < 0:
            return "LEFT"
        if _sw > 0:
            return "RIGHT"
        return "FORWARD"

    def _mode_name():
        if mode_control_manager is None:
            return None
        try:
            return mode_control_manager.get_current_mode()
        except Exception:
            return None

    def _tick_record(event_data):
        record = {
            "monotonic_time": event_data["monotonic_time"],
            "loop_dt": event_data["loop_dt"],
            "robot_mode": _mode_name(),
            "command": event_data["command"],
            "command_data": event_data.get("command_data"),
            "gait_phase": event_data["gait_phase"],
            "accepted": event_data["accepted"],
            "legs": [],
        }
        foot_positions = event_data.get("foot_positions")
        gait_diag = event_data.get("gait_diag") or []
        ik_diag = event_data.get("ik_diag") or {}
        servo_diag = event_data.get("servo_diag") or {}
        joint_angles = event_data.get("joint_angles")
        ik_by_leg = {item.get("leg"): item for item in ik_diag.get("legs", []) if item}
        mapped = servo_diag.get("mapped_servo_angles")
        final = servo_diag.get("final_servo_angles")
        clamped = set(servo_diag.get("clamped_channels") or [])

        for index, leg in enumerate(leg_names):
            ik_leg = ik_by_leg.get(leg, {})
            channels = servo_channels[index]
            angles_rad = joint_angles[index] if joint_angles is not None else None
            leg_record = {
                "leg": leg,
                "phase": gait_diag[index].get("phase") if index < len(gait_diag) else None,
                "state": gait_diag[index].get("state") if index < len(gait_diag) else None,
                "raw_foot_target": foot_positions[index][:3] if foot_positions is not None else None,
                "leg_local_ik_target": ik_leg.get("leg_local_target"),
                "link_lengths": ik_leg.get("link_lengths"),
                "F": ik_leg.get("F"),
                "G": ik_leg.get("G"),
                "H": ik_leg.get("H"),
                "D": ik_leg.get("D"),
                "reach_distance_ratio": ik_leg.get("reach_distance_ratio"),
                "joint_angles_rad": angles_rad,
                "joint_angles_deg": [float(v) * 180.0 / np.pi for v in angles_rad] if angles_rad is not None else None,
                "mapped_servo_angles": [mapped[channel] for channel in channels] if mapped else None,
                "clamped": any(channel in clamped for channel in channels),
                "final_servo_angles": [final[channel] for channel in channels] if final else None,
            }
            record["legs"].append(leg_record)
        return record

    def _log_anomaly(anomaly_type, event_data, reason, failed_leg=None):
        if not diag_logger.enabled:
            return
        record = _tick_record(event_data)
        record.update({
            "anomaly_type": anomaly_type,
            "failed_leg": failed_leg,
            "failure_reason": reason,
            "servo_write_occurred": (event_data.get("servo_diag") or {}).get("servo_write_occurred", False),
        })
        diag_logger.anomaly(record)

    command_queue = kb_controller.robot_commands

    def _loop():
        # Import config inside thread to ensure values are read at runtime
        from utils.config import GAIT_BODY_POS, GAIT_BODY_ROT, STAND_BODY_POS, STAND_BODY_ROT, STAND_FOOT_POSITIONS
        from utils.config import GAIT_TIMING, GAIT_TOTAL_TIME_CALC
        _GAIT_TOTAL_PERIOD = sum(GAIT_TIMING)
        _stand_pose_applied = [False]
        _was_stepping = [False]
        _last_command_name = ["STOP"]
        _last_loop_mono = [time.monotonic()]

        def _apply_stand_pose_once():
            if _stand_pose_applied[0]:
                return
            stand_foot_positions = np.array(STAND_FOOT_POSITIONS, dtype=np.float64)
            stand_joint_angles = kinematics.solve_complete_inverse_kinematics(
                stand_foot_positions, STAND_BODY_POS, STAND_BODY_ROT
            )
            servo_manager.execute_servo_motion(stand_joint_angles)
            _stand_pose_applied[0] = True

        _last_known_command = [{'IDstepLength': 0.0, 'IDstepWidth': 0.0, 'IDstepAlpha': 0.0, 'StartStepping': False}]

        def _drain_latest():
            latest = None
            while True:
                try:
                    latest = command_queue.get_nowait()
                except Exception:
                    break
            if latest is not None:
                _last_known_command[0] = latest
            return _last_known_command[0]

        while True:
            command_data = _drain_latest()
            _loop_mono = time.monotonic()
            _loop_dt = _loop_mono - _last_loop_mono[0]
            _last_loop_mono[0] = _loop_mono
            _event_data = {
                "monotonic_time": _loop_mono,
                "loop_dt": _loop_dt,
                "command": _command_name(command_data),
                "command_data": dict(command_data),
                "gait_phase": None,
                "accepted": False,
            }

            try:
                # Hold a known stand pose when idle or stopped.
                if not command_data.get("StartStepping", False):
                    if _was_stepping[0]:
                        _was_stepping[0] = False
                        _last_command_name[0] = "STOP"
                    _apply_stand_pose_once()
                    time.sleep(0.02)
                    continue

                # Only execute physical movement when the robot is in MANUAL mode
                if mode_control_manager is not None and not mode_control_manager.is_manual():
                    time.sleep(0.02)
                    continue

                # Full pipeline: gait trajectory → inverse kinematics → servo output
                _gait_time = time.time()
                _phase_ms = int((_gait_time * GAIT_TOTAL_TIME_CALC) % _GAIT_TOTAL_PERIOD)
                _event_data["gait_phase"] = _phase_ms
                if diag_logger.enabled:
                    foot_positions, gait_diag = gait.calculate_leg_positions(_gait_time, command_data, include_diagnostics=True)
                else:
                    foot_positions = gait.calculate_leg_positions(_gait_time, command_data)
                    gait_diag = None
                ik_diag = {} if diag_logger.enabled else None
                _event_data.update({
                    "foot_positions": foot_positions,
                    "gait_diag": gait_diag,
                    "ik_diag": ik_diag,
                })
                joint_angles = kinematics.solve_complete_inverse_kinematics(
                    foot_positions, GAIT_BODY_POS, GAIT_BODY_ROT, diagnostics=ik_diag
                )
                servo_diag = {} if diag_logger.enabled else None
                _event_data["joint_angles"] = joint_angles
                _event_data["servo_diag"] = servo_diag
                servo_manager.execute_servo_motion(joint_angles, diagnostics=servo_diag)
                _stand_pose_applied[0] = False
                _was_stepping[0] = True
                _event_data["accepted"] = True

                try:
                    _cmd_name = _event_data["command"]
                    _last_command_name[0] = _cmd_name
                except Exception:
                    pass

                if diag_logger.enabled:
                    record = _tick_record(_event_data)
                    diag_logger.snapshot(record)
                    for leg in record["legs"]:
                        ratio = leg.get("reach_distance_ratio")
                        if ratio is not None and ratio >= GAIT_DIAGNOSTIC_REACH_WARNING_RATIO:
                            _log_anomaly("near_reach_boundary", _event_data, f"reach_distance_ratio={ratio}", leg.get("leg"))
                    if servo_diag.get("clamped_channels"):
                        _log_anomaly("servo_clamp", _event_data, f"clamped_channels={servo_diag.get('clamped_channels')}")

            except Exception as e:
                _event_data["failure_reason"] = str(e)
                if diag_logger.enabled:
                    ik_diag = _event_data.get("ik_diag")
                    failed_leg = ik_diag.get("failed_leg") if isinstance(ik_diag, dict) else None
                    _log_anomaly(type(e).__name__, _event_data, str(e), failed_leg)
                logger.log_error("GaitLoop", str(e))
            # ~50 Hz max update rate
            time.sleep(0.02)

    thread = threading.Thread(target=_loop, daemon=True, name="gait-loop")
    thread.start()
    logger.log_system_state("GAIT_LOOP_STARTED")
    print("Gait loop started (servo motion active)")


def _apply_fire_state_transition(state_machine, detection_state, logger):
    """
    Apply StateMachine transitions based on FireDetector.evaluate() result.

    Transition rules (only attempted when transition is valid):
    - SUSPECTED_FIRE → DETECTING      (robot is investigating a potential fire)
    - VERIFIED_FIRE  → FIRE_DETECTED  (confirmed fire; REPORTING is triggered
                                       externally by the telemetry layer after
                                       a successful server report)
    - NORMAL         → PATROLLING     (resume patrol when suspicion clears)

    Invalid transitions (e.g. IDLE → DETECTING) are silently skipped because
    the robot may not be in PATROLLING when detection runs at startup.
    StateMachine.transition_to() already logs rejected transitions internally.
    """
    if state_machine is None:
        return

    from detection.fire_events import DetectionState
    from utils.state_machine import RobotState

    try:
        current = state_machine.get_state()

        if detection_state == DetectionState.SUSPECTED_FIRE:
            if current == RobotState.PATROLLING:
                state_machine.transition_to(RobotState.DETECTING)
        elif detection_state == DetectionState.VERIFIED_FIRE:
            if current == RobotState.PATROLLING:
                state_machine.transition_to(RobotState.DETECTING)
            if state_machine.get_state() == RobotState.DETECTING:
                state_machine.transition_to(RobotState.FIRE_DETECTED)
        elif detection_state == DetectionState.NORMAL:
            if current == RobotState.DETECTING:
                state_machine.transition_to(RobotState.PATROLLING)
    except Exception as e:
        logger.log_error("FireDetectionLoop._apply_fire_state_transition", str(e))


def _start_fire_detection_loop(logger, fire_detector, camera_vision, state_machine=None):
    """
    Start a thread that calls FireDetector.evaluate() at a fixed interval.

    Skips evaluation only when fire_detector is unavailable.
    camera_vision is accepted for interface symmetry but is not used directly
    here; it must be wired into fire_detector.camera_vision before this call.
    When state_machine is provided, StateMachine transitions are applied after
    each evaluate() call based on the returned DetectionState.
    Exceptions inside evaluate() are logged but do not stop the loop.
    """
    if fire_detector is None:
        logger.log_system_state("FIRE_DETECTION_LOOP_SKIPPED fire_detector=None")
        print("Fire detection loop skipped: FireDetector unavailable")
        return None, None

    stop_event = threading.Event()

    def _loop():
        logger.log_system_state(
            f"FIRE_DETECTION_LOOP_STARTED interval={FIRE_DETECTION_INTERVAL_SECONDS}s"
        )
        while not stop_event.is_set():
            try:
                detection_state, _alert, _report = fire_detector.evaluate()
                _apply_fire_state_transition(state_machine, detection_state, logger)
            except Exception as e:
                logger.log_error("FireDetectionLoop", str(e))
            stop_event.wait(FIRE_DETECTION_INTERVAL_SECONDS)
        logger.log_system_state("FIRE_DETECTION_LOOP_STOPPED")

    thread = threading.Thread(target=_loop, name="fire-detection-loop")
    thread.start()
    print(f"Fire detection loop started (interval={FIRE_DETECTION_INTERVAL_SECONDS}s)")
    return stop_event, thread


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
    fire_detection_stop_event = None
    fire_detection_thread = None

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

        if runtime.fire_detector is not None:
            runtime.fire_detector.camera_vision = camera_vision
            logger.log_system_state(f"FIRE_DETECTOR_CAMERA_VISION_WIRED camera_vision={camera_vision is not None}")

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
        fire_detection_stop_event, fire_detection_thread = _start_fire_detection_loop(
            logger,
            runtime.fire_detector,
            camera_vision,
            state_machine=runtime.state_machine,
        )

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
                        spring_telemetry = SpringTelemetry(_spring_client, data_collector=_collector, state_machine=runtime.state_machine)
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
        if fire_detection_stop_event is not None:
            fire_detection_stop_event.set()
        if fire_detection_thread is not None:
            try:
                fire_detection_thread.join(timeout=FIRE_DETECTION_INTERVAL_SECONDS + 1.0)
            except Exception:
                pass
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
