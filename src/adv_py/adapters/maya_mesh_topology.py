"""Topology identity for meshes bound by this project."""
from __future__ import annotations

from array import array
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
    digest.update(array("I", face_sizes).tobytes())
    digest.update(array("I", face_vertices).tobytes())
    return digest.hexdigest()


def assert_bound_topology(cmds, skin: str, shape: str) -> None:
    if not cmds.attributeQuery(TOPOLOGY_ATTRIBUTE, node=skin, exists=True):
        return  # Older scenes have no recorded bind topology.
    expected = cmds.getAttr(f"{skin}.{TOPOLOGY_ATTRIBUTE}")
    if expected != mesh_topology_digest(shape):
        raise ValueError(
            f"{skin} 的模型拓扑已在绑定后改变；旧 Skin 权重不能直接沿用。"
            "请恢复原拓扑，或重新绑定并转移权重。"
        )
