"""One continuous original AutoFit operation, with native early returns."""
from dataclasses import dataclass

from adv_py.core.original_auto_face_fitting import original_auto_face_steps


@dataclass(frozen=True, slots=True)
class OriginalAutoFaceFittingResult:
    profile: str
    rows: tuple[tuple[str,str,str],...]
    finished: bool
    build_result: dict | None = None


class AutoFitOriginalFace:
    def __init__(self,host):self.host=host

    def apply(self):
        host=self.host
        profile=host.detect_original_auto_face_profile()
        if profile is None:return None
        if not host.confirm_original_auto_face_fitting(profile):return None
        from .face_input_upgrade import check_original_face_input_upgrade
        check_original_face_input_upgrade(host)
        rows=[]
        with host.transaction('原版 '+profile.title+' AutoFit'):
            if not host.prepare_original_auto_face_inputs(profile):
                return OriginalAutoFaceFittingResult(profile.code,(),False)
            for side in ('Right','Left'):
                host.set_original_auto_face_side(side)
                for step in original_auto_face_steps(profile,side):
                    host.create_original_auto_face_step(step)
                    rows.append((side,step.section,step.part))
            host.finish_original_auto_face_fitting(profile)
        # Native AutoFit commits its fitting even when the final build is
        # declined. The full Face build owns its own operation boundary.
        built = host.build_original_auto_face_if_confirmed()
        return OriginalAutoFaceFittingResult(profile.code,tuple(rows),True,built)
