"""Read a selected Maya joint hierarchy without changing the source rig."""
from __future__ import annotations

from adv_py.application.source_skeleton_fit import SourceSkeletonJoint

from .maya_face import MayaFaceHost


class MayaSourceSkeletonFitHost(MayaFaceHost):
    def capture_source_skeleton(self, root: str) -> tuple[SourceSkeletonJoint, ...]:
        from maya import cmds

        matches = cmds.ls(root, long=True, type="joint") or []
        if len(matches) != 1:
            raise ValueError("请选择唯一的来源根关节")
        root_path = matches[0]
        paths = [root_path] + (cmds.listRelatives(root_path,
            allDescendents=True, type="joint", fullPath=True) or [])
        paths = sorted(set(paths), key=lambda path: (path.count("|"), path))
        path_set = set(paths)
        joints = []
        def optional_int(path: str, attribute: str) -> int | None:
            return (int(cmds.getAttr(path + "." + attribute))
                    if cmds.attributeQuery(attribute, node=path, exists=True)
                    else None)

        def optional_bool(path: str, attribute: str) -> bool | None:
            return (bool(cmds.getAttr(path + "." + attribute))
                    if cmds.attributeQuery(attribute, node=path, exists=True)
                    else None)

        for path in paths:
            parent = (cmds.listRelatives(path, parent=True,
                                        fullPath=True) or [None])[0]
            while parent and parent not in path_set:
                parent = (cmds.listRelatives(parent, parent=True,
                                            fullPath=True) or [None])[0]
            position = tuple(float(value) for value in cmds.xform(
                path, query=True, worldSpace=True, translation=True))
            joints.append(SourceSkeletonJoint(path,
                path.rsplit("|", 1)[-1], parent, position,
                optional_int(path, "twistJoints"),
                optional_int(path, "inbetweenJoints"),
                optional_bool(path, "unTwister")))
        return tuple(joints)
