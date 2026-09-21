"""Generated full-body fixture, usable in Maya or mayapy; no supplied assets.

Call build_character() in a fresh Z-up scene with Undo enabled. The result is
one Undo operation. This proxy uses explicit two-joint fixture weights, not a
production mesh or a general automatic weighting algorithm.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from math import sqrt

from adv_py.adapters import MayaBodyBuildHost
from adv_py.application import (
    BindSkin, BuildBodyCharacterRig, BuildOrientedBodySkeleton,
    BuildSyntheticBodySourceFit, BuildSyntheticBodyWithHandSourceFit,
    CreateFitSkeleton, EditSkinWeights,
)
from adv_py.application.body_character_rig import BodyCharacterRigBuildResult
from adv_py.core.skin_weights import SkinInfluenceWeight, SkinVertexWeights


class CharacterExampleHost(MayaBodyBuildHost):
    """Join application transactions only within this all-or-nothing example.

    Inner failures must propagate; the outer Maya transaction owns rollback.
    The standard adapter continues to reject nested transactions.
    """
    @contextmanager
    def transaction(self, label):
        if self._transaction_active:
            yield
        else:
            with super().transaction(label):
                yield

    def create_proxy(self, body):
        self._require_transaction()
        c = self._cmds
        by_path = {j.path: j for j in body.joints}
        segments = []
        parts = []
        self._transaction_changed = True
        for joint in body.joints:
            parent = by_path.get(joint.parent_path)
            if parent is None:
                continue
            delta = tuple(b-a for a,b in zip(parent.world_position, joint.world_position))
            length = sqrt(sum(v*v for v in delta))
            if length < 1e-5:
                continue
            segments.append((parent.path, joint.path, parent.world_position, delta, length*length))
            part = c.polyCylinder(
                name="AdvPy_ProxyPart", axis=delta, height=length,
                radius=min(0.35, length*0.12), subdivisionsX=4, subdivisionsY=2,
                constructionHistory=False,
            )[0]
            c.xform(part, worldSpace=True, translation=tuple((a+b)*0.5 for a,b in zip(parent.world_position,joint.world_position)))
            parts.append(part)
        mesh = c.polyUnite(parts, name="AdvPy_CharacterProxy", constructionHistory=False)[0]
        # polyUnite may retain empty input transforms; they are fixture-owned.
        remaining = [part for part in parts if c.objExists(part)]
        if remaining:
            c.delete(remaining)
        mesh = c.ls(mesh, long=True)[0]
        points = c.xform(mesh + ".vtx[*]", query=True, worldSpace=True, translation=True)
        vertices = []
        for index in range(len(points)//3):
            point = points[index*3:index*3+3]
            candidates = []
            for parent, child, origin, delta, length2 in segments:
                t = max(0.0, min(1.0, sum((p-a)*d for p,a,d in zip(point,origin,delta))/length2))
                distance2 = sum((p-a-t*d)**2 for p,a,d in zip(point,origin,delta))
                candidates.append((distance2, parent, child, t))
            _, parent, child, t = min(candidates)
            # Every row is explicit and normalized; middle rings blend both bones.
            t = max(0.05, min(0.95, t))
            vertices.append(SkinVertexWeights(index, (
                SkinInfluenceWeight(parent, 1-t), SkinInfluenceWeight(child, t),
            )))
        return mesh, tuple(vertices)


@dataclass(frozen=True)
class CharacterExample:
    host: CharacterExampleHost
    container: str
    rig: BodyCharacterRigBuildResult
    mesh: str
    skin: str
    weights: tuple[SkinVertexWeights, ...]


def build_character(*, with_hand=True, host=None):
    from maya import cmds
    if not isinstance(with_hand, bool):
        raise ValueError("with_hand must be a bool")
    if (cmds.ls(type="joint") or cmds.ls(type="mesh")
            or cmds.ls("AdvPy_*", "FitSkeleton")
            or cmds.upAxis(query=True, axis=True) != "z"
            or cmds.currentUnit(query=True, angle=True) != "deg"
            or not cmds.undoInfo(query=True, state=True)):
        raise ValueError("Example requires a fresh Z-up, degree scene with Undo enabled")
    host = host or CharacterExampleHost()
    if not isinstance(host, CharacterExampleHost) or host._transaction_active:
        raise ValueError("Example requires an idle CharacterExampleHost")
    selection = cmds.ls(selection=True, long=True) or []
    with host.transaction("Build generated character with explicit skin"):
        try:
            container = CreateFitSkeleton(host).apply().state.path
            (BuildSyntheticBodyWithHandSourceFit if with_hand else BuildSyntheticBodySourceFit)(host).apply(container)
            body = BuildOrientedBodySkeleton(host).apply(container).snapshot
            rig = BuildBodyCharacterRig(host).apply(
                container, include_torso=True, include_spine_ik=True,
                include_control_spaces=True,
            )
            mesh, weights = host.create_proxy(body)
            skin = "AdvPy_CharacterSkin"
            BindSkin(host).apply(mesh, tuple(j.path for j in body.joints), skin_name=skin, maximum_influences=2)
            EditSkinWeights(host).apply(skin, mesh, weights)
            return CharacterExample(host, container, rig, mesh, skin, weights)
        finally:
            cmds.select(selection, replace=True) if selection else cmds.select(clear=True)
