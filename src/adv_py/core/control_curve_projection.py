"""ADV 6.925 asProjectControlCurve point selection, MEL 77032–77130."""
from dataclasses import dataclass
from fnmatch import fnmatchcase

from .control_curves import ControlCurveState


def projection_factor(control, index, local_point):
    """None denotes the source's unchanged CV; otherwise its radial factor."""
    if all(-.001 < value < .001 for value in local_point):
        return None
    name=control.rsplit('|',1)[-1].rsplit(':',1)[-1]
    if fnmatchcase(name,'FKShoulder_*') and index<3:
        return None
    if fnmatchcase(name,'FKHip_*') and index<3:
        return None
    if fnmatchcase(name,'FKCup_*') and 1<index<5:
        return None
    if fnmatchcase(name,'FKThumbFinger[1-2]_*') and index<3:
        return None
    if 'Eye' in name or 'Jaw' in name:
        return None
    if name=='FKChest_M' and index in (1,5):
        return None
    return 1.3*1.2 if name=='RootX_M' and index in (5,15,25,35) else 1.3


def projection_cv_count(form, spans, degree):
    return spans if form==2 else spans+degree


@dataclass(frozen=True,slots=True)
class ControlCurveProjectionResult:
    mesh: str
    before: tuple[ControlCurveState,...]
    verified: tuple[ControlCurveState,...]
    projected_points: int
