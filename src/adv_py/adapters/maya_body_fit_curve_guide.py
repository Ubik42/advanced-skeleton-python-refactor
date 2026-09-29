"""Build the 6.925 CurveGuide sampling, target and CV-control graph."""
from __future__ import annotations

from adv_py.core.body_fit_curve_guide import (
    BodyFitCurveGuideBuilt, BodyFitCurveGuideSpec,
)
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_adv_icons import create_adv_icon


class MayaBodyFitCurveGuideMixin:
    def create_body_fit_curve_guides(
        self, guides: tuple[BodyFitCurveGuideSpec, ...],
        *, main_control: str, fit_container: str,
    ) -> tuple[BodyFitCurveGuideBuilt, ...]:
        if not guides:
            return ()
        self._require_transaction()
        c = self._cmds
        motion = "|Group|MotionSystem"
        ik_parent = motion + "|IKSystem"
        global_follow = motion + "|GlobalSystem|GlobalFollowMain"
        for path in (motion, ik_parent, global_follow, main_control,
                     fit_container):
            if (c.ls(path, long=True, type="transform") or []) != [path]:
                raise FitSkeletonValidationError(
                    "Curve Guide 缺少角色层级：" + path)
        if c.objExists("CurveGuideSystem"):
            raise FitSkeletonValidationError("CurveGuideSystem 名称已被占用")
        by_curve: dict[str, list[BodyFitCurveGuideSpec]] = {}
        names: set[str] = {"CurveGuideSystem"}
        for spec in guides:
            by_curve.setdefault(spec.curve_name, []).append(spec)
            curve = c.ls(spec.source_curve, long=True,
                         type="transform") or []
            if len(curve) != 1 or len(c.listRelatives(
                    curve[0], shapes=True, fullPath=True,
                    type="nurbsCurve") or []) != 1:
                raise FitSkeletonValidationError(
                    "Curve Guide 来源曲线无效：" + spec.source_curve)
            if (c.ls(spec.control.aim_path, long=True,
                     type="transform") or []) != [spec.control.aim_path]:
                raise FitSkeletonValidationError(
                    "Curve Guide FK Aim 层缺失："
                    + str(spec.control.aim_path))
            if (c.ls(spec.parent_body, long=True,
                     type="joint") or []) != [spec.parent_body]:
                raise FitSkeletonValidationError(
                    "Curve Guide 父关节缺失：" + spec.parent_body)
            stem = spec.control.control_name.removeprefix("AdvPy_")
            for name in ("AdvPy_CurveOn_" + stem,
                         "AdvPy_CurveInfo_" + stem,
                         "AdvPy_CurveStatic_" + stem,
                         "AdvPy_CurveIKOffset_" + stem,
                         "AdvPy_CurveIK_" + stem):
                if name in names or c.objExists(name):
                    raise FitSkeletonValidationError(
                        "Curve Guide 节点名称冲突：" + name)
                names.add(name)
        for curve_name in by_curve:
            for name in (curve_name, curve_name + "BlendUnitConversion",
                         curve_name + "BlendReverse"):
                if name in names or c.objExists(name):
                    raise FitSkeletonValidationError(
                        "Curve Guide 曲线名称冲突：" + name)
                names.add(name)
        self._transaction_changed = True
        system = c.createNode("transform", name="CurveGuideSystem",
                              parent=motion, skipSelect=True)
        system = (c.ls(system, long=True) or [system])[0]
        if system != motion + "|CurveGuideSystem":
            raise RuntimeError("CurveGuideSystem 路径漂移")
        c.setAttr(system + ".inheritsTransform", 0, lock=True)
        if not c.attributeQuery("guideTargetsVis", node=main_control,
                                exists=True):
            c.addAttr(main_control, longName="guideTargetsVis",
                      attributeType="bool", defaultValue=False,
                      keyable=True)
            c.setAttr(main_control + ".guideTargetsVis",
                      keyable=False, channelBox=True)
        built: list[BodyFitCurveGuideBuilt] = []
        for curve_name, group in by_curve.items():
            source = c.ls(group[0].source_curve, long=True,
                          type="transform")[0]
            if not (c.listRelatives(source, parent=True,
                                    fullPath=True) or []):
                source = c.parent(source, fit_container)[0]
            if c.attributeQuery("curveGuide", node=source, exists=True):
                c.deleteAttr(source + ".curveGuide")
            duplicate = c.duplicate(source, name=curve_name,
                                    returnRootsOnly=True)[0]
            curve = c.parent(duplicate, system)[0]
            curve = (c.ls(curve, long=True) or [curve])[0]
            c.makeIdentity(curve, apply=True, translate=True,
                           rotate=True, scale=True)
            shape = (c.listRelatives(curve, shapes=True, fullPath=True,
                                     type="nurbsCurve") or [None])[0]
            if shape is None:
                raise RuntimeError("Curve Guide 复制曲线缺少形状")
            if group[0].side == "L":
                c.scale(-1, 1, 1, curve + ".cv[*]", relative=True,
                        objectSpace=True, pivot=(0, 0, 0))
            c.setAttr(shape + ".overrideEnabled", 1)
            c.setAttr(shape + ".overrideColor", 17)
            if not c.attributeQuery("blend", node=curve, exists=True):
                c.addAttr(curve, longName="blend", attributeType="double",
                          minValue=0, maxValue=10, defaultValue=10,
                          keyable=True)
            blend = c.createNode(
                "unitConversion", name=curve_name + "BlendUnitConversion",
                skipSelect=True)
            reverse = c.createNode(
                "reverse", name=curve_name + "BlendReverse",
                skipSelect=True)
            c.setAttr(blend + ".conversionFactor", 0.1)
            c.connectAttr(curve + ".blend", blend + ".input")
            c.connectAttr(blend + ".output", reverse + ".inputX")
            cv_controls, cv_helpers = self._create_curve_guide_cv_controls(
                curve, shape, system, global_follow, main_control, group)
            for spec in group:
                stem = spec.control.control_name.removeprefix("AdvPy_")
                on_curve = c.createNode(
                    "transform", name="AdvPy_CurveOn_" + stem,
                    parent=system, skipSelect=True)
                near = c.createNode("nearestPointOnCurve", skipSelect=True)
                try:
                    c.connectAttr(shape + ".worldSpace[0]",
                                  near + ".inputCurve")
                    c.setAttr(near + ".inPosition",
                              *spec.control.world_position, type="double3")
                    parameter = float(c.getAttr(near + ".parameter"))
                finally:
                    c.delete(near)
                info = c.createNode(
                    "pointOnCurveInfo", name="AdvPy_CurveInfo_" + stem,
                    skipSelect=True)
                c.connectAttr(shape + ".worldSpace[0]",
                              info + ".inputCurve")
                c.setAttr(info + ".parameter", parameter)
                c.connectAttr(info + ".position",
                              on_curve + ".translate")
                c.tangentConstraint(
                    curve, on_curve, maintainOffset=False,
                    aimVector=(spec.tangent_sign, 0, 0),
                    upVector=(0, 0, 1),
                    worldUpType="objectrotation",
                    worldUpVector=(0, 0, 1),
                    worldUpObject=spec.parent_body)
                static = c.createNode(
                    "transform", name="AdvPy_CurveStatic_" + stem,
                    parent=system, skipSelect=True)
                c.xform(static, worldSpace=True,
                        matrix=c.xform(on_curve, query=True,
                                       worldSpace=True, matrix=True))
                offset = c.createNode(
                    "transform", name="AdvPy_CurveIKOffset_" + stem,
                    parent=ik_parent, skipSelect=True)
                c.xform(offset, worldSpace=True,
                        matrix=c.xform(static, query=True,
                                       worldSpace=True, matrix=True))
                ik = create_adv_icon(
                    c, name="AdvPy_CurveIK_" + stem,
                    parent=offset, template="IK_icon",
                    radius=max(spec.control.radius * 0.3, 1e-4),
                    fallback_normal=(1.0, 0.0, 0.0))
                c.connectAttr(main_control + ".guideTargetsVis",
                              offset + ".visibility")
                constraint = c.parentConstraint(
                    on_curve, static, offset, maintainOffset=False)[0]
                aliases = c.parentConstraint(
                    constraint, query=True, weightAliasList=True) or []
                if len(aliases) != 2:
                    raise RuntimeError("Curve Guide 混合约束目标数量错误")
                c.connectAttr(blend + ".output",
                              constraint + "." + aliases[0])
                c.connectAttr(reverse + ".outputX",
                              constraint + "." + aliases[1])
                c.aimConstraint(
                    ik, spec.control.aim_path, maintainOffset=True,
                    aimVector=(spec.tangent_sign, 0, 0),
                    upVector=(0, 0, 1),
                    worldUpType="objectrotation",
                    worldUpVector=(0, 0, 1),
                    worldUpObject=ik)
                built.append(BodyFitCurveGuideBuilt(
                    curve_path=curve,
                    ik_control_path=ik,
                    cv_control_paths=cv_controls,
                    helper_paths=(system, on_curve, static, offset,
                                  *cv_helpers)))
        return tuple(built)

    def _create_curve_guide_cv_controls(
        self, curve: str, shape: str, system: str,
        global_follow: str, main_control: str,
        guides: list[BodyFitCurveGuideSpec],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        c = self._cmds
        count = (int(c.getAttr(shape + ".spans"))
                 + int(c.getAttr(shape + ".degree")))
        controls: list[str] = []
        helpers: list[str] = []
        for index in range(count):
            point = tuple(float(value) for value in c.pointPosition(
                curve + f".cv[{index}]", world=True))
            side = ("L" if point[0] > 0.01 else
                    "R" if point[0] < -0.01 else "M")
            stem = curve.rsplit("|", 1)[-1] + "Ctrl" + str(index) + "_" + side
            name = "AdvPy_" + stem
            if c.objExists(name):
                raise FitSkeletonValidationError(
                    "Curve Guide CV 控制器名称冲突：" + name)
            offset = c.createNode("transform", name=name + "Offset",
                                  parent=system, skipSelect=True)
            control = c.curve(
                name=name, degree=1,
                point=((0, 1, 0), (0, -1, 0), (0, 0, 0),
                       (1, 0, 0), (-1, 0, 0)),
                knot=(0, 1, 2, 3, 4))
            control = c.parent(control, offset)[0]
            control = (c.ls(control, long=True) or [control])[0]
            c.xform(offset, worldSpace=True, translation=point)
            shapes = c.listRelatives(control, shapes=True, fullPath=True,
                                     type="nurbsCurve") or []
            c.setAttr(shapes[0] + ".overrideEnabled", 1)
            c.setAttr(shapes[0] + ".overrideColor", 17)
            locator = c.createNode("transform", name=name + "Loc",
                                   parent=control, skipSelect=True)
            locator_shape = c.createNode("locator", name=name + "LocShape",
                                         parent=locator, skipSelect=True)
            c.setAttr(locator_shape + ".visibility", 0, lock=True)
            c.connectAttr(locator_shape + ".worldPosition[0]",
                          shape + f".controlPoints[{index}]", force=True)
            c.addAttr(control, longName="follow", attributeType="double",
                      minValue=0, maxValue=10, defaultValue=10,
                      keyable=True)
            follow_range = c.createNode(
                "setRange", name=name + "FollowSetRange", skipSelect=True)
            for axis, lo, hi in (("X", 0, 1), ("Y", 1, 0)):
                c.setAttr(follow_range + ".min" + axis, lo)
                c.setAttr(follow_range + ".max" + axis, hi)
                c.setAttr(follow_range + ".oldMin" + axis, 0)
                c.setAttr(follow_range + ".oldMax" + axis, 10)
                c.connectAttr(control + ".follow",
                              follow_range + ".value" + axis)
            follow_on = c.createNode("transform", name=name + "FollowOn",
                                     parent=system, skipSelect=True)
            follow_off = c.createNode("transform", name=name + "FollowOff",
                                      parent=global_follow, skipSelect=True)
            for target in (follow_on, follow_off):
                c.xform(target, worldSpace=True, translation=point)
            nearest = min(guides, key=lambda guide: sum(
                (left - right) ** 2 for left, right in zip(
                    point, guide.control.world_position)))
            c.parentConstraint(nearest.parent_body, follow_on,
                               maintainOffset=True)
            blend = c.parentConstraint(follow_on, follow_off, offset,
                                       maintainOffset=True)[0]
            aliases = c.parentConstraint(
                blend, query=True, weightAliasList=True) or []
            if len(aliases) != 2:
                raise RuntimeError("Curve Guide CV Follow 目标数量错误")
            c.connectAttr(follow_range + ".outValueX",
                          blend + "." + aliases[0])
            c.connectAttr(follow_range + ".outValueY",
                          blend + "." + aliases[1])
            c.scaleConstraint(main_control, offset,
                              maintainOffset=True)
            controls.append(control)
            helpers.extend((offset, locator, follow_on, follow_off))
        return tuple(controls), tuple(helpers)
