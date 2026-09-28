"""Rebuild a cleaned geo hierarchy from verified OBJ files while source is live."""
from __future__ import annotations

from pathlib import Path

from adv_py.core.model_clean import ModelCleanArchive, ModelCleanPlan


def _copy_attributes(host, source: str, target: str) -> None:
    c = host.cmds
    for (name, kind, value, locked, keyable, channel_box, short_name,
         enum_labels, minimum, maximum, default) in host._user_attributes(source):
        options = {"longName": name, "shortName": short_name}
        if kind == "string":
            options["dataType"] = "string"
        else:
            options["attributeType"] = kind
            if kind == "enum":
                if len(enum_labels) != 1:
                    raise ValueError("Model Clean 枚举属性定义无效：" + source + "." + name)
                options["enumName"] = enum_labels[0]
            if minimum:
                options["minValue"] = minimum[0]
            if maximum:
                options["maxValue"] = maximum[0]
            if default:
                options["defaultValue"] = default[0]
        c.addAttr(target, **options)
        plug = target + "." + name
        if kind == "string":
            c.setAttr(plug, value or "", type="string")
        elif value is not None:
            c.setAttr(plug, value)
        c.setAttr(plug, keyable=keyable)
        c.setAttr(plug, channelBox=channel_box)
        c.setAttr(plug, lock=locked)


def _copy_uvs(host, source_shape: str, target_shape: str) -> None:
    c, om = host.cmds, host.om
    source = om.MFnMesh(om.MSelectionList().add(source_shape).getDagPath(0))
    target = om.MFnMesh(om.MSelectionList().add(target_shape).getDagPath(0))
    expected = tuple(source.getUVSetNames())
    existing = tuple(target.getUVSetNames())
    # Maya keeps one default UV set on an OBJ import. Reuse it for the first
    # source set, then create any additional named sets explicitly.
    if expected and existing and existing[0] != expected[0]:
        c.polyUVSet(target_shape, rename=True, uvSet=existing[0],
                    newUVSet=expected[0])
    for uv_set in expected:
        if uv_set not in target.getUVSetNames():
            c.polyUVSet(target_shape, create=True, uvSet=uv_set)
        u_values, v_values = source.getUVs(uv_set)
        counts, indices = source.getAssignedUVs(uv_set)
        target.clearUVs(uv_set)
        target.setUVs(u_values, v_values, uv_set)
        target.assignUVs(counts, indices, uv_set)
    for uv_set in tuple(target.getUVSetNames()):
        if uv_set not in expected:
            c.polyUVSet(target_shape, delete=True, uvSet=uv_set)


def _restore_points(host, source_shape: str, target_shape: str) -> None:
    """Recover full Maya coordinate precision after the OBJ text round trip."""
    om = host.om
    source = om.MFnMesh(om.MSelectionList().add(source_shape).getDagPath(0))
    target = om.MFnMesh(om.MSelectionList().add(target_shape).getDagPath(0))
    if source.numVertices != target.numVertices:
        raise ValueError("Model Clean OBJ 顶点数量变化：" + source_shape)
    target.setPoints(source.getPoints(om.MSpace.kWorld), om.MSpace.kWorld)


def _restore_shape_display(host, shape: str, display) -> None:
    if display is None:
        return
    c = host.cmds
    smooth, smooth_lock, resolution, resolution_lock, mode, mode_lock = display
    for attribute, value, locked in (
        ("smoothLevel", smooth, smooth_lock),
        ("dispResolution", resolution, resolution_lock),
        ("displaySmoothMesh", mode, mode_lock),
    ):
        plug = shape + "." + attribute
        c.setAttr(plug, lock=False)
        c.setAttr(plug, value)
        c.setAttr(plug, lock=locked)


def _copy_materials(host, source_shape: str, target_shape: str) -> None:
    c, om = host.cmds, host.om
    source_path = om.MSelectionList().add(source_shape).getDagPath(0)
    source = om.MFnMesh(source_path)
    shaders, face_slots = source.getConnectedShaders(source_path.instanceNumber())
    engines = tuple(om.MFnDependencyNode(shader).name() for shader in shaders)
    for slot, engine in enumerate(engines):
        faces = [f"{target_shape}.f[{index}]"
                 for index, assigned in enumerate(face_slots)
                 if int(assigned) == slot]
        for offset in range(0, len(faces), 256):
            c.sets(faces[offset:offset + 256], edit=True, forceElement=engine)


def _import_obj(host, path: Path) -> str:
    c = host.cmds
    before = set(c.ls(assemblies=True, long=True) or [])
    c.file(str(path), i=True, type="OBJ", options="mo=0;lo=1;",
           ignoreVersion=True, mergeNamespacesOnClash=False,
           returnNewNodes=True, executeScriptNodes=False)
    roots = set(c.ls(assemblies=True, long=True) or []) - before
    if len(roots) != 1:
        raise RuntimeError("Model Clean OBJ 导入后没有唯一的顶层网格：" + str(path))
    root = roots.pop()
    shapes = c.listRelatives(root, shapes=True, fullPath=True,
                             noIntermediate=True, type="mesh") or []
    if len(shapes) != 1:
        raise RuntimeError("Model Clean OBJ 导入后网格 Shape 不唯一：" + str(path))
    return root


def build_model_clean_stage(host, plan: ModelCleanPlan,
                            archive: ModelCleanArchive) -> str:
    """Create and verify an exportable hierarchy before replacing the scene."""
    c = host.cmds
    archive_path = Path(archive.location)
    stage = c.group(empty=True, world=True, name="AdvPy_ModelCleanStage")
    targets = {plan.geo_root: stage}
    try:
        for item in plan.items:
            if item.source_path == plan.geo_root:
                _copy_attributes(host, item.source_path, stage)
                continue
            parent_source = item.source_path.rsplit("|", 1)[0]
            parent_target = targets[parent_source]
            leaf = item.target_path.rsplit("|", 1)[-1]
            if item.kind == "group":
                node = c.group(empty=True, parent=parent_target, name=leaf)
                _copy_attributes(host, item.source_path, node)
            else:
                node = _import_obj(host, archive_path / (item.obj_key + ".obj"))
                node = c.parent(node, parent_target, absolute=True)[0]
                node = c.rename(node, leaf)
                source_shape = (c.listRelatives(item.source_path, shapes=True,
                    noIntermediate=True, fullPath=True, type="mesh") or [])[0]
                target_shape = (c.listRelatives(node, shapes=True,
                    noIntermediate=True, fullPath=True, type="mesh") or [])[0]
                c.rename(target_shape, item.expected_shape_name)
                target_shape = (c.listRelatives(node, shapes=True,
                    noIntermediate=True, fullPath=True, type="mesh") or [])[0]
                _restore_points(host, source_shape, target_shape)
                _copy_uvs(host, source_shape, target_shape)
                _copy_materials(host, source_shape, target_shape)
                c.setAttr(target_shape + ".doubleSided", item.double_sided)
                _restore_shape_display(host, target_shape,
                                       item.shape_display)
                _copy_attributes(host, item.source_path, node)
                _copy_attributes(host, source_shape, target_shape)
                (vertices, faces, surface, uv_sets, uv_digest,
                 slots, material_digest) = host._mesh_data(target_shape)
                if ((vertices, faces, surface, uv_sets, uv_digest, slots,
                     material_digest) !=
                    (item.vertex_count, item.face_count, item.surface_sha256,
                     item.uv_sets, item.uv_content_sha256,
                     item.material_slots, item.material_assignment_sha256)):
                    raise ValueError("Model Clean OBJ 往返未保留网格数据："
                                     + item.source_path)
            targets[item.source_path] = c.ls(node, long=True)[0]
        return c.ls(stage, long=True)[0]
    except Exception:
        if c.objExists(stage):
            c.delete(stage)
        raise
