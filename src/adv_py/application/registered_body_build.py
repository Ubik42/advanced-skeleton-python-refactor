"""Build and register a complete Body character in one host transaction."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

from adv_py.core.character_registry import CharacterRegistration
from adv_py.core.body_description import BodyAxialDescription
from adv_py.core.fit_settings import FitSkeletonValidationError

from .axial_part_deform import BuildAxialPartDeform
from .body_character_rig import BuildBodyCharacterRig, BodyCharacterRigBuildResult
from .character_registry import RegisterBodyCharacter
from .finger_mid_deform import BuildFingerMidDeform
from .limb_part_deform import BuildLimbPartDeform
from .oriented_body_skeleton import (BuildOrientedBodySkeleton,
    OrientedBodySkeletonBuildResult)


class _JoinedTransactionHost:
    """Forward host operations while the outer build owns the undo chunk."""

    def __init__(self, host):
        self._host = host

    def __getattr__(self, name):
        return getattr(self._host, name)

    @contextmanager
    def transaction(self, label):
        del label
        yield


@dataclass(frozen=True, slots=True)
class RegisteredBodyBuildResult:
    skeleton: OrientedBodySkeletonBuildResult
    rig: BodyCharacterRigBuildResult
    registration: CharacterRegistration
    segment_influences: tuple[str, ...] = ()


class BuildRegisteredBodyCharacter:
    """Materialize Body, controls and registry as one undoable operation."""

    def __init__(self, host):
        self._host = host

    def apply(self, container_name: str = "FitSkeleton", *,
              axial_description=None, include_head_aim: bool = False,
              infer_missing_labels: bool = False,
              include_segment_influences: bool = False,
              ) -> RegisteredBodyBuildResult:
        preview = BuildOrientedBodySkeleton(self._host).plan(
            container_name, infer_missing_labels=infer_missing_labels)
        if not preview.ready:
            raise FitSkeletonValidationError(
                "角色构建预检失败，场景未修改：" + "；".join(preview.blockers))
        with self._host.transaction("构建并登记完整 Body 角色"):
            joined = _JoinedTransactionHost(self._host)
            skeleton = BuildOrientedBodySkeleton(joined).apply(
                container_name, infer_missing_labels=infer_missing_labels)
            rig = BuildBodyCharacterRig(joined).apply(container_name,
                include_torso=True, include_spine_ik=True,
                include_control_spaces=True, axial_description=axial_description,
                include_head_aim=include_head_aim)
            registration = RegisterBodyCharacter(joined).apply(rig)
            if len(registration.body) != len(skeleton.snapshot.joints):
                raise RuntimeError("登记骨架数量与本次构建结果不一致")
            segments: list[str] = []
            if include_segment_influences:
                # The five-finger and described axial helpers are optional Body
                # branches; the limb segments exist on every supported Body.
                body_names = {item.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                              for item in registration.body}
                axial = axial_description or BodyAxialDescription()
                if set(axial.spine + axial.neck) <= body_names:
                    segments.extend(spec.path for spec in
                        BuildAxialPartDeform(joined).apply(
                            axial_description=axial))
                original_fingers = {f"{digit}Finger{index}_{side}"
                                    for side in ("R", "L")
                                    for digit in ("Thumb", "Index", "Middle", "Ring", "Pinky")
                                    for index in (2, 3)}
                canonical_fingers = {f"{digit}{index}_{side}"
                                     for side in ("R", "L")
                                     for digit in ("Thumb", "Index", "Middle", "Ring", "Pinky")
                                     for index in (2, 3)}
                if (original_fingers <= body_names
                        or canonical_fingers <= body_names):
                    segments.extend(spec.path for spec in
                        BuildFingerMidDeform(joined).apply())
                for spec in BuildLimbPartDeform(joined).apply():
                    segments.extend((spec.part1, spec.part2))
        return RegisteredBodyBuildResult(skeleton, rig, registration,
                                         tuple(segments))
