"""The polygon mask and geometry inputs used before Face fitting."""
from __future__ import annotations

from enum import Enum
from contextlib import nullcontext

from adv_py.core.original_eye_lid_fit import order_original_eye_lid_loop
from .face_input_upgrade import check_original_face_input_upgrade


class FacePreRole(str, Enum):
    FACE = "Face"
    ALL_HEAD = "AllHead"


class EyeLidLayer(str, Enum):
    OUTER = "Outer"
    MAIN = "Main"
    INNER = "Inner"


class OptionalEyeLidLayer(str, Enum):
    MAIN2 = "Main2"


class FaceSide(str, Enum):
    RIGHT = "Right"
    LEFT = "Left"


class RecordFacePreInput:
    def __init__(self, host) -> None:
        self.host = host

    def head_joint(self) -> str:
        check_original_face_input_upgrade(self.host)
        with self.host.transaction('记录原版 Face Head 关节'):
            return self.host.record_original_face_head_joint()

    def eye(self,side: FaceSide):
        if not isinstance(side,FaceSide):raise ValueError('Face Eye 输入侧别无效')
        check_original_face_input_upgrade(self.host)
        with self.host.transaction('记录原版 '+side.value+' Eye 输入'):
            return self.host.record_original_face_eye_input(side.value)

    def mask(self) -> tuple[str, int, float]:
        check_original_face_input_upgrade(self.host)
        with self.host.transaction('记录原版 Face Mask'):
            prepare=getattr(self.host,'prepare_original_face_mask',None)
            if prepare is not None and not prepare():
                return None
            # Sample after unit conversion and optional build-pose restore.
            mesh, faces, bounds = self.host.selected_mask()
            if not faces:
                raise ValueError("Mask 需要选择面部多边形面")
            self.host.store_face_mask(mesh, faces, bounds)
            stored = self.host.read_face_mask()
            if stored[:2] != (mesh, faces):
                raise RuntimeError("Mask 写后读回不一致")
            options = getattr(self.host, '_face_input_options', None)
            if options is not None:
                self.host.write_original_face_options(options, complete=True)
            return mesh, len(faces), stored[2]

    def objects(self, role: FacePreRole, head_joint: str) -> tuple[str, ...]:
        if not isinstance(role, FacePreRole):
            raise ValueError("Face Pre 输入类型无效")
        check_original_face_input_upgrade(self.host)
        with (nullcontext() if getattr(self.host, '_transaction_active', False) else
              self.host.transaction('记录原版 Face '+role.value+' 输入')):
            ensure = getattr(self.host, 'ensure_original_face_fit_container', None)
            if ensure is not None:
                ensure()
            return self._objects(role, head_joint)

    def _objects(self, role, head_joint):
        if role is FacePreRole.ALL_HEAD:
            validate=getattr(self.host,'validate_original_all_head_selection',None)
            if validate is not None:validate()
        meshes = self.host.selected_face_meshes()
        if not meshes:
            raise ValueError("请先选择 Face 或 All Head 几何对象")
        if role is FacePreRole.ALL_HEAD:
            face = self.host.read_face_objects(FacePreRole.FACE)
            if face and (len(face) != 1 or face[0] not in meshes):
                raise ValueError("All Head 必须包含已记录的 Face 网格")
        if self.host.store_face_objects(role, meshes, head_joint) is False:
            return None
        if self.host.read_face_objects(role) != meshes:
            raise RuntimeError("Face Pre 对象写后读回不一致")
        return meshes


class CreateFaceEyeBallFit:
    def __init__(self, host) -> None:
        self.host = host

    def execute(self, eye_mesh: str, head_joint: str) -> str:
        if not eye_mesh or not head_joint:
            raise ValueError("EyeBall Fit 需要当前侧眼网格和 Head 关节")
        self.host.read_face_mask()
        side = self.host.active_face_side()
        result = self.host.create_eye_ball_fit(eye_mesh, head_joint, side)
        if result is None:
            return None
        if self.host.read_eye_ball_fit() != result:
            raise RuntimeError("EyeBall Fit 写后读回不一致")
        return result


class CreateFaceEyeLidFit:
    def __init__(self, host) -> None:
        self.host = host

    def execute(self, layer: EyeLidLayer, *,native_main2_part=False) -> tuple[str, str]:
        if not isinstance(layer, (EyeLidLayer, OptionalEyeLidLayer)):
            raise ValueError("眼睑 Fit 层级无效")
        mesh, edges, positions, corners = self.host.selected_eye_lid_edges()
        side = self.host.active_face_side()
        cyclops = getattr(self.host, 'original_eye_lid_fit_cyclops', lambda: False)()
        ordered = order_original_eye_lid_loop(edges, positions,
            corner_vertices=corners, side=side.value, cyclops=cyclops,
            extra_main=layer is OptionalEyeLidLayer.MAIN2 and not native_main2_part)
        options={'native_main2_part':True} if native_main2_part else {}
        created = self.host.create_eye_lid_fit(layer, mesh, ordered,
                                               positions, edges, corners,**options)
        if self.host.read_eye_lid_fit(layer) != created:
            raise RuntimeError("眼睑 Fit 写后读回不一致")
        if layer is EyeLidLayer.INNER:
            self.host.read_eye_lid_area()
        return created
