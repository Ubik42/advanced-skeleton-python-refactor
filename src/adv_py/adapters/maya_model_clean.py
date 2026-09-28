"""Maya capture for the 6.925 Model Cleaner scene contract."""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import shutil
from tempfile import mkdtemp

from adv_py.core.model_clean import (
    ModelCleanArchive, ModelCleanArchiveItem, ModelCleanNode,
    ModelCleanPlan, ModelCleanScene, model_clean_content_sha256,
    plan_model_clean,
)


def _json_value(value):
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise ValueError("Model Clean 遇到无法归档的 Maya 属性值")


class MayaModelCleanHost:
    def __init__(self) -> None:
        from maya import cmds
        from maya.api import OpenMaya

        self.cmds = cmds
        self.om = OpenMaya
        self._archive_dir: Path | None = None

    def _user_attributes(self, path: str):
        c = self.cmds
        rows = []
        for name in sorted(c.listAttr(path, userDefined=True) or []):
            plug = path + "." + name
            kind = c.getAttr(plug, type=True)
            if kind == "message":
                continue
            try:
                value = _json_value(c.getAttr(plug))
            except (RuntimeError, ValueError) as exc:
                raise ValueError("Model Clean 不支持归档属性：" + plug) from exc
            rows.append((name, kind, value,
                         bool(c.getAttr(plug, lock=True)),
                         bool(c.getAttr(plug, keyable=True)),
                         bool(c.getAttr(plug, channelBox=True))))
        return tuple(rows)

    def _material_network(self, engines: set[str]):
        c = self.cmds
        rows = []
        for engine in sorted(engines):
            source = tuple(sorted(c.listConnections(
                engine + ".surfaceShader", source=True,
                destination=False, plugs=True) or []))
            upstream = set(c.listHistory(engine, future=False) or [])
            upstream.add(engine)
            nodes = []
            for node in sorted(upstream):
                if not c.objExists(node):
                    continue
                plugs = []
                for attribute in sorted(c.listAttr(
                        node, scalar=True, read=True, settable=True) or []):
                    plug = node + "." + attribute
                    try:
                        plugs.append((attribute,
                                      _json_value(c.getAttr(plug))))
                    except (RuntimeError, ValueError):
                        continue
                nodes.append((node, c.nodeType(node), tuple(plugs)))
            rows.append((engine, source, tuple(nodes)))
        return model_clean_content_sha256(rows)

    def _mesh_data(self, shape: str):
        om = self.om
        dag = om.MSelectionList().add(shape).getDagPath(0)
        mesh = om.MFnMesh(dag)
        points = tuple(tuple(round(float(value), 8)
                             for value in (point.x, point.y, point.z))
                       for point in mesh.getPoints(om.MSpace.kWorld))
        face_counts, face_vertices = mesh.getVertices()
        surface = model_clean_content_sha256((
            points, tuple(int(value) for value in face_counts),
            tuple(int(value) for value in face_vertices)))
        uv_names = tuple(mesh.getUVSetNames())
        uv_rows = []
        for uv_name in uv_names:
            u_values, v_values = mesh.getUVs(uv_name)
            counts, indices = mesh.getAssignedUVs(uv_name)
            uv_rows.append((uv_name,
                tuple(round(float(value), 8) for value in u_values),
                tuple(round(float(value), 8) for value in v_values),
                tuple(int(value) for value in counts),
                tuple(int(value) for value in indices)))
        shaders, assignments = mesh.getConnectedShaders(dag.instanceNumber())
        slots = tuple(om.MFnDependencyNode(shader).name()
                      for shader in shaders)
        material = model_clean_content_sha256((
            slots, tuple(int(value) for value in assignments)))
        return (len(points), len(face_counts), surface,
                uv_names,
                model_clean_content_sha256(uv_rows) if uv_names else "",
                slots, material if slots else "")

    def capture_model_clean_scene(self) -> ModelCleanScene:
        c = self.cmds
        if (c.ls("|geo", long=True,
                 type="transform") or []) != ["|geo"]:
            raise ValueError("Model Clean 需要唯一的顶层 |geo 组")
        nodes = []
        used_engines = set()

        def visit(path: str) -> None:
            shapes = c.listRelatives(path, shapes=True,
                                     fullPath=True,
                                     noIntermediate=True) or []
            if len(shapes) > 1:
                raise ValueError("Model Clean 每个对象只支持一个可见 Shape：" + path)
            if shapes and c.nodeType(shapes[0]) != "mesh":
                raise ValueError("Model Clean 的 geo 中含非多边形 Shape：" + path)
            if shapes:
                shape = shapes[0]
                (vertices, faces, surface, uv_sets, uv_digest,
                 slots, material_digest) = self._mesh_data(shape)
                used_engines.update(slots)
            else:
                shape = None
                vertices = faces = 0
                surface = uv_digest = material_digest = ""
                uv_sets = slots = ()
            attributes = self._user_attributes(path)
            if shape:
                attributes += tuple(("shape:" + row[0], *row[1:])
                                    for row in self._user_attributes(shape))
            parents = c.listRelatives(path, allParents=True,
                                      fullPath=True) or []
            shape_parents = (c.listRelatives(shape, allParents=True,
                                             fullPath=True) or []
                             if shape else [])
            nodes.append(ModelCleanNode(
                path, "mesh" if shape else "group",
                shape.rsplit("|", 1)[-1] if shape else None,
                vertices, faces, uv_sets, slots,
                tuple(row[0] for row in attributes), surface,
                uv_digest, material_digest,
                model_clean_content_sha256(attributes)
                if attributes else "",
                bool(c.referenceQuery(path, isNodeReferenced=True)),
                len(parents) > 1 or len(shape_parents) > 1))
            descendants = c.listRelatives(path, children=True,
                                          fullPath=True) or []
            unexpected = [child for child in descendants
                          if c.nodeType(child) not in ("transform", "mesh")]
            if unexpected:
                raise ValueError("Model Clean 的 geo 中含非模型节点："
                                 + unexpected[0])
            children = [child for child in descendants
                        if c.nodeType(child) == "transform"]
            for child in sorted(children):
                visit(child)

        visit("|geo")
        other = tuple(sorted(path for path in
                             (c.ls(assemblies=True, long=True) or [])
                             if path != "|geo"))
        return ModelCleanScene(
            str(c.file(query=True, sceneName=True) or ""),
            "|geo", tuple(nodes), other,
            tuple(sorted(c.file(query=True, reference=True) or [])),
            self._material_network(used_engines))

    def stage_model_clean_archive(
        self, plan: ModelCleanPlan,
    ) -> ModelCleanArchive:
        c = self.cmds
        if self._archive_dir is not None:
            raise RuntimeError("已有 Model Clean 临时归档")
        scene = self.capture_model_clean_scene()
        if plan_model_clean(scene) != plan:
            raise RuntimeError("Model Clean 归档前来源场景已变化")
        if not c.undoInfo(query=True, state=True):
            raise ValueError("Model Clean 归档需要开启 Maya Undo")
        if not c.pluginInfo("objExport", query=True, loaded=True):
            c.loadPlugin("objExport")
        directory = Path(mkdtemp(prefix="adv-py-model-clean-"))
        self._archive_dir = directory
        selected = c.ls(selection=True, long=True) or []
        modified = bool(c.file(query=True, modified=True))
        archive_items = []
        marker = None
        c.undoInfo(openChunk=True, chunkName="Model Clean OBJ 归档")
        try:
            marker = c.createNode("network", name="AdvPy_ModelCleanProbe")
            for item in plan.meshes:
                duplicate = c.duplicate(
                    item.source_path,
                    name="AdvPy_ModelClean_" + item.obj_key,
                    returnRootsOnly=True)[0]
                descendants = c.listRelatives(
                    duplicate, children=True, fullPath=True,
                    type="transform") or []
                if descendants:
                    c.delete(descendants)
                shapes = c.listRelatives(
                    duplicate, shapes=True, noIntermediate=True,
                    fullPath=True, type="mesh") or []
                if len(shapes) != 1:
                    raise RuntimeError("Model Clean 临时 OBJ 网格不唯一："
                                       + item.source_path)
                c.makeIdentity(duplicate, apply=True, translate=True,
                               rotate=True, scale=True, normal=False)
                c.delete(duplicate, constructionHistory=True)
                obj_path = directory / (item.obj_key + ".obj")
                c.select(duplicate, replace=True)
                c.file(str(obj_path), force=True, exportSelected=True,
                       type="OBJexport",
                       options="groups=0;ptgroups=0;materials=0;"
                               "smoothing=1;normals=1;")
                content = obj_path.read_bytes()
                archive_items.append(ModelCleanArchiveItem(
                    item.obj_key, sha256(content).hexdigest(),
                    item.vertex_count, item.face_count, item.uv_sets,
                    item.material_slots, item.user_attributes,
                    item.surface_sha256, item.uv_content_sha256,
                    item.material_assignment_sha256,
                    item.attribute_content_sha256))
                c.delete(duplicate)
        except Exception:
            c.undoInfo(closeChunk=True)
            if marker is not None:
                c.undo()
            self.release_model_clean_archive(
                ModelCleanArchive(str(directory), "", "", "", "", ()))
            raise
        else:
            c.undoInfo(closeChunk=True)
            c.undo()
        finally:
            if selected:
                c.select(selected, replace=True)
            else:
                c.select(clear=True)
            c.file(modified=modified)
        try:
            manifest = {
                "plan": asdict(plan),
                "scene": asdict(scene),
                "items": [asdict(item) for item in archive_items],
            }
            manifest_bytes = json.dumps(
                manifest, ensure_ascii=False, sort_keys=True,
                allow_nan=False, separators=(",", ":")).encode("utf-8")
            (directory / "manifest.json").write_bytes(manifest_bytes)
            return ModelCleanArchive(
                str(directory), sha256(manifest_bytes).hexdigest(),
                plan.material_network_sha256,
                model_clean_content_sha256(tuple(
                    (item.obj_key, item.uv_content_sha256)
                    for item in archive_items)),
                model_clean_content_sha256(tuple(
                    (item.obj_key, item.attribute_content_sha256)
                    for item in archive_items)),
                tuple(archive_items))
        except Exception:
            self.release_model_clean_archive(
                ModelCleanArchive(str(directory), "", "", "", "", ()))
            raise

    def inspect_model_clean_archive(
        self, archive: ModelCleanArchive,
    ) -> ModelCleanArchive:
        directory = Path(archive.location)
        if self._archive_dir != directory:
            raise ValueError("Model Clean 临时归档归属不符")
        manifest_bytes = (directory / "manifest.json").read_bytes()
        if sha256(manifest_bytes).hexdigest() != archive.scene_payload_sha256:
            raise ValueError("Model Clean 场景归档内容已变化")
        manifest = json.loads(manifest_bytes)
        expected_items = json.loads(json.dumps(
            [asdict(item) for item in archive.items]))
        if manifest.get("items") != expected_items:
            raise ValueError("Model Clean OBJ 清单已变化")
        for item in archive.items:
            content = (directory / (item.obj_key + ".obj")).read_bytes()
            if sha256(content).hexdigest() != item.obj_sha256:
                raise ValueError("Model Clean OBJ 文件已变化：" + item.obj_key)
            lines = content.splitlines()
            vertex_count = sum(line.startswith(b"v ") for line in lines)
            face_count = sum(line.startswith(b"f ") for line in lines)
            if (vertex_count != item.vertex_count or
                    face_count != item.face_count):
                raise ValueError("Model Clean OBJ 拓扑数量不一致：" + item.obj_key)
        return archive

    def release_model_clean_archive(self, archive: ModelCleanArchive) -> None:
        directory = Path(archive.location)
        if self._archive_dir != directory:
            raise ValueError("Model Clean 临时归档归属不符")
        self._archive_dir = None
        shutil.rmtree(directory)
