from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.character_registry import CharacterChannel, CharacterRegistration, REGISTRY_NAME


class CharacterRegistryHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def describe_character_registration(self, rig, channels: tuple[CharacterChannel, ...]) -> CharacterRegistration: ...
    def preflight_character_registration(self, registration: CharacterRegistration) -> None: ...
    def create_character_registration(self, registration: CharacterRegistration) -> None: ...
    def read_character_registration(self, name: str) -> CharacterRegistration: ...
    def discover_character_registrations(self) -> tuple[str, ...]: ...


def character_channels(rig):
    """Declare user channels from the actual build plans, never scene selection."""
    p = rig.plan
    if not p.torso or not p.torso.torso.spine or not p.control_spaces:
        raise ValueError("角色登记要求完整 Torso、Spine IK 和控制空间")
    rows = []
    def add(key,node,attributes):
        rows.extend(CharacterChannel(key+"."+attr,node,attr) for attr in attributes)
    translation = tuple("translate"+axis for axis in "XYZ")
    rotation = tuple("rotate"+axis for axis in "XYZ")
    add("global",p.global_control.control_path,translation+rotation+(p.global_control.scale_attribute,))
    for control in p.torso.torso.controls.controls:
        add("torso."+control.control_name.removeprefix("AdvPy_"),control.control_path,
            (translation if control.control_path==p.torso.torso.pelvis_translation.source else ())+rotation)
    spine = p.torso.torso.spine
    add("spine.ik",spine.ik_control,translation+rotation+("waistRoll","spineIkFk"))
    add("spine.pole",spine.pole_control,translation)
    for label,module in (("arm",p.arm),("leg",p.leg)):
        for control in module.fk_controls.controls:
            add(label+".fk."+control.control_name.removeprefix("AdvPy_"),control.control_path,rotation)
        for limb in module.ik.limbs:
            target = limb.wrist_control_path if label=="arm" else limb.ankle_control_path
            add(label+".ik."+limb.side.value,target,translation+rotation)
            add(label+".pole."+limb.side.value,limb.pole_control_path,translation)
        for settings in (module.blend,module.stretch,module.volume):
            add(label+".settings",settings.settings_path,tuple(s.attribute for s in settings.sides))
    for settings in (p.leg.stretch_bias,p.leg.knee_pin):
        add("leg.settings",settings.settings_path,tuple(s.attribute for s in settings.sides))
    for side in p.leg.foot.sides:
        add("foot."+side.side.value,side.ankle_control_path,side.attributes)
        add("foot.toe."+side.side.value,side.toe_control_path,rotation)
    if p.hand:
        for control in p.hand.controls.controls:
            add("hand.fk."+control.control_name.removeprefix("AdvPy_"),control.control_path,rotation)
        for attr in p.hand.pose.attributes:
            add("hand."+attr.side.value,attr.root_path,(attr.name,))
    return tuple(rows)


class RegisterBodyCharacter:
    def __init__(self, host: CharacterRegistryHost):
        self._host = host

    def apply(self, rig) -> CharacterRegistration:
        channels = character_channels(rig)
        plan = self._host.describe_character_registration(rig,channels)
        self._host.preflight_character_registration(plan)
        with self._host.transaction("Register complete body character"):
            if self._host.describe_character_registration(rig,channels) != plan:
                raise RuntimeError("角色登记输入在执行前变化")
            self._host.preflight_character_registration(plan)
            self._host.create_character_registration(plan)
            result = self._host.read_character_registration(REGISTRY_NAME)
            if result != plan:
                raise RuntimeError("角色登记读回不一致")
        return result


class ResolveBodyCharacter:
    def __init__(self, host: CharacterRegistryHost):
        self._host = host

    def discover(self) -> tuple[str, ...]:
        return self._host.discover_character_registrations()

    def execute(self, name: str = REGISTRY_NAME) -> CharacterRegistration:
        return self._host.read_character_registration(name)
