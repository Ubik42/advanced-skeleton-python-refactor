"""Build and verify the paired eyelid joint and Skin stage."""
from __future__ import annotations


class BuildFaceEyeLids:
    def __init__(self, host) -> None:
        self.host = host

    def execute(self) -> dict:
        result = self.host.build()
        mobile_apertures = (set(result.get("aperture_sides", ())) -
                            set(result.get("stationary_aperture_sides", ())))
        expected_controls = 8 + 2 * len(mobile_apertures)
        if (len(result["controls"]) != expected_controls
                or len(result["joints"]) < 16
                or not all(result["area_vertices"].values())):
            raise RuntimeError("眼睑绑定写后读回不完整")
        return result
