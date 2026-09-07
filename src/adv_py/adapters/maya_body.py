from __future__ import annotations

from adv_py.core.body_skeleton import (
    BodyJointSpec,
    BodyJointState,
    BodySkeletonSnapshot,
)
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_symmetry import FitBuildSide

from .maya_fit import MayaFitJointHost


_MAYA_SIDE_FROM_CORE = {
    FitBuildSide.MIDDLE: 0,
    FitBuildSide.LEFT: 1,
    FitBuildSide.RIGHT: 2,
}
_CORE_SIDE_FROM_MAYA = {value: key for key, value in _MAYA_SIDE_FROM_CORE.items()}


class MayaBodyBuildHost(MayaFitJointHost):
    """Maya scene adapter for the first materialized Body skeleton stage."""

    def create_body_joint(self, spec: BodyJointSpec) -> str:
        self._require_transaction()
        if self.find_name_collisions(spec.name):
            raise FitSkeletonValidationError(
                f"同名节点已存在，拒绝创建构建关节：{spec.name}"
            )
        parent = None
        if spec.parent_path is not None:
            matches = self._cmds.ls(spec.parent_path, long=True, type="joint") or []
            if len(matches) != 1:
                raise FitSkeletonValidationError(
                    f"构建关节父级在执行前失效：{spec.parent_path}"
                )
            parent = matches[0]
        options = {
            "name": spec.name,
            "skipSelect": True,
        }
        if parent is not None:
            options["parent"] = parent
        joint = self._cmds.createNode("joint", **options)
        self._transaction_changed = True
        path = (self._cmds.ls(joint, long=True) or [joint])[0]
        self._cmds.xform(
            path,
            worldSpace=True,
            translation=spec.world_position,
        )
        self.set_joint_label(path, spec.label)
        self._cmds.setAttr(f"{path}.side", _MAYA_SIDE_FROM_CORE[spec.side])
        return path

    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot:
        roots = self._cmds.ls(root_name, long=True, type="joint") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError(
                f"Body skeleton 根关节无效：{root_name}"
            )
        root = roots[0]
        paths = self._cmds.listRelatives(
            root,
            allDescendents=True,
            type="joint",
            fullPath=True,
        ) or []
        paths.append(root)
        paths = sorted(set(paths), key=lambda path: (path.count("|"), path))
        states: list[BodyJointState] = []
        for path in paths:
            parents = self._cmds.listRelatives(path, parent=True, fullPath=True) or []
            position = self._cmds.xform(
                path,
                query=True,
                worldSpace=True,
                translation=True,
            )
            side_code = int(self._cmds.getAttr(f"{path}.side"))
            try:
                side = _CORE_SIDE_FROM_MAYA[side_code]
            except KeyError as error:
                raise FitSkeletonValidationError(
                    f"构建关节侧向值无效：{path}.side={side_code}"
                ) from error
            joint_orient = self._cmds.getAttr(f"{path}.jointOrient")[0]
            rotation = self._cmds.getAttr(f"{path}.rotate")[0]
            states.append(
                BodyJointState(
                    path=path,
                    name=path.rsplit("|", 1)[-1].rsplit(":", 1)[-1],
                    parent_path=parents[0] if parents else None,
                    side=side,
                    world_position=tuple(float(value) for value in position),
                    label=self.read_joint_label(path),
                    joint_orient=tuple(float(value) for value in joint_orient),
                    rotation=tuple(float(value) for value in rotation),
                )
            )
        return BodySkeletonSnapshot(root, tuple(states))
