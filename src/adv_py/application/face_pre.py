"""The polygon mask and geometry inputs used before Face fitting."""
from __future__ import annotations

from enum import Enum

from adv_py.core.face_eyelid_fit import order_eye_lid_loop


class FacePreRole(str, Enum):
    FACE = "Face"
    ALL_HEAD = "AllHead"


class EyeLidLayer(str, Enum):
    OUTER = "Outer"
    MAIN = "Main"
    INNER = "Inner"


class RecordFacePreInput:
    def __init__(self, host) -> None:
        self.host = host

    def mask(self) -> tuple[str, int, float]:
        mesh, faces, bounds = self.host.selected_mask()
        if not faces:
            raise ValueError("Mask 需要选择面部多边形面")
        self.host.store_face_mask(mesh, faces, bounds)
        stored = self.host.read_face_mask()
        if stored[:2] != (mesh, faces):
            raise RuntimeError("Mask 写后读回不一致")
        return mesh, len(faces), stored[2]

    def objects(self, role: FacePreRole, head_joint: str) -> tuple[str, ...]:
        if not isinstance(role, FacePreRole):
            raise ValueError("Face Pre 输入类型无效")
        meshes = self.host.selected_face_meshes()
        if not meshes or (role is FacePreRole.FACE and len(meshes) != 1):
            raise ValueError("Face 需要一件网格；All Head 需要至少一件网格")
        if role is FacePreRole.ALL_HEAD:
            face = self.host.read_face_objects(FacePreRole.FACE)
            if len(face) != 1 or face[0] not in meshes:
                raise ValueError("All Head 必须包含已记录的 Face 网格")
        self.host.store_face_objects(role, meshes, head_joint)
        if self.host.read_face_objects(role) != meshes:
            raise RuntimeError("Face Pre 对象写后读回不一致")
        return meshes


class CreateFaceEyeBallFit:
    def __init__(self, host) -> None:
        self.host = host

    def execute(self, right_eye: str, head_joint: str) -> str:
        if not right_eye or not head_joint:
            raise ValueError("EyeBall Fit 需要右眼网格和 Head 关节")
        self.host.read_face_mask()
        result = self.host.create_eye_ball_fit(right_eye, head_joint)
        if self.host.read_eye_ball_fit() != result:
            raise RuntimeError("EyeBall Fit 写后读回不一致")
        return result


class CreateFaceEyeLidFit:
    def __init__(self, host) -> None:
        self.host = host

    def execute(self, layer: EyeLidLayer) -> tuple[str, str]:
        if not isinstance(layer, EyeLidLayer):
            raise ValueError("眼睑 Fit 层级无效")
        mesh, edges, positions, corners = self.host.selected_eye_lid_edges()
        ordered = order_eye_lid_loop(edges, positions,
            eye_center_y=self.host.eye_ball_fit_center_y(),
            corner_vertices=corners)
        created = self.host.create_eye_lid_fit(layer, mesh, ordered,
                                               positions, edges, corners)
        if self.host.read_eye_lid_fit(layer) != created:
            raise RuntimeError("眼睑 Fit 写后读回不一致")
        return created
