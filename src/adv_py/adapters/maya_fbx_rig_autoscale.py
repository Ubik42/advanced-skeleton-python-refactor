"""Project FBX FK control CVs onto bound Skin, following the 6.925 MEL path."""
from __future__ import annotations

from adv_py.core.fbx_rig_autoscale import fbx_fk_projection_factor


def _curve_shape(cmds, control: str) -> str:
    paths = cmds.ls(control, long=True, type="transform") or ()
    if len(paths) != 1:
        raise RuntimeError("FBX rig FK 控制器缺失：" + control)
    shapes = cmds.listRelatives(paths[0], shapes=True,
                                noIntermediate=True, fullPath=True,
                                type="nurbsCurve") or ()
    if len(shapes) != 1:
        raise RuntimeError("FBX rig FK 控制器曲线不唯一：" + control)
    return shapes[0]


def _cvs(cmds, shape: str) -> tuple[str, ...]:
    return tuple(cmds.ls(shape + ".cv[*]", flatten=True) or ())


def _world_position(cmds, path: str) -> tuple[float, float, float]:
    return tuple(float(value) for value in cmds.xform(
        path, query=True, worldSpace=True, translation=True))


def _best_bound_mesh(cmds, meshes: tuple[str, ...]) -> str:
    candidates = []
    for mesh in meshes:
        if not cmds.objExists(mesh):
            raise RuntimeError("FBX rig 来源蒙皮网格已丢失：" + mesh)
        shapes = cmds.listRelatives(mesh, shapes=True,
                                    noIntermediate=True, fullPath=True,
                                    type="mesh") or ()
        if len(shapes) != 1:
            raise RuntimeError("FBX rig 来源蒙皮对象不是单一多边形网格：" + mesh)
        candidates.append((int(cmds.polyEvaluate(shapes[0], vertex=True)), mesh))
    if not candidates:
        raise RuntimeError("FBX rig 自动缩放控制器需要来源蒙皮网格")
    return max(candidates, key=lambda item: item[0])[1]


def _project_curve(cmds, control: str, shape: str, mesh: str, *,
                   source_control_name: str | None = None) -> int:
    """Use the MEL orbital ray and nearest positive projected curve hit."""
    origin = _world_position(cmds, control)
    aim = cmds.createNode("transform", name="AdvPy_FBX_ProjectAim#",
                          skipSelect=True)
    target = cmds.createNode("transform", name="AdvPy_FBX_ProjectTarget#",
                             skipSelect=True)
    probe = cmds.createNode("transform", name="AdvPy_FBX_ProjectProbe#",
                            parent=aim, skipSelect=True)
    cmds.xform(aim, worldSpace=True, translation=origin)
    constraint = cmds.aimConstraint(
        target, aim, aimVector=(0, 0, 1), upVector=(1, 0, 0),
        worldUpVector=(0, 1, 0), worldUpType="objectrotation",
        worldUpObject=control)[0]
    changed = 0
    try:
        for index, cv in enumerate(_cvs(cmds, shape)):
            local = tuple(float(cmds.getAttr(cv + "." + axis + "Value"))
                          for axis in "xyz")
            factor = fbx_fk_projection_factor(source_control_name or control, index, local)
            if factor is None:
                continue
            cv_world = _world_position(cmds, cv)
            cmds.xform(target, worldSpace=True, translation=cv_world)
            cmds.xform(probe, worldSpace=True, translation=cv_world)
            direction = tuple(float(value) for value in cmds.xform(
                aim, query=True, worldSpace=True, matrix=True)[8:11])
            cmds.setAttr(constraint + ".offsetY", -15)
            orbital = _world_position(cmds, probe)
            cmds.setAttr(constraint + ".offsetY", 0)
            direct = _world_position(cmds, probe)
            ray = cmds.curve(degree=1, point=(orbital, direct),
                             name="AdvPy_FBX_ProjectRay#")
            projected = ()
            try:
                result = cmds.polyProjectCurve(
                    ray, mesh, constructionHistory=True, direction=direction,
                    pointsOnEdges=False, curveSamples=3,
                    automatic=False)
                projected = ((result,) if isinstance(result, str)
                             else tuple(result or ()))
                if not projected:
                    continue
                candidates = cmds.listRelatives(projected[0], children=True,
                                                type="nurbsCurve", fullPath=True) or ()
                distances = []
                for candidate in candidates:
                    if int(cmds.getAttr(candidate + ".spans")) == 0:
                        continue
                    hit = _world_position(cmds, candidate + ".cv[1]")
                    cmds.xform(probe, worldSpace=True, translation=hit)
                    depth = float(cmds.getAttr(probe + ".translateZ"))
                    if depth >= 0:
                        distances.append(depth)
                if not distances:
                    continue
                cmds.setAttr(probe + ".translate", 0, 0,
                             min(distances) * factor, type="double3")
                destination = _world_position(cmds, probe)
                cmds.xform(cv, worldSpace=True, translation=destination)
                if any(abs(actual - expected) > 1e-4 for actual, expected
                       in zip(_world_position(cmds, cv), destination)):
                    raise RuntimeError("FBX rig 控制曲线投射后坐标不一致：" + cv)
                changed += 1
            finally:
                if projected:
                    cmds.delete(*projected)
                cmds.delete(ray)
    finally:
        cmds.delete(target, aim)
    return changed


def project_fbx_fk_controls(
    cmds, control_names: tuple[str, ...], bound_meshes: tuple[str, ...],
    *, control_aliases: tuple[tuple[str, str], ...] = (),
) -> int:
    """Project center/right curves, then mirror right CVs into left curves."""
    aliases = dict(control_aliases)
    if (len(aliases) != len(control_aliases)
            or len(set(aliases.values())) != len(aliases)):
        raise ValueError("FBX rig 曲线投射映射不唯一")
    shapes = {name: _curve_shape(cmds, aliases.get(name, name))
              for name in control_names}
    eligible = tuple(name for name in control_names
                     if name.startswith("FK") and not name.startswith("FKIK")
                     and not name.endswith("_L"))
    if not eligible:
        return 0
    mesh = _best_bound_mesh(cmds, bound_meshes)
    selection = tuple(cmds.ls(selection=True, long=True) or ())
    try:
        changed = sum(_project_curve(cmds, aliases.get(name, name),
                      shapes[name], mesh, source_control_name=name)
                      for name in eligible)
        for right in eligible:
            if not right.endswith("_R"):
                continue
            left = right[:-2] + "_L"
            if left not in shapes:
                continue
            right_cvs = _cvs(cmds, shapes[right])
            left_cvs = _cvs(cmds, shapes[left])
            if len(right_cvs) != len(left_cvs):
                raise RuntimeError("FBX rig 左右控制曲线 CV 数量不同：" + right)
            for source, destination in zip(right_cvs, left_cvs):
                x, y, z = _world_position(cmds, source)
                expected = (-x, y, z)
                cmds.xform(destination, worldSpace=True, translation=expected)
                if any(abs(actual - wanted) > 1e-4 for actual, wanted
                       in zip(_world_position(cmds, destination), expected)):
                    raise RuntimeError("FBX rig 左侧控制曲线镜像失败：" + left)
        return changed
    finally:
        if selection:
            cmds.select(selection, replace=True)
        else:
            cmds.select(clear=True)
