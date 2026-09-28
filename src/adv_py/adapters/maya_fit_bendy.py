"""Maya construction boundary for 6.925 Bendy guide curves."""
from __future__ import annotations

from typing import TYPE_CHECKING

from adv_py.core.fit_bendy import FitBendyChainSpec

if TYPE_CHECKING:
    from adv_py.application.fit_bendy import FitBendyFollowSpec, FitBendyWorldSource


_GROUPS = ("AdvPy_BendSystem", "AdvPy_BendCurve",
           "AdvPy_BendJoints", "AdvPy_BendMPX")
_OWNER = "adv_py.fit_bendy_guides.v1"


class MayaFitBendyMixin:
    def preflight_fit_bendy_follow(self, spec: "FitBendyFollowSpec") -> None:
        c = self._cmds
        if any(c.objExists(name) for name in spec.chain.follow_node_names):
            raise ValueError("Bendy 跟随节点名称已占用：" + spec.chain.curve_name)
        for source in (spec.start, spec.end):
            for plug in (source.fk_matrix, source.ik_matrix, source.blend_plug):
                if plug is not None and not c.objExists(plug):
                    raise ValueError("Bendy 独立驱动插口不存在：" + plug)

    def preflight_fit_bendy_guides(
        self, spec: FitBendyChainSpec
    ) -> None:
        c = self._cmds
        if any(c.objExists(name) for name in spec.guide_node_names):
            raise ValueError("Bendy 节点名称已占用：" + spec.curve_name)
        for group in _GROUPS:
            if c.objExists(group):
                marker = group + ".advPyBendyGuideOwner"
                if (not c.objExists(marker)
                        or c.getAttr(marker) != _OWNER):
                    raise ValueError("Bendy 系统组不属于当前构建：" + group)
        for name in (spec.start_body, spec.end_body):
            matches = c.ls(name, long=True, type="joint") or []
            if matches != [name]:
                raise ValueError("Bendy 两端 Body 不唯一：" + name)

    def _ensure_fit_bendy_groups(self) -> None:
        c = self._cmds
        for index, group in enumerate(_GROUPS):
            if c.objExists(group):
                continue
            parent = _GROUPS[0] if index else None
            options = {"parent": parent} if parent else {}
            node = c.createNode("transform", name=group,
                                skipSelect=True, **options)
            c.addAttr(node, longName="advPyBendyGuideOwner",
                      dataType="string")
            c.setAttr(node + ".advPyBendyGuideOwner", _OWNER,
                      type="string", lock=True)
            self._transaction_changed = True

    def create_fit_bendy_guides(
        self, spec: FitBendyChainSpec
    ) -> None:
        self._require_transaction()
        c = self._cmds
        self._ensure_fit_bendy_groups()
        start, end = spec.start_position, spec.end_position
        curve = c.curve(name=spec.curve_name, degree=1,
                        point=(start, end))
        c.rebuildCurve(curve, ch=False, rpo=True, rt=0, end=1,
                       kr=0, kcp=False, kep=False, kt=False,
                       s=spec.control_count + 1, d=3, tol=0.01)
        curve = c.parent(curve, _GROUPS[1])[0]
        curve = (c.ls(curve, long=True) or [curve])[0]
        shapes = c.listRelatives(curve, shapes=True,
                                 fullPath=True) or []
        if len(shapes) != 1:
            raise RuntimeError("Bendy 曲线形状数量不正确")
        c.setAttr(shapes[0] + ".overrideEnabled", True)
        c.setAttr(shapes[0] + ".overrideDisplayType", 1)

        positions = (start, *spec.control_positions[1:], end)
        controls = []
        for index, (name, position) in enumerate(zip(
                spec.control_names, (spec.control_positions[1],
                                     *spec.control_positions))):
            control = c.circle(name=name, normal=(1, 0, 0),
                               radius=0.25, constructionHistory=False)[0]
            parent = (spec.control_names[0]
                      if index == 2 and spec.control_count == 1
                      else _GROUPS[0])
            control = c.parent(control, parent)[0]
            c.xform(control, worldSpace=True, translation=position)
            controls.append((c.ls(control, long=True) or [control])[0])
        end_proxy = c.createNode("transform", name=spec.end_proxy_name,
                                 parent=_GROUPS[0], skipSelect=True)
        c.xform(end_proxy, worldSpace=True, translation=end)
        drivers = (controls[1], *controls[2:], end_proxy)
        influences = []
        for name, position, driver in zip(
                spec.influence_names, positions, drivers):
            joint = c.createNode("joint", name=name, parent=_GROUPS[2],
                                 skipSelect=True)
            c.xform(joint, worldSpace=True, translation=position)
            c.setAttr(joint + ".drawStyle", 2)
            c.parentConstraint(driver, joint, maintainOffset=False,
                               name="AdvPy_BendGuide" + name)
            influences.append(joint)
        skin = c.skinCluster(*(influences + [curve]),
                             name=spec.skin_name,
                             maximumInfluences=2,
                             normalizeWeights=1,
                             toSelectedBones=True)[0]
        cv_count = int(c.getAttr(shapes[0] + ".controlPoints",
                                 size=True))
        if cv_count < len(influences) + 1:
            raise RuntimeError("Bendy 曲线控制点不足")
        for index in range(cv_count):
            driver_index = min(len(influences) - 1,
                               round(index * (len(influences) - 1)
                                     / (cv_count - 1)))
            c.skinPercent(skin, curve + f".cv[{index}]",
                          transformValue=[(influences[driver_index], 1.0)])
        for index, (path_name, transform_name) in enumerate(zip(
                spec.motion_path_names,
                spec.motion_transform_names)):
            path = c.createNode("motionPath", name=path_name,
                                skipSelect=True)
            transform = c.createNode("transform", name=transform_name,
                                     parent=_GROUPS[3], skipSelect=True)
            c.setAttr(path + ".fractionMode", True)
            c.setAttr(path + ".uValue",
                      index / (len(spec.part_names) + 1))
            c.connectAttr(shapes[0] + ".worldSpace[0]",
                          path + ".geometryPath")
            c.connectAttr(path + ".allCoordinates",
                          transform + ".translate")
        self._transaction_changed = True

    def create_fit_bendy_follow(self, spec: "FitBendyFollowSpec") -> None:
        """Keep animator channels free while the guide follows independent Rig."""
        self._require_transaction()
        c = self._cmds
        chain = spec.chain
        names = chain.follow_node_names
        start_proxy, end_proxy = names[:2]

        def source_proxy(name: str, world_name: str, blend_name: str,
                         source: "FitBendyWorldSource") -> None:
            proxy = c.createNode("transform", name=name,
                                 parent=_GROUPS[0], skipSelect=True)
            matrix = source.fk_matrix
            if source.ik_matrix is not None:
                blend = c.createNode("blendMatrix", name=blend_name,
                                     skipSelect=True)
                c.connectAttr(source.fk_matrix, blend + ".inputMatrix")
                c.connectAttr(source.ik_matrix,
                              blend + ".target[0].targetMatrix")
                c.connectAttr(source.blend_plug,
                              blend + ".target[0].weight")
                matrix = blend + ".outputMatrix"
            world = c.createNode("multMatrix", name=world_name,
                                 skipSelect=True)
            c.connectAttr(matrix, world + ".matrixIn[0]")
            c.connectAttr(proxy + ".parentInverseMatrix[0]",
                          world + ".matrixIn[1]")
            c.connectAttr(world + ".matrixSum",
                          proxy + ".offsetParentMatrix")

        source_proxy(start_proxy, names[2], names[4], spec.start)
        source_proxy(end_proxy, names[3], names[5], spec.end)
        for index, control in enumerate(chain.control_names):
            position = (chain.control_positions[1] if index == 0
                        else chain.control_positions[index - 1])
            offset = c.createNode("transform", name=control + "Offset",
                                  parent=_GROUPS[0], skipSelect=True)
            c.xform(offset, worldSpace=True, translation=position)
            c.parent(control, offset, absolute=True)
            targets = ((start_proxy, end_proxy) if index == 0
                       or index > 1 else (start_proxy,))
            constraint = c.parentConstraint(
                *targets, offset, maintainOffset=True,
                name=f"AdvPy_{control}Follow")[0]
            if len(targets) == 2:
                fraction = (0.5 if index == 0
                            else (index - 1) / (chain.control_count + 1))
                weights = c.parentConstraint(
                    constraint, query=True, weightAliasList=True)
                if len(weights) != 2:
                    raise RuntimeError("Bendy 跟随约束权重数量不正确")
                c.setAttr(constraint + "." + weights[0], 1.0 - fraction)
                c.setAttr(constraint + "." + weights[1], fraction)
        c.parentConstraint(end_proxy, chain.end_proxy_name,
                           maintainOffset=True,
                           name=f"AdvPy_{chain.end_proxy_name}Follow")
        self._transaction_changed = True

    def capture_fit_bendy_follow(self, spec: "FitBendyFollowSpec") -> bool:
        c = self._cmds
        names = spec.chain.follow_node_names
        for proxy, world, source, blend in (
                (names[0], names[2], spec.start, names[4]),
                (names[1], names[3], spec.end, names[5])):
            if (not c.objExists(proxy) or c.nodeType(proxy) != "transform"
                    or not c.objExists(world)
                    or c.nodeType(world) != "multMatrix"
                    or c.connectionInfo(proxy + ".offsetParentMatrix",
                                        sourceFromDestination=True)
                    != world + ".matrixSum"):
                return False
            expected = source.fk_matrix
            if source.ik_matrix is not None:
                if (not c.objExists(blend) or c.nodeType(blend) != "blendMatrix"
                        or c.connectionInfo(blend + ".inputMatrix",
                                            sourceFromDestination=True)
                        != source.fk_matrix
                        or c.connectionInfo(blend + ".target[0].targetMatrix",
                                            sourceFromDestination=True)
                        != source.ik_matrix
                        or c.connectionInfo(blend + ".target[0].weight",
                                            sourceFromDestination=True)
                        != source.blend_plug):
                    return False
                expected = blend + ".outputMatrix"
            if c.connectionInfo(world + ".matrixIn[0]",
                                sourceFromDestination=True) != expected:
                return False
        for control in spec.chain.control_names:
            offset = control + "Offset"
            follow = f"AdvPy_{control}Follow"
            if (not c.objExists(offset) or not c.objExists(follow)
                    or c.nodeType(follow) != "parentConstraint"
                    or (c.listRelatives(control, parent=True) or [])
                    != [offset]):
                return False
        return (c.objExists(names[-1])
                and c.nodeType(names[-1]) == "parentConstraint")

    def capture_fit_bendy_guides(
        self, spec: FitBendyChainSpec
    ) -> bool:
        c = self._cmds
        curve = c.ls(spec.curve_name, long=True,
                     type="transform") or []
        if len(curve) != 1:
            return False
        shapes = c.listRelatives(curve[0], shapes=True,
                                 fullPath=True) or []
        if (len(shapes) != 1 or c.nodeType(shapes[0]) != "nurbsCurve"
                or not c.objExists(spec.skin_name)
                or c.nodeType(spec.skin_name) != "skinCluster"):
            return False
        influences = c.skinCluster(spec.skin_name, query=True,
                                   influence=True) or []
        if {name.rsplit("|", 1)[-1] for name in influences} != set(
                spec.influence_names):
            return False
        for name in spec.influence_names:
            constraint = "AdvPy_BendGuide" + name
            if (not c.objExists(name) or c.nodeType(name) != "joint"
                    or not c.objExists(constraint)
                    or c.nodeType(constraint) != "parentConstraint"):
                return False
        for name in (*spec.control_names, spec.end_proxy_name):
            if not c.objExists(name) or c.nodeType(name) != "transform":
                return False
        for index, (path, transform) in enumerate(zip(
                spec.motion_path_names, spec.motion_transform_names)):
            if (not c.objExists(path) or c.nodeType(path) != "motionPath"
                    or not c.objExists(transform)
                    or c.connectionInfo(path + ".geometryPath",
                        sourceFromDestination=True)
                    != shapes[0] + ".worldSpace[0]"
                    or c.connectionInfo(transform + ".translate",
                        sourceFromDestination=True)
                    != path + ".allCoordinates"
                    or not c.getAttr(path + ".fractionMode")
                    or abs(float(c.getAttr(path + ".uValue"))
                           - index / (len(spec.part_names) + 1)) > 1e-8):
                return False
        return True
