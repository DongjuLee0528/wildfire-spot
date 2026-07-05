"""
Camera pan/tilt gimbal controller.

Thin delegation wrapper over CameraControlManager.
Pan uses a 360-degree continuous servo (throttle-controlled).
Tilt uses a 180-degree positional servo (angle-controlled).
"""

from hardware.camera_control_manager import CameraControlManager


class PanTiltController:
    """
    High-level controller for the camera pan/tilt gimbal.

    Delegates all pan and tilt commands to a CameraControlManager instance.
    """

    def __init__(self, camera_manager: CameraControlManager):
        """
        Args:
            camera_manager: CameraControlManager instance that drives the hardware servos.
        """
        self._camera = camera_manager

    def camera_left(self):
        """Start panning the camera to the left (continuous servo)."""
        return self._camera.camera_left()

    def camera_right(self):
        """Start panning the camera to the right (continuous servo)."""
        return self._camera.camera_right()

    def camera_pan_stop(self):
        """Stop camera panning."""
        return self._camera.camera_pan_stop()

    def camera_up(self):
        """Tilt the camera up by one step."""
        return self._camera.camera_up()

    def camera_down(self):
        """Tilt the camera down by one step."""
        return self._camera.camera_down()

    def camera_center(self):
        """Stop panning and return tilt to the initial centre angle."""
        return self._camera.camera_center()

    def get_camera_position(self):
        """Return the current camera position without issuing any movement."""
        return self._camera.get_camera_position()

    def is_available(self):
        """Return True if the underlying camera hardware is ready."""
        return self._camera.is_available()

    def reset(self):
        """Reset the camera to the centre position."""
        return self._camera.camera_center()
