"""Native RP Fit pole-plane display, asFitDisplayPoleVector 4307–4420."""
from dataclasses import dataclass

from .fit_ik import fit_joint_ik_info


@dataclass(frozen=True, slots=True)
class SourceFitPoleVector:
    name: str
    start: str
    middle: str
    end: str

    @property
    def stem(self):
        return 'VisualizePoleVector_'+self.name


def source_fit_pole_vectors(hierarchy, labels, ordered_paths=None):
    paths = tuple(joint.path for joint in hierarchy.joints) if ordered_paths is None else tuple(ordered_paths)
    known = {joint.path for joint in hierarchy.joints}
    if len(set(paths)) != len(paths) or set(paths)-known:
        raise ValueError('Fit PoleVector 遍历关节身份无效')
    result = []
    for path in paths:
        info = fit_joint_ik_info(hierarchy, labels, path)
        if info is not None and info.start == path and info.solver == 'ikRPsolver':
            result.append(SourceFitPoleVector(info.name, info.start, info.middle, info.end))
    return tuple(result)
