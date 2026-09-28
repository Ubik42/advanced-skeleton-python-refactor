"""Maya construction boundary for 6.925 Bendy guide curves."""
from __future__ import annotations

from adv_py.core.fit_bendy import FitBendyChainSpec


_GROUPS = ("AdvPy_BendSystem", "AdvPy_BendCurve",
           "AdvPy_BendJoints", "AdvPy_BendMPX")
_OWNER = "adv_py.fit_bendy_guides.v1"


class MayaFitBendyMixin:
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
