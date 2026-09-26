"""Undoable dense skin-weight write for Maya Python API 2.0."""
from __future__ import annotations

from array import array
from pathlib import Path

from maya.api import OpenMaya as om
from maya.api import OpenMayaAnim as oma
from maya import OpenMayaMPx as ompx


COMMAND_NAME = "advPySetSkinWeights"


class SetSkinWeights(ompx.MPxCommand):
    def __init__(self):
        super().__init__()
        self._skin = None
        self._dag = None
        self._component = None
        self._indices = None
        self._new = None
        self._old = None

    @staticmethod
    def creator():
        return ompx.asMPxPtr(SetSkinWeights())

    def isUndoable(self):
        return True

    def doIt(self, arguments):
        skin_name = arguments.asString(0)
        shape_name = arguments.asString(1)
        payload_path = Path(arguments.asString(2))
        vertex_count = arguments.asInt(3)
        influence_count = arguments.asInt(4)
        if vertex_count < 1 or influence_count < 1:
            raise ValueError("Skin 权重矩阵维度无效")
        selection = om.MSelectionList()
        selection.add(skin_name)
        self._skin = oma.MFnSkinCluster(selection.getDependNode(0))
        selection = om.MSelectionList()
        selection.add(shape_name)
        self._dag = selection.getDagPath(0)
        actual_influences = self._skin.influenceObjects()
        if len(actual_influences) != influence_count:
            raise ValueError("Skin 影响关节数量发生变化")
        self._indices = om.MIntArray(list(range(influence_count)))
        component_fn = om.MFnSingleIndexedComponent()
        self._component = component_fn.create(om.MFn.kMeshVertComponent)
        component_fn.addElements(range(vertex_count))
        expected_bytes = vertex_count * influence_count * 8
        if payload_path.stat().st_size != expected_bytes:
            raise ValueError("Skin 权重文件大小与矩阵维度不符")
        values = array("d")
        with payload_path.open("rb") as stream:
            values.fromfile(stream, vertex_count * influence_count)
        if len(values) != vertex_count * influence_count:
            raise ValueError("Skin 权重文件读取不完整")
        self._new = om.MDoubleArray(values.tolist())
        self._old, actual_count = self._skin.getWeights(
            self._dag, self._component)
        if actual_count != influence_count:
            raise ValueError("Skin 当前权重矩阵维度不符")
        self.redoIt()

    def redoIt(self):
        self._skin.setWeights(self._dag, self._component,
                              self._indices, self._new, normalize=False)

    def undoIt(self):
        self._skin.setWeights(self._dag, self._component,
                              self._indices, self._old, normalize=False)


def initializePlugin(plugin_object):
    plugin = ompx.MFnPlugin(plugin_object, "ADV Python", "0.1", "Any")
    plugin.registerCommand(COMMAND_NAME, SetSkinWeights.creator)


def uninitializePlugin(plugin_object):
    plugin = ompx.MFnPlugin(plugin_object)
    plugin.deregisterCommand(COMMAND_NAME)
