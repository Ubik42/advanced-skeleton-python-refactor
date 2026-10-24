"""Original custom-control surface attachment through native UV projection.

MEL 57917–57974 maps a posed surface point to build pose using a duplicated
mesh, automatic UVs and pointOnPolyConstraint. A barycentric approximation of
the closest polygon is not the same mapping.
"""
from contextlib import contextmanager, nullcontext

from .maya_face_build_pose import MayaFaceBuildPoseMixin
from .maya_original_driver_attributes import MayaOriginalDriverAttributesMixin


class _PoseHost(MayaOriginalDriverAttributesMixin, MayaFaceBuildPoseMixin):
    def __init__(self, owner):
        self.owner = owner
        self._cmds = owner._cmds
        self._transaction_changed = False

    def __getattr__(self, name):
        return getattr(self.owner, name)


def _restore_rows(commands):
    """asGetRestorePoseCmd's native settable/keyable control-set order."""
    rows = []
    for name in ("ControlSet", "FaceControlSet"):
        if not commands.objExists(name):continue
        for control in commands.sets(name, query=True) or []:
            for attribute in commands.listAttr(control, keyable=True) or []:
                plug = control + "." + attribute
                if commands.getAttr(plug, lock=True) or not commands.getAttr(plug, settable=True):
                    continue
                rows.append((plug, commands.getAttr(plug)))
    return tuple(rows)


def _set_surface_uv(commands, constraint, u, v):
    """Resolve the stock utility's namespace-sanitized target aliases."""
    expected = ("TempUVAttachMeshU0", "TempUVAttachMeshV0")
    if all(commands.objExists(constraint + "." + attr) for attr in expected):
        attributes = expected
    else:
        names = commands.listAttr(constraint, userDefined=True) or []
        pairs = [(name, name[:-2] + "V0") for name in names
                 if name.endswith("U0") and name[:-2] + "V0" in names]
        if len(pairs) != 1:
            raise ValueError("原生表面约束缺少唯一的首目标 UV 属性")
        attributes = pairs[0]
    for attribute, value in zip(attributes, (u, v)):
        commands.setAttr(constraint + "." + attribute, value)


def original_softmod_mesh(host, deformer):
    """MEL 57898: first output mesh in native forward history, even multi-geometry."""
    commands = host._cmds
    raw = getattr(commands, "raw", commands)
    source = host._unique(deformer, "softMod")
    for node in raw.listHistory(source, future=True, pruneDagObjects=False,
                                interestLevel=2) or []:
        if raw.nodeType(node) == "mesh":
            parents = raw.listRelatives(node, parent=True, fullPath=True) or []
            if parents:
                return host._mesh(parents[0])
    raise ValueError("SoftMod 输出历史中没有可用的多边形网格")


@contextmanager
def build_pose_session(host, deformer):
    host._require_transaction()
    c = host._cmds
    raw = getattr(c, "raw", c)
    from maya import mel
    source = host._unique(deformer, "softMod")
    mesh = original_softmod_mesh(host, source)
    handles = raw.listConnections(source + ".matrix", source=True, destination=False, type="transform") or []
    if len(handles) != 1:raise ValueError("构建姿态定位要求唯一 SoftMod 操作柄")
    handle = host._unique(handles[0], "transform")
    before = tuple(raw.getAttr(handle + ".translate")[0])
    pivot = tuple(raw.xform(handle, query=True, worldSpace=True, pivots=True)[:3])
    center = tuple(raw.getAttr(source + ".falloffCenter")[0])
    origins = {shape: tuple(raw.getAttr(shape + ".origin")[0])
        for shape in raw.listRelatives(handle, shapes=True, fullPath=True) or []
        if raw.objExists(shape + ".origin")}
    pose = _restore_rows(c)
    host._transaction_changed = True
    temporary_mesh = temporary_transform = sampler = None
    pose_host = _PoseHost(host)
    scope = c._creation_namespace if hasattr(c, "_creation_namespace") else nullcontext
    try:
        raw.setAttr(handle + ".translate", 0, 0, 0, type="float3")
        posed = raw.xform(handle, query=True, worldSpace=True, pivots=True)[:3]
        temporary_mesh = c.duplicate(mesh, name="TempUVAttachMesh")[0]
        try:temporary_mesh = c.parent(temporary_mesh, world=True)[0]
        except RuntimeError:pass
        for shape in c.listRelatives(temporary_mesh, shapes=True, fullPath=True) or []:
            if c.nodeType(shape) == "mesh" and c.getAttr(shape + ".intermediateObject"):
                c.delete(shape)
        c.select(temporary_mesh, replace=True)
        current = raw.polyUVSet(query=True, currentUVSet=True)[0]
        for uv in raw.polyUVSet(query=True, allUVSets=True) or []:
            if uv != current:raw.polyUVSet(delete=True, uvSet=uv)
        c.select(temporary_mesh, replace=True)
        raw.polyAutoProjection(constructionHistory=False, layoutMethod=0,
            projectBothDirections=False, insertBeforeDeformers=True,
            createNewMap=False, layout=2, scaleMode=1, optimize=1,
            planes=6, percentageSpace=.2, worldSpace=False)
        if c.objExists("closestSampler"):c.delete("closestSampler")
        sampler = c.createNode("closestPointOnMesh", name="closestSampler")
        c.connectAttr(temporary_mesh + ".outMesh", sampler + ".inMesh", force=True)
        c.connectAttr(temporary_mesh + ".worldMatrix[0]", sampler + ".inputMatrix", force=True)
        c.setAttr(sampler + ".inPosition", *posed)
        u, v = c.getAttr(sampler + ".parameterU"), c.getAttr(sampler + ".parameterV")
        c.delete(sampler);sampler = None
        if c.objExists("tempXform"):c.delete("tempXform")
        temporary_transform = c.createNode("transform", name="tempXform")
        c.select(temporary_mesh, temporary_transform, replace=True)
        with scope():
            mel.eval('doCreatePointOnPolyConstraintArgList 1 { "0","0","0","1","","1" };')
        constraint = host.scene_address("tempXform_pointOnPolyConstraint1")
        _set_surface_uv(raw, constraint, u, v)
        pose_host.go_to_original_corrective_build_pose(face=host.face)
        c.select(mesh, temporary_mesh, replace=True)
        c.blendShape(frontOfChain=True, weight=(0, 1))
        build_center = c.xform(temporary_transform, query=True, worldSpace=True, translation=True)
        c.delete(temporary_transform, temporary_mesh)
        temporary_transform = temporary_mesh = None
        raw.xform(handle, pivots=build_center)
        for shape in origins:raw.setAttr(shape + ".origin", *build_center, type="float3")
        raw.setAttr(source + ".falloffCenter", *build_center, type="float3")
        yield
    finally:
        host._transaction_changed |= pose_host._transaction_changed
        for node in (sampler, temporary_transform, temporary_mesh):
            if node and c.objExists(node):c.delete(node)
        # A read-only plan returns to the caller's pose. Once the source
        # handle has been consumed, ADV leaves the new rig in build pose.
        if raw.objExists(handle):
            raw.setAttr(handle + ".translate", *before, type="float3")
            raw.xform(handle, worldSpace=True, pivots=pivot)
            for shape, value in origins.items():
                if raw.objExists(shape):raw.setAttr(shape + ".origin", *value, type="float3")
            if raw.objExists(source):raw.setAttr(source + ".falloffCenter", *center, type="float3")
            for plug, value in pose:
                if c.objExists(plug):c.setAttr(plug, value)
