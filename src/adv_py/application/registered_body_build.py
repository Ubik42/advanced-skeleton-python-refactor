"""Build and register a complete Body character in one host transaction."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

from adv_py.core.character_registry import CharacterRegistration
from adv_py.core.fit_settings import FitSkeletonValidationError

from .body_character_rig import BuildBodyCharacterRig, BodyCharacterRigBuildResult
from .character_registry import RegisterBodyCharacter
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


class BuildRegisteredBodyCharacter:
    """Materialize Body, controls and registry as one undoable operation."""

    def __init__(self, host):
        self._host = host

    def apply(self, container_name: str = "FitSkeleton", *,
              axial_description=None, include_head_aim: bool = False
              ) -> RegisteredBodyBuildResult:
        preview = BuildOrientedBodySkeleton(self._host).plan(container_name)
        if not preview.ready:
            raise FitSkeletonValidationError(
                "角色构建预检失败，场景未修改：" + "；".join(preview.blockers))
        with self._host.transaction("构建并登记完整 Body 角色"):
            joined = _JoinedTransactionHost(self._host)
            skeleton = BuildOrientedBodySkeleton(joined).apply(container_name)
            rig = BuildBodyCharacterRig(joined).apply(container_name,
                include_torso=True, include_spine_ik=True,
                include_control_spaces=True, axial_description=axial_description,
                include_head_aim=include_head_aim)
            registration = RegisterBodyCharacter(joined).apply(rig)
            if len(registration.body) != len(skeleton.snapshot.joints):
                raise RuntimeError("登记骨架数量与本次构建结果不一致")
        return RegisteredBodyBuildResult(skeleton, rig, registration)
