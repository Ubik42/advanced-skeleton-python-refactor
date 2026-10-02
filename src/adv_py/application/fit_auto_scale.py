"""Scale an imported Fit using the original geometry measurement phase."""
from dataclasses import dataclass
from adv_py.core.fit_auto_scale import FitAutoScalePlan, plan_fit_auto_scale


@dataclass(frozen=True, slots=True)
class FitAutoScaleResult:
    plan: FitAutoScalePlan
    eye_placed: bool


class AutoScaleFit:
    def __init__(self, host):
        self._host=host

    def apply(self, container='FitSkeleton', *, skin=(), all_objects=(), right_eye=()):
        skin,all_objects,right_eye=tuple(skin),tuple(all_objects),tuple(right_eye)
        # Measurement duplicates and final writes share one undo transaction;
        # no temporary geometry or partly moved Fit survives an exception.
        with self._host.transaction('Fit auto scale from geometry'):
            snapshot=self._host.capture_fit_auto_scale(container,skin,all_objects,right_eye)
            plan=plan_fit_auto_scale(snapshot)
            eye=self._host.apply_fit_auto_scale(plan,right_eye,skin,all_objects)
        return FitAutoScaleResult(plan,eye)
