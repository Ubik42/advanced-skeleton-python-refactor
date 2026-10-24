"""Scale an imported Fit using the original geometry measurement phase."""
from dataclasses import dataclass
from adv_py.core.fit_auto_scale import FitAutoScalePlan


@dataclass(frozen=True, slots=True)
class FitAutoScaleResult:
    plan: FitAutoScalePlan | None
    eye_placed: bool


class AutoScaleFit:
    def __init__(self, host):
        self._host=host

    def apply(self, container='FitSkeleton', *, skin=(), all_objects=(), right_eye=()):
        skin,all_objects,right_eye=tuple(skin),tuple(all_objects),tuple(right_eye)
        # Original asFitAutoScale sets a marker and delegates to AutoPlace.
        # Keep model checks, the actual CombinedSkin and cleanup together.
        with self._host.transaction('Fit auto scale from geometry'):
            return self._host.auto_scale_fit(container,skin,all_objects,right_eye)
