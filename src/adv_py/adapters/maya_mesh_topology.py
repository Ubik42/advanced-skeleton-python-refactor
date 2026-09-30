"""Topology identity for meshes bound by this project."""
from __future__ import annotations

from hashlib import sha256
from struct import pack


TOPOLOGY_ATTRIBUTE = "advPyBindTopology"


def mesh_topology_digest(shape: str) -> str:
    from maya.api import OpenMaya as om

    selection = om.MSelectionList()
    selection.add(shape)
    mesh = om.MFnMesh(selection.getDagPath(0))
    face_sizes, face_vertices = mesh.getVertices()
    digest = sha256()
    digest.update(pack("<III", mesh.numVertices, mesh.numPolygons,
                       len(face_vertices)))
    # Fixed byte order keeps a saved bind fingerprint stable when a Maya
    # scene moves between Windows and Linux.
    for values in (face_sizes, face_vertices):
        for offset in range(0, len(values), 4096):
            batch = values[offset:offset + 4096]
            digest.update(pack(f"<{len(batch)}I", *batch))
    return digest.hexdigest()


def assert_bound_topology(cmds, skin: str, shape: str) -> None:
    if not cmds.attributeQuery(TOPOLOGY_ATTRIBUTE, node=skin, exists=True):
        return  # Older scenes have no recorded bind topology.
    expected = cmds.getAttr(f"{skin}.{TOPOLOGY_ATTRIBUTE}")
    scene_shape = (cmds.identity.to_scene(shape)
                   if hasattr(cmds, "identity") else shape)
    if expected != mesh_topology_digest(scene_shape):
        raise ValueError(
            f"{skin} 的模型拓扑已在绑定后改变；旧 Skin 权重不能直接沿用。"
            "请恢复原拓扑，或重新绑定并转移权重。"
        )
