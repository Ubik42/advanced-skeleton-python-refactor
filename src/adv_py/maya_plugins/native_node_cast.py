"""Keep Maya's native nodeCast inside one caller-owned undo operation.

Maya 2024's native nodeCast corrupts an enclosing command chunk. The cast
itself is a swap, so journal that native swap as one explicit command instead
of allowing its private undo implementation to split the surrounding build.
"""
from maya import cmds
from maya.api import OpenMaya as om
from maya import OpenMayaMPx as ompx

COMMAND_NAME = 'advPyNativeNodeCast'


def address(handle):
    obj = handle.object()
    if obj.hasFn(om.MFn.kDagNode):
        return om.MDagPath.getAPathTo(obj).fullPathName()
    return om.MFnDependencyNode(obj).name()


class NativeNodeCast(ompx.MPxCommand):
    @staticmethod
    def creator():
        return ompx.asMPxPtr(NativeNodeCast())

    def isUndoable(self):
        return True

    def doIt(self, arguments):
        source = om.MSelectionList(); source.add(arguments.asString(0))
        destination = om.MSelectionList(); destination.add(arguments.asString(1))
        self.source = om.MObjectHandle(source.getDependNode(0))
        self.destination = om.MObjectHandle(destination.getDependNode(0))
        self.swap_names = arguments.asInt(2) != 0
        self.redoIt()

    def cast(self):
        enabled = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(stateWithoutFlush=False)
        try:
            cmds.nodeCast(address(self.source), address(self.destination), swapNames=self.swap_names)
        finally:
            cmds.undoInfo(stateWithoutFlush=enabled)

    def redoIt(self):
        self.cast()

    def undoIt(self):
        self.cast()


def initializePlugin(plugin_object):
    plugin = ompx.MFnPlugin(plugin_object, 'ADV Python', '1.0', 'Any')
    plugin.registerCommand(COMMAND_NAME, NativeNodeCast.creator)


def uninitializePlugin(plugin_object):
    ompx.MFnPlugin(plugin_object).deregisterCommand(COMMAND_NAME)
