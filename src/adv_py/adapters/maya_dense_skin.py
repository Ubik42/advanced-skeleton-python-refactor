"""Maya capture and undoable bulk write of exact Skin weights."""
from __future__ import annotations

from array import array
from pathlib import Path
import tempfile

from adv_py.core.dense_skin_transfer import DenseSkinWeights, validate_dense_skin
from .maya_body import MayaBodyBuildHost


class MayaDenseSkinHost(MayaBodyBuildHost):
    def _skin_api(self, skin_name: str):
        from maya.api import OpenMaya as om
        from maya.api import OpenMayaAnim as oma

        c = self._cmds
        skins = c.ls(skin_name, type="skinCluster") or []
        if len(skins) != 1:
            raise ValueError("Skin 节点不存在或名称不唯一：" + skin_name)
        shapes = c.skinCluster(skins[0], query=True, geometry=True) or []
        if len(shapes) != 1:
            raise ValueError("Skin 需要唯一网格：" + skin_name)
        shape = (c.ls(shapes[0], long=True, type="mesh") or [])[0]
        selection = om.MSelectionList()
        selection.add(skins[0])
        skin_fn = oma.MFnSkinCluster(selection.getDependNode(0))
        selection = om.MSelectionList()
        selection.add(shape)
        dag = selection.getDagPath(0)
        count = int(c.polyEvaluate(shape, vertex=True))
        component_fn = om.MFnSingleIndexedComponent()
        component = component_fn.create(om.MFn.kMeshVertComponent)
        component_fn.addElements(range(count))
        names = tuple(path.fullPathName().rsplit("|", 1)[-1]
                      for path in skin_fn.influenceObjects())
        return skin_fn, dag, component, names, count

    def capture_dense_skin(self, skin_name: str) -> DenseSkinWeights:
        skin_fn, dag, component, names, count = self._skin_api(skin_name)
        values, width = skin_fn.getWeights(dag, component)
        if width != len(names):
            raise RuntimeError("Skin API 返回的影响关节维度不符")
        data = DenseSkinWeights(skin_name, count, names,
                                array("d", values).tobytes())
        validate_dense_skin(data)
        return data

    def apply_dense_skin(self, data: DenseSkinWeights) -> None:
        self._require_transaction()
        validate_dense_skin(data)
        _, dag, _, names, count = self._skin_api(data.skin_name)
        if count != data.vertex_count or names != data.influence_names:
            raise ValueError("Skin 目标在批量写入前发生变化")
        plugin = (Path(__file__).resolve().parents[1] / "maya_plugins"
                  / "skin_bulk.py")
        self._cmds.loadPlugin(str(plugin), quiet=True)
        with tempfile.TemporaryDirectory(prefix="advpy-skin-") as directory:
            path = Path(directory) / "weights.bin"
            path.write_bytes(data.values)
            self._transaction_changed = True
            self._cmds.advPySetSkinWeights(
                data.skin_name, dag.fullPathName(), str(path),
                data.vertex_count, len(names))
