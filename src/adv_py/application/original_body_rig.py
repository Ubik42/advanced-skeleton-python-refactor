"""Write ADV's original BodyRig JSON schema without changing binding behavior."""
import json
from pathlib import Path


class ExportOriginalBodyRig:
    def __init__(self, host):
        self.host = host

    def apply(self, destination):
        filename = str(destination)
        if not filename:
            raise ValueError('BodyRig 导出路径不能为空')
        if not filename.lower().endswith('.json'):
            filename += '.json'
        destination = Path(filename)
        if not destination.is_absolute() or not destination.parent.is_dir():
            raise ValueError('请选择现有目录中的绝对 JSON 文件路径')
        self.host.preflight_original_body_rig()
        with self.host.transaction('BodyRig export'):
            document = self.host.capture_original_body_rig()
            destination.write_text(json.dumps(document, ensure_ascii=False, indent=2,
                                               allow_nan=False) + '\n', encoding='utf-8')
        return destination
