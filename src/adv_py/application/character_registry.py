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
    if not p.torso or not (p.torso.torso.spine or p.torso.torso.spline) or not p.control_spaces:
        raise ValueError("角色登记要求完整 Torso、Spine IK 和控制空间")
    rows = []
    locked = {spec.control: frozenset(spec.attributes)
              for spec in getattr(p, "fk_channel_locks", ())}
    def add(key,node,attributes):
        rows.extend(CharacterChannel(key+"."+attr,node,attr)
                    for attr in attributes
                    if attr not in locked.get(node, ()))
    translation = tuple("translate"+axis for axis in "XYZ")
    rotation = tuple("rotate"+axis for axis in "XYZ")
    scale = tuple("scale"+axis for axis in "XYZ")
    transform = translation + rotation + scale
    def add_layers(key, control):
        if control.sub_control_path:
            add(key + ".sub", control.sub_control_path, transform)
        if control.extra_path:
            add(key + ".extra", control.extra_path, transform)
    add("global",p.global_control.control_path,translation+rotation+(p.global_control.scale_attribute,))
    for index, path in enumerate(p.global_control.extra_control_paths, 1):
        add(f"global.extra.{index}", path,
            translation + rotation + tuple("scale" + axis for axis in "XYZ"))
    if p.torso.torso.root_x is not None:
        add("root.x", p.torso.torso.root_x.control_path,
            translation + rotation + tuple("scale" + axis for axis in "XYZ"))
    for cog in p.torso.torso.cogs:
        add("root.cog." + cog.control_name, cog.control_path,
            translation + rotation + tuple("scale" + axis for axis in "XYZ"))
    for control in p.torso.torso.controls.controls:
        key = "torso." + control.control_name.removeprefix("AdvPy_")
        add(key, control.control_path,
            (translation if control.control_path == p.torso.torso.pelvis_translation.source else ())
            + rotation + scale)
        add_layers(key, control)
    lock = p.torso.torso.leg_lock
    if lock.static_source is not None and lock.enabled:
        add("root.leg_lock", lock.weight_control, ("legLock",))
    spine = p.torso.torso.spine
    if spine:
        add("spine.ik",spine.ik_control,
            translation+rotation+("waistRoll","spineIkFk","stretchy","antiPop",
                                  "volume","Lenght1","Lenght2",
                                  "Fatness1","Fatness2"))
        if spine.ik_extra_path:
            add("spine.ik.extra", spine.ik_extra_path, transform)
        if spine.ik_sub_path:
            add("spine.ik.sub", spine.ik_sub_path, transform)
        add("spine.pole",spine.pole_control,translation+("lock",))
    else:
        spline = p.torso.torso.spline
        for index, target in enumerate(spline.targets):
            add(f"spine.spline.{index}", target,
                (() if index == 0 else translation)
                + (rotation if index in (0, len(spline.targets)-1)
                   or spline.twist_ramp_graph else ())
                + tuple("scale" + axis for axis in "XYZ"))
            if spline.extra_targets:
                add(f"spine.spline.{index}.extra",
                    spline.extra_targets[index], transform)
            if spline.sub_targets:
                add(f"spine.spline.{index}.sub",
                    spline.sub_targets[index], transform)
        add("spine.spline", spline.settings,
            ("spineIkFk", "stretchy", "volume") +
            (("stretchEven",) if spline.even_stretch_graph else ()))
        if spline.mid_follow_graph:
            for index, target in enumerate(spline.targets[1:-1], 1):
                add(f"spine.spline.{index}", target, ("followEnd",))
    if p.torso.torso.head_aim:
        aim=p.torso.torso.head_aim
        add('head.aim.target',aim.target,translation+rotation+('follow',))
        add('head.aim',aim.head_control,('headAim',))
    for aim in getattr(p, "fit_aim", ()):
        add("fit.aim." + aim.stem + ".center", aim.center_control,
            translation + rotation + ("follow",))
        for side in aim.sides:
            if side.suffix != "M":
                add("fit.aim." + aim.stem + "." + side.suffix,
                    side.target_control, translation + rotation)
    for label,module in (("arm",p.arm),("leg",p.leg)):
        for control in module.fk_controls.controls:
            key = label + ".fk." + control.control_name.removeprefix("AdvPy_")
            add(key, control.control_path, rotation + scale)
            add_layers(key, control)
        for limb in module.ik.limbs:
            target = limb.wrist_control_path if label=="arm" else limb.ankle_control_path
            key = label + ".ik." + limb.side.value
            add(key, target, transform)
            sub = limb.wrist_sub_path if label == "arm" else limb.ankle_sub_path
            extra = limb.wrist_extra_path if label == "arm" else limb.ankle_extra_path
            if sub:
                add(key + ".sub", sub, transform)
            if extra:
                add(key + ".extra", extra, transform)
            add(label+".pole."+limb.side.value,limb.pole_control_path,translation)
            if limb.pole_extra_path:
                add(label + ".pole.extra." + limb.side.value,
                    limb.pole_extra_path, transform)
        for settings in (module.blend,module.stretch,module.volume):
            add(label+".settings",settings.settings_path,tuple(s.attribute for s in settings.sides))
    for settings in (p.leg.stretch_bias,p.leg.knee_pin):
        add("leg.settings",settings.settings_path,tuple(s.attribute for s in settings.sides))
    for side in p.leg.foot.sides:
        add("foot."+side.side.value,side.ankle_control_path,side.attributes)
        for pivot in side.pivots:
            if pivot.roll_control_path:
                role = (pivot.role.value if hasattr(pivot.role, "value")
                        else pivot.role)
                add("foot.roll."+role+"."+side.side.value,
                    pivot.roll_control_path,rotation)
        for manual in side.manual_pivots:
            add("foot.pivot."+manual.target_name+"."+side.side.value,
                manual.control_path,translation+rotation)
        if side.hybrid is not None:
            for segment in side.hybrid.segments:
                add("foot.ikhybrid."+segment.marker_name+"."
                    +side.side.value,segment.control_path,
                    translation+rotation)
        else:
            add("foot.toe."+side.side.value,
                side.toe_control_path, rotation + scale)
            if side.toe_sub_path:
                add("foot.toe.sub." + side.side.value,
                    side.toe_sub_path, transform)
            if side.toe_extra_curve:
                add("foot.toe.extra." + side.side.value,
                    side.toe_extra_path, transform)
    if p.hand:
        for control in p.hand.controls.controls:
            key = "hand.fk." + control.control_name.removeprefix("AdvPy_")
            add(key, control.control_path, rotation + scale)
            add_layers(key, control)
        for attr in p.hand.pose.attributes:
            add("hand."+attr.side.value,attr.root_path,(attr.name,))
    for spec in p.fk_globals:
        add("fk.global." + spec.control.rsplit("|", 1)[-1],
            spec.control,
            ("Global", "GlobalTranslate") if spec.translate
            else ("Global",))
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
