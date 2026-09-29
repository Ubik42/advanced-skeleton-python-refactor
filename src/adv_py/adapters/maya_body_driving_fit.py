"""Copy AdvancedSkeleton driving-system links onto Fit for edit mode.

The original asDsToFitSkeleton stores a message list of driven SDK curves on
FitSkeleton and connects one enabled bool per driving control to those curves.
This keeps the driven-key graph discoverable while the generated rig is hidden.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from adv_py.core.fit_settings import FitSkeletonValidationError


_ATTRIBUTE = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")


@dataclass(frozen=True, slots=True)
class DrivingFitAttribute:
    name: str
    curves: tuple[str, ...]
    minimum: float | None = None
    maximum: float | None = None
    soft_minimum: float | None = None
    soft_maximum: float | None = None


@dataclass(frozen=True, slots=True)
class DrivingFitControl:
    path: str
    fit_attribute: str
    attributes: tuple[DrivingFitAttribute, ...]


@dataclass(frozen=True, slots=True)
class DrivingFitPlan:
    fit: str
    controls: tuple[DrivingFitControl, ...]


class MayaBodyDrivingFitMixin:
    @property
    def _driving_cmds(self):
        return getattr(self._cmds, "raw", self._cmds)

    @staticmethod
    def _driving_leaf(path: str) -> str:
        return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def _driving_unique(self, name: str, *, node_type: str) -> str | None:
        c = self._driving_cmds
        paths = c.ls(self.scene_address(name), long=True,
                     type=node_type) or ()
        if len(paths) > 1:
            raise FitSkeletonValidationError(
                "Body DrivingSystem 名称不唯一：" + name)
        return paths[0] if paths else None

    def _driving_sdk_curves(self, driver_plug: str) -> tuple[str, ...]:
        """Follow the direct SDK edge or the v5.732 blendWeighted edge."""
        c = self._driving_cmds
        curves = list(c.listConnections(
            driver_plug, source=False, destination=True,
            skipConversionNodes=True, type="animCurve") or ())
        weighted = c.listConnections(
            driver_plug, source=False, destination=True,
            skipConversionNodes=True, type="blendWeighted") or ()
        for node in weighted:
            curves.extend(c.listConnections(
                node + ".output", source=False, destination=True,
                skipConversionNodes=True, type="animCurve") or ())
        paths = []
        for curve in curves:
            resolved = c.ls(curve, long=True) or ()
            if len(resolved) != 1 or not c.nodeType(resolved[0]).startswith(
                    "animCurve"):
                raise FitSkeletonValidationError(
                    "DrivingSystem SDK 曲线不存在或不唯一：" + curve)
            if resolved[0] not in paths:
                paths.append(resolved[0])
        return tuple(sorted(paths, key=lambda item: (
            0 if "_translate" in item else
            1 if "_rotate" in item else 2, item)))

    def _driving_source_attributes(self, driver: str, *,
                                   ordinary: bool,
                                   face: bool) -> tuple[str, ...]:
        c = self._driving_cmds
        user = tuple(c.listAttr(driver, userDefined=True) or ())
        if ordinary:
            candidates = user
        elif face:
            candidates = (() if c.getAttr(driver + ".translateX", lock=True)
                          else ("translateX", "translateY"))
            candidates += tuple(name for name in user if (
                not c.getAttr(driver + "." + name, lock=True)
                and (c.getAttr(driver + "." + name, keyable=True)
                     or c.getAttr(driver + "." + name,
                                  channelBox=True))))
            if self._driving_leaf(driver) == "ctrlPhonemes_M":
                candidates = tuple(name for name in candidates if name not in
                                   ("multipliers", "jaw", "lip"))
        else:
            # AutoDrivers are ordinary rig controls routed through weighted
            # SDK input nodes. Only channels with an actual SDK edge qualify.
            candidates = tuple(c.listAttr(driver, keyable=True) or ()) + user
        return tuple(dict.fromkeys(name for name in candidates
                                   if name != "optimizedDS"))

    def _driving_limits(self, plug: str, *, user_defined: bool
                        ) -> tuple[float | None, ...]:
        if not user_defined:
            return (None, None, None, None)
        c = self._driving_cmds
        values = []
        for has_flag, value_flag in (
            ("hasMinValue", "minValue"),
            ("hasMaxValue", "maxValue"),
            ("hasSoftMinValue", "softMinValue"),
            ("hasSoftMaxValue", "softMaxValue"),
        ):
            if c.addAttr(plug, query=True, **{has_flag: True}):
                value = c.addAttr(plug, query=True, **{value_flag: True})
                if isinstance(value, (list, tuple)):
                    value = value[0]
                values.append(float(value))
            else:
                values.append(None)
        return tuple(values)

    def plan_body_driving_fit_sync(self, fit: str) -> DrivingFitPlan | None:
        """Resolve all graph links before touching visibility or Fit attrs."""
        c = self._driving_cmds
        driving = self._driving_unique("DrivingSystem",
                                       node_type="transform")
        control_set = self._driving_unique("ControlSet",
                                            node_type="objectSet")
        if driving is None or control_set is None:
            return None
        face_set = self._driving_unique("FaceControlSet",
                                         node_type="objectSet")
        direct = set(c.listRelatives(driving, children=True,
                                     fullPath=True, type="transform") or ())
        members = c.sets(control_set, query=True) or ()
        candidates = []
        for member in members:
            resolved = c.ls(member, long=True, type="transform") or ()
            if len(resolved) != 1:
                continue
            path = resolved[0]
            if path not in candidates:
                candidates.append(path)
        controls = []
        used_fit_attributes = set()
        curve_attributes: dict[tuple[str, str], str] = {}
        for driver in candidates:
            ordinary = driver in direct
            face = bool(face_set and c.sets(driver, isMember=face_set))
            source_attrs = self._driving_source_attributes(
                driver, ordinary=ordinary, face=face)
            attributes = []
            user = set(c.listAttr(driver, userDefined=True) or ())
            for name in source_attrs:
                if not _ATTRIBUTE.fullmatch(name):
                    raise FitSkeletonValidationError(
                        "DrivingSystem 属性名不支持迁移：" + name)
                curves = self._driving_sdk_curves(driver + "." + name)
                if not ordinary and not curves:
                    continue
                for curve in curves:
                    key = (curve, name)
                    previous = curve_attributes.get(key)
                    if previous is not None and previous != driver:
                        raise FitSkeletonValidationError(
                            "多个 DrivingSystem 控制器共用同一 SDK 属性："
                            + curve + "." + name)
                    curve_attributes[key] = driver
                    if (c.referenceQuery(curve, isNodeReferenced=True)
                            or any(c.lockNode(curve, query=True,
                                              lock=True) or ())):
                        raise FitSkeletonValidationError(
                            "DrivingSystem SDK 曲线不可修改：" + curve)
                limits = self._driving_limits(driver + "." + name,
                                              user_defined=name in user)
                attributes.append(DrivingFitAttribute(
                    name, curves, *limits))
            if not ordinary and not attributes:
                continue
            leaf = self._driving_leaf(driver)
            fit_attribute = "drivingSystem_" + leaf
            if (not _ATTRIBUTE.fullmatch(fit_attribute)
                    or fit_attribute in used_fit_attributes):
                raise FitSkeletonValidationError(
                    "DrivingSystem 控制器名称冲突：" + leaf)
            used_fit_attributes.add(fit_attribute)
            controls.append(DrivingFitControl(
                driver, fit_attribute, tuple(attributes)))
        return DrivingFitPlan(fit, tuple(controls))

    def apply_body_driving_fit_sync(self, plan: DrivingFitPlan) -> None:
        """Run within the caller's undo transaction, like asDsToFitSkeleton."""
        self._require_transaction()
        c = self._driving_cmds
        fit = plan.fit
        if not c.objExists(fit):
            raise FitSkeletonValidationError("FitSkeleton 已丢失")
        existing = tuple(c.listAttr(fit, userDefined=True) or ())
        self._transaction_changed = True
        if c.attributeQuery("drivingSystem", node=fit, exists=True):
            c.deleteAttr(fit + ".drivingSystem")
        for name in existing:
            if name.startswith("drivingSystem_"):
                c.deleteAttr(fit + "." + name)
        c.addAttr(fit, longName="drivingSystem", attributeType="message",
                  multi=True, indexMatters=False, keyable=False)
        linked_curves = set()
        for control in plan.controls:
            c.addAttr(fit, longName=control.fit_attribute,
                      attributeType="bool", defaultValue=True,
                      multi=True, keyable=False)
            index = 0
            for attribute in control.attributes:
                for curve in attribute.curves:
                    if c.attributeQuery(attribute.name, node=curve,
                                        exists=True):
                        if attribute.name not in (
                                c.listAttr(curve, userDefined=True) or ()):
                            raise FitSkeletonValidationError(
                                "SDK 内建属性与驱动属性冲突：" + curve + "."
                                + attribute.name)
                        c.deleteAttr(curve + "." + attribute.name)
                    options = {}
                    for value, flag in (
                        (attribute.minimum, "minValue"),
                        (attribute.maximum, "maxValue"),
                        (attribute.soft_minimum, "softMinValue"),
                        (attribute.soft_maximum, "softMaxValue"),
                    ):
                        if value is not None:
                            options[flag] = value
                    c.addAttr(curve, longName=attribute.name,
                              attributeType="float", keyable=False,
                              **options)
                    c.connectAttr(
                        f"{fit}.{control.fit_attribute}[{index}]",
                        curve + "." + attribute.name, force=True)
                    if not c.isConnected(
                            f"{fit}.{control.fit_attribute}[{index}]",
                            curve + "." + attribute.name):
                        raise RuntimeError(
                            "Fit 驱动属性未连接 SDK：" + curve + "."
                            + attribute.name)
                    if curve not in linked_curves:
                        if not c.attributeQuery("drivingSystemOut",
                                                node=curve, exists=True):
                            c.addAttr(curve, longName="drivingSystemOut",
                                      attributeType="message", keyable=False)
                        c.connectAttr(curve + ".drivingSystemOut",
                                      fit + ".drivingSystem",
                                      nextAvailable=True)
                        linked_curves.add(curve)
                    index += 1
