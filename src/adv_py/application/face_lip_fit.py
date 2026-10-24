"""Coordinate original Lip edge traversal and scene creation."""
from adv_py.core.face_lip_fit import plan_lip_fit

class CreateFaceLipFit:
    def __init__(self,host): self.host=host
    def apply(self,part):
        with self.host.transaction("创建 Lip "+part+" Fit"):
            # The original samples the previous fit through a temporary
            # closestPointOnMesh. Capture belongs to the same undo boundary.
            source=self.host.capture_lip_fit_input(part)
            plan=plan_lip_fit(source)
            self.host.preflight_lip_fit(plan)
            return self.host.create_lip_fit(plan)

class SwapFaceLipFit:
    def __init__(self,host): self.host=host
    def apply(self,part):
        with self.host.transaction("交换 Lip "+part+" 上下 Fit"):
            return self.host.swap_lip_upper_lower(part)
