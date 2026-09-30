"""Maya realization of the original Wheel / RollingBall FK mechanism."""
from __future__ import annotations

from adv_py.core.body_fit_wheel import BodyFitWheelSpec
from adv_py.core.fit_settings import FitSkeletonValidationError


class MayaBodyFitWheelMixin:
    def create_body_fit_wheels(
        self, wheels: tuple[BodyFitWheelSpec, ...]
    ) -> None:
        if not wheels:
            return
        self._require_transaction()
        c = self._cmds
        motion = "|Group|MotionSystem"
        if (c.ls(motion, long=True, type="transform") or []) != [motion]:
            raise FitSkeletonValidationError("Wheel 缺少 MotionSystem")
        system = motion + "|WheelSystem"
        if c.objExists("WheelSystem"):
            raise FitSkeletonValidationError("WheelSystem 名称已被占用")
        names: set[str] = {"WheelSystem"}
        for wheel in wheels:
            control = wheel.control
            stem = control.control_name.removeprefix("AdvPy_")
            for name in (
                "AdvPy_WheelFKX" + stem,
                "prevPosOffset" + stem, "prevPos" + stem,
                "prevPosAngler" + stem, "prevPosSteer" + stem,
                "nowPos" + stem, stem + "WheelExpression",
            ):
                if name in names or c.objExists(name):
                    raise FitSkeletonValidationError(
                        "Wheel 辅助节点名称冲突：" + name)
                names.add(name)
            if (c.ls(control.control_path, long=True,
                     type="transform") or []) != [control.control_path]:
                raise FitSkeletonValidationError(
                    "Wheel FK 控制器不存在：" + control.control_path)
            if not c.objExists(control.constraint_name):
                raise FitSkeletonValidationError(
                    "Wheel FK 朝向约束不存在：" + control.constraint_name)
            if control.source_override_path is not None:
                receiver = control.source_override_path
                internal = receiver.startswith(control.control_path + "|")
                expected_type = ("joint" if control.source_override_joint
                                 else "transform")
                if ((c.ls(receiver, long=True) or []) != [receiver]
                        or c.nodeType(receiver)
                        not in ((expected_type,) if internal else
                                ("joint", "transform"))):
                    raise FitSkeletonValidationError(
                        "Wheel FKX 接收层不存在：" + receiver)
            for attr in ("diameter", "autoRoll", "reset",
                         "prevPosX", "prevPosY", "prevPosZ"):
                if c.attributeQuery(attr, node=control.control_path,
                                    exists=True):
                    raise FitSkeletonValidationError(
                        "Wheel 控制属性已存在：" + control.control_path
                        + "." + attr)
        self._transaction_changed = True
        system = c.createNode("transform", name="WheelSystem",
                              parent=motion, skipSelect=True)
        system = (c.ls(system, long=True) or [system])[0]
        if system != motion + "|WheelSystem":
            raise RuntimeError("WheelSystem 路径漂移")
        c.setAttr(system + ".inheritsTransform", 0, lock=True)
        for wheel in wheels:
            self._create_body_fit_wheel(system, wheel)

    def _create_body_fit_wheel(self, system: str,
                               wheel: BodyFitWheelSpec) -> None:
        c = self._cmds
        spec = wheel.control
        control = spec.control_path
        stem = spec.control_name.removeprefix("AdvPy_")
        position = wheel.source_position
        diameter = position[1] * 2.0
        if diameter < 0.01:
            diameter = 1.0
        shapes = c.listRelatives(control, shapes=True, fullPath=True,
                                 type="nurbsCurve") or []
        if (len(shapes) == 1 and
                int(c.getAttr(shapes[0] + ".controlPoints", size=True)) == 11):
            # FK_icon in the original asIcons.ma has eight distinct ring
            # points and three periodic closing CVs.  The MEL builder edits
            # those eight CVs before sizing the whole control by radius.
            points = (
                (0, -0.783612, -0.783612),
                (0, 0, -1.108194),
                (0, 0.783612, -0.783612),
                (0, 1.108194, 0),
                (0, 0.783612, 0.783612),
                (0, 0, 1.108194),
                (0, -0.783612, 0.783612),
                (0, -1.108194, 0),
            )
            for index, point in enumerate(points):
                c.xform(control + f".cv[{index}]", objectSpace=True,
                        translation=point)
            factor = diameter / 2.0
            c.scale(factor, factor, factor, control + ".cv[*]",
                    relative=True, objectSpace=True, pivot=(0, 0, 0))
        c.addAttr(control, longName="diameter", attributeType="double",
                  defaultValue=diameter, keyable=True)
        c.addAttr(control, longName="autoRoll", attributeType="double",
                  defaultValue=1.0, softMinValue=-1.0,
                  softMaxValue=1.0, keyable=True)
        c.addAttr(control, longName="reset", attributeType="bool",
                  defaultValue=False)
        for axis, value in zip("XYZ", position):
            c.addAttr(control, longName="prevPos" + axis,
                      attributeType="double", defaultValue=value)
        source = spec.source_override_path
        if source is None:
            parent = spec.sub_control_path or control
            source = c.createNode(
                "transform", name="AdvPy_WheelFKX" + stem,
                parent=parent, skipSelect=True)
            # The original FKX sits below FK.  Reconnect the FK orient
            # constraint to that receiver so manual and automatic rotation
            # compose in the same local space.
            c.delete(spec.constraint_name)
            c.orientConstraint(source, spec.driven_joint,
                               maintainOffset=False,
                               name=spec.constraint_name)
        offset = c.createNode("transform", name="prevPosOffset" + stem,
                              parent=system, skipSelect=True)
        previous = c.createNode("transform", name="prevPos" + stem,
                                parent=offset, skipSelect=True)
        angler = c.createNode("transform", name="prevPosAngler" + stem,
                              parent=previous, skipSelect=True)
        now = c.createNode("transform", name="nowPos" + stem,
                           parent=system, skipSelect=True)
        c.pointConstraint(control, now, maintainOffset=False)
        c.xform(offset, worldSpace=True, translation=position)
        control_rotation = c.xform(control, query=True, worldSpace=True,
                                   rotation=True)
        c.setAttr(offset + ".rotateZ", 90.0)
        c.setAttr(offset + ".rotateX", control_rotation[1])
        steer = c.createNode("transform", name="prevPosSteer" + stem,
                             parent=control, skipSelect=True)
        c.xform(steer, worldSpace=True,
                matrix=c.xform(angler, query=True, worldSpace=True,
                               matrix=True))
        c.orientConstraint(steer, angler, maintainOffset=False)
        c.aimConstraint(
            control, previous, maintainOffset=False,
            aimVector=(0, 1, 0), upVector=(1, 0, 0),
            worldUpType="vector", worldUpVector=(0, 1, 0))
        # Expressions are evaluated after the namespace creation context has
        # ended.  Resolve every referenced node in the script itself.
        scene = self.scene_address
        fk = scene(spec.control_name)
        fkx = scene(source.rsplit("|", 1)[-1])
        now_name = scene("nowPos" + stem)
        prev_name = scene("prevPosOffset" + stem)
        angler_name = scene("prevPosAngler" + stem)
        scale_plug = scene(wheel.scale_plug)
        # Maya expressions are required here: the original rolls from the
        # previous evaluated position, so an acyclic DG graph cannot carry
        # its time-integrated state.
        script = (
            f"float $diameter={fk}.diameter;\n"
            f"float $autoRoll={fk}.autoRoll;\n"
            f"float $reset={fk}.reset;\n"
            f"float $sideAngle={angler_name}.rotateX;\n"
            f"float $scale={scale_plug};\n"
            f"float $prevPosX={fk}.prevPosX;\n"
            f"float $prevPosY={fk}.prevPosY;\n"
            f"float $prevPosZ={fk}.prevPosZ;\n"
            f"{prev_name}.translateX=$prevPosX;\n"
            f"{prev_name}.translateY=$prevPosY;\n"
            f"{prev_name}.translateZ=$prevPosZ;\n"
            f"float $nowPosX={now_name}.translateX;\n"
            f"float $nowPosY={now_name}.translateY;\n"
            f"float $nowPosZ={now_name}.translateZ;\n"
            "float $distance=`mag<<$nowPosX-$prevPosX,"
            "$nowPosY-$prevPosY,$nowPosZ-$prevPosZ>>`;\n"
            "float $piD=3.14*$diameter;\n"
        )
        if wheel.rolling_ball:
            script += (
                "float $x=($distance/$piD)*360*$autoRoll*-1*"
                "sin(deg_to_rad($sideAngle))/$scale;\n"
                "float $z=($distance/$piD)*360*$autoRoll*-1*"
                "sin(deg_to_rad($sideAngle-90))/$scale;\n"
                f"rotate -ws -r $x 0 $z {fkx};\n"
            )
        else:
            script += (
                f"float $curRotX={fkx}.rotateX;\n"
                "if ($reset) $curRotX=0;\n"
                f"{fkx}.rotateX=$curRotX+($distance/$piD)*360*"
                f"$autoRoll*{-wheel.side_factor}*"
                "sin(deg_to_rad($sideAngle))/$scale;\n"
            )
        script += (
            f"{fk}.prevPosX=$nowPosX;\n"
            f"{fk}.prevPosY=$nowPosY;\n"
            f"{fk}.prevPosZ=$nowPosZ;\n"
        )
        c.expression(name=stem + "WheelExpression", string=script,
                     object=source, alwaysEvaluate=True,
                     unitConversion="all")
