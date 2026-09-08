from __future__ import annotations

from adv_py.core.mocap_source import (
    MOCAP_TRANSFORM_ATTRIBUTES,
    MocapChannelSnapshot,
    MocapDriverKind,
    MocapJointSnapshot,
    MocapSourceSnapshot,
    MocapSourceValidationError,
)


class MayaMocapSourceReader:
    """Read an explicit Maya joint hierarchy without modifying scene state."""

    def __init__(self) -> None:
        from maya import cmds  # type: ignore[import-not-found]

        self._cmds = cmds

    def capture_mocap_source(self, root_name: str) -> MocapSourceSnapshot:
        roots = self._cmds.ls(root_name, long=True, type="joint") or []
        if len(roots) != 1:
            raise MocapSourceValidationError(
                f"MoCap 根关节必须明确且唯一：{root_name}"
            )
        root = roots[0]
        paths = self._cmds.listRelatives(
            root,
            allDescendents=True,
            type="joint",
            fullPath=True,
        ) or []
        paths.append(root)
        ordered_paths = sorted(set(paths), key=lambda path: (path.count("|"), path))
        joints: list[MocapJointSnapshot] = []
        channels: list[MocapChannelSnapshot] = []

        for path in ordered_paths:
            leaf = path.rsplit("|", 1)[-1]
            namespace, separator, name = leaf.rpartition(":")
            if not separator:
                namespace, name = "", leaf
            parents = self._cmds.listRelatives(
                path, parent=True, fullPath=True
            ) or []
            joint_parent = None
            if parents and self._cmds.nodeType(parents[0]) == "joint":
                joint_parent = parents[0]
            joints.append(MocapJointSnapshot(
                path=path,
                name=name,
                namespace=namespace,
                joint_parent=joint_parent,
            ))

            for attribute in MOCAP_TRANSFORM_ATTRIBUTES:
                source_plugs = self._cmds.listConnections(
                    f"{path}.{attribute}",
                    source=True,
                    destination=False,
                    plugs=True,
                ) or []
                if not source_plugs:
                    continue
                if len(source_plugs) != 1:
                    raise MocapSourceValidationError(
                        f"MoCap 通道输入不唯一：{path}.{attribute}"
                    )
                source_plug = str(source_plugs[0])
                source_node = source_plug.rsplit(".", 1)[0]
                node_type = str(self._cmds.nodeType(source_node))
                is_animation_curve = node_type.startswith("animCurve")
                key_times = ()
                if is_animation_curve:
                    values = self._cmds.keyframe(
                        source_node, query=True, timeChange=True
                    ) or []
                    key_times = tuple(sorted({float(value) for value in values}))
                channels.append(MocapChannelSnapshot(
                    joint_path=path,
                    attribute=attribute,
                    driver_kind=(
                        MocapDriverKind.ANIMATION_CURVE
                        if is_animation_curve
                        else MocapDriverKind.OTHER
                    ),
                    driver_path=source_plug,
                    key_times=key_times,
                ))

        return MocapSourceSnapshot(
            root=root,
            joints=tuple(joints),
            channels=tuple(channels),
        )
