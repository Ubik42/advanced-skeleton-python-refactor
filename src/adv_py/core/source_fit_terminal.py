"""Carry the native detached-child end-joint analysis into a staged Fit.

NonSymmetryFitJoints is a legacy scene container. Its joints are not part of
the Fit build list; previousParent only changes the analyzed end-joint bit
(MEL 79088–79095). A staging namespace cannot resolve those original names.
Keep Fit-relative identities rather than inventing children in the Fit DAG.
"""
from dataclasses import dataclass

from .fit_settings import FitSkeletonValidationError


def _relative_identity(container, path):
    if not path.startswith(container+'|'):
        raise FitSkeletonValidationError('非对称末端来源不属于当前 Fit')
    return tuple(part.rsplit(':',1)[-1] for part in path[len(container)+1:].split('|'))


@dataclass(frozen=True, slots=True)
class SourceFitTerminalState:
    non_terminal: tuple[tuple[str, ...], ...] = ()

    def __post_init__(self):
        if (not isinstance(self.non_terminal, tuple)
                or any(not isinstance(row, tuple) for row in self.non_terminal)):
            raise FitSkeletonValidationError('非对称末端相对身份必须是不可变路径')
        if (len(set(self.non_terminal))!=len(self.non_terminal)
                or any(not row or any(not isinstance(part,str) or not part
                       or any(token in part for token in '|:.') for part in row)
                       for row in self.non_terminal)):
            raise FitSkeletonValidationError('非对称末端相对身份无效')

    def resolve(self, hierarchy):
        by_identity={}
        for node in hierarchy.joints:
            key=_relative_identity(hierarchy.container,node.path)
            if key in by_identity:
                raise FitSkeletonValidationError('暂存 Fit 非对称末端身份重复')
            by_identity[key]=node.path
        missing=set(self.non_terminal)-set(by_identity)
        if missing:
            raise FitSkeletonValidationError('暂存 Fit 丢失非对称末端来源：'+repr(sorted(missing)))
        return tuple(by_identity[key] for key in self.non_terminal)


def source_fit_terminal_state(hierarchy, non_terminal):
    known={node.path for node in hierarchy.joints}
    if set(non_terminal)-known:
        raise FitSkeletonValidationError('非对称末端来源不在 Fit 快照中')
    return SourceFitTerminalState(tuple(sorted(
        {_relative_identity(hierarchy.container,path) for path in non_terminal})))
