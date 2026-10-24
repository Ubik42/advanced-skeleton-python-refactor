"""Copy AdvancedSkeleton driving-system links onto Fit for edit mode.

The original asDsToFitSkeleton stores a message list of driven SDK curves on
FitSkeleton and connects one enabled bool per driving control to those curves.
This keeps the driven-key graph discoverable while the generated rig is hidden.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_driving_catalog import MayaDrivingCatalogMixin


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
    def capture_body_game_rebuild(self, registration):
        from .maya_game_rebuild import capture
        return capture(self, registration)

    def restore_body_game_rebuild_root(self, state, registration, rig):
        from .maya_game_rebuild import restore_root
        return restore_root(self, state, registration, rig)

    def restore_body_game_rebuild_modes(self, state, registration, rig):
        from .maya_game_rebuild import restore_modes
        return restore_modes(self, state, registration, rig)

    def capture_body_control_orient_rebuild(self, registration):
        from .maya_control_orient_rebuild import capture
        return capture(self, registration)

    def restore_body_control_orient_rebuild(self, rows, registration, rig):
        from .maya_control_orient_rebuild import restore
        return restore(self, rows, registration, rig)

    def capture_body_driving_rebuild(self, registration):
        from .maya_driving_rebuild import capture
        return capture(self, registration)

    def restore_body_driving_rebuild(self, state, registration, rig, *, fit='FitSkeleton'):
        from .maya_driving_rebuild import restore
        return restore(self, state, registration, rig, fit=fit)

    def restore_body_driving_rebuild_membership(self, state):
        from .maya_driving_rebuild import restore_membership
        return restore_membership(self, state)

    def restore_body_driving_from_fit(self, registration, rig, *, fit='FitSkeleton',
                                      scene_before=None, populate_all=True):
        """Join native SDK restoration to the existing Body undo transaction."""
        self._require_transaction()
        from .maya_driving_systems import MayaDrivingSystemsHost
        from adv_py.core.fit_part import FitPartFinalPaths, rebase_plan_paths_after_parts
        # The same scene boundary, transaction flags and host state are used;
        # no second scene host or nested native undo chunk is initialized.
        driving = object.__new__(MayaDrivingSystemsHost)
        driving.__dict__ = self.__dict__
        plan = driving.capture_original_driving_fit_restore(fit)
        if not plan:
            return registration, rig
        if driving.original_corrective_body_registration() != registration:
            raise FitSkeletonValidationError('Fit SDK 恢复需要当前 Body 登记')
        driving.restore_original_driving_from_fit(plan, fit=fit)
        if populate_all:
            # Source AllSet collection and automatic unit naming run AFTER
            # the restored SDK curves/controllers are built (MEL 85824).
            if scene_before is None:
                raise FitSkeletonValidationError('恢复 SDK 后登记 AllSet 缺少构建前快照')
            from adv_py.application.body_all_set import PopulateBodyAllSet
            PopulateBodyAllSet(self).apply(scene_before, fit)
            from .maya_driving_registration import refresh_registered_sdks
            refresh_registered_sdks(driving)
        updated = self.read_character_registration()
        current = {node.uuid: node for node in updated.nodes}
        rewrites = []
        for node in registration.nodes:
            if node.uuid not in current:
                raise FitSkeletonValidationError('恢复 Fit SDK 替换了 Body 原节点')
            actual = current[node.uuid]
            if actual.node_type != node.node_type:
                raise FitSkeletonValidationError('恢复 Fit SDK 改变了 Body 原节点类型')
            if actual.path != node.path:
                rewrites.append((node.path, actual.path))
        final_paths = FitPartFinalPaths((), (), tuple(rewrites))
        return updated, rebase_plan_paths_after_parts(rig, final_paths)

    _driving_catalog_leaf = staticmethod(MayaDrivingCatalogMixin._driving_catalog_leaf)
    original_driving_attributes = MayaDrivingCatalogMixin.original_driving_attributes
    original_driving_curves = MayaDrivingCatalogMixin.original_driving_curves
    original_driving_systems = MayaDrivingCatalogMixin.original_driving_systems
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
            skipConversionNodes=True) or ())
        weighted = c.listConnections(
            driver_plug, source=False, destination=True,
            skipConversionNodes=True, type="blendWeighted") or ()
        if weighted:
            curves = list(c.listConnections(
                weighted[0] + ".output", source=False, destination=True,
                skipConversionNodes=True, type="animCurve") or ())
        paths = []
        for curve in curves:
            resolved = c.ls(curve, long=True) or ()
            if len(resolved) != 1:
                raise FitSkeletonValidationError(
                    "DrivingSystem SDK 曲线不存在或不唯一：" + curve)
            paths.append(resolved[0])
        # Preserve discovery order within translate/rotate groups. MEL does
        # not alphabetically sort, and puts every remaining node after them.
        ordered=[path for path in paths if "_translate" in path]
        ordered.extend(path for path in paths if "_rotate" in path)
        for path in paths:
            if path not in ordered:ordered.append(path)
        return tuple(ordered)

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
        candidates = []
        for control in self.original_driving_systems():
            resolved = c.ls(self.scene_address(control), long=True) or ()
            if len(resolved) != 1:
                raise FitSkeletonValidationError(
                    "DrivingSystem 控制器不存在或不唯一：" + control)
            if c.sets(resolved[0], isMember=control_set):
                candidates.append((control, resolved[0]))
        controls = []
        used_fit_attributes = set()
        curve_attributes: dict[tuple[str, str], str] = {}
        for control, driver in candidates:
            source_attrs = self.original_driving_attributes(control)
            attributes = []
            user = set(c.listAttr(driver, userDefined=True) or ())
            for name in source_attrs:
                if not _ATTRIBUTE.fullmatch(name):
                    raise FitSkeletonValidationError(
                        "DrivingSystem 属性名不支持迁移：" + name)
                curves = self._driving_sdk_curves(driver + "." + name)
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
        existing = tuple(c.listAttr(fit, userDefined=True, scalar=True) or ())
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
                    for value, flag, enabled in (
                        (attribute.minimum, "minValue", "hasMinValue"),
                        (attribute.maximum, "maxValue", "hasMaxValue"),
                        (attribute.soft_minimum, "softMinValue", "hasSoftMinValue"),
                        (attribute.soft_maximum, "softMaxValue", "hasSoftMaxValue"),
                    ):
                        if value is not None:
                            options[flag] = value
                            options[enabled] = True
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
