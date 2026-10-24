"""Native asExportFbxBrowser scene export, separate from baked asset publishing."""
from pathlib import Path
from typing import Protocol


class OriginalFbxExportHost(Protocol):
    def transaction(self, label): ...
    def preflight_original_fbx_export(self, destination): ...
    def confirm_original_fbx_export(self): ...
    def export_mannequin_fbx(self, destination, options): ...


class ExportOriginalFbx:
    def __init__(self, host: OriginalFbxExportHost):
        self.host = host

    def apply(self, destination=None):
        destination = Path(destination) if destination is not None else None
        self.host.preflight_original_fbx_export(destination)
        # Native Root Motion confirmation can create a permanent joint even if
        # the later file dialog is cancelled. It is not a temporary bake asset.
        if not self.host.confirm_original_fbx_export():
            return None
        with self.host.transaction('Export FBX'):
            result = self.host.export_mannequin_fbx(destination, None)
        return result
