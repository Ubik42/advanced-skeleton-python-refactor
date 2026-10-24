"""Export evaluated ADV FaceJoint drivers to the native FaceRig JSON schema."""
import json
from pathlib import Path

from adv_py.core.unreal_face_solver import face_solver_filename


class ExportUnrealFaceSolver:
    def __init__(self, host):
        self.host = host

    def apply(self, export_file):
        filename = face_solver_filename(str(export_file))
        if not filename:
            raise ValueError('请选择 FaceRig JSON 或对应 FBX 的输出路径')
        destination = Path(filename)
        if not destination.is_absolute() or not destination.parent.is_dir():
            raise ValueError('FaceRig 输出目录不存在，或文件路径不是绝对路径')
        self.host.preflight_unreal_face_solver()
        with self.host.transaction('FaceRig export'):
            document = self.host.capture_unreal_face_solver()
            if document is None:
                return None
            destination.write_text(json.dumps(document, ensure_ascii=False, indent=2,
                                               allow_nan=False) + '\n', encoding='utf-8')
        return destination
