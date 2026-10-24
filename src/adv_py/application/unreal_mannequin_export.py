"""Create, transfer, export and restore ADV's native Mannequin asset."""
from pathlib import Path
from typing import Protocol

from adv_py.core.original_fbx_export import MannequinExportOptions
from adv_py.core.unreal_mannequin import plan_mannequin
from .unreal_mannequin import MannequinHost, build_mannequin


class MannequinExportHost(MannequinHost, Protocol):
    def preflight_mannequin_export(self, destination: Path | None,
                                  template_path: str, options) -> None: ...
    def confirm_original_control_build_pose(self) -> int: ...
    def clear_mannequin_export_assets(self) -> None: ...
    def remove_unused_mannequin_joints(self) -> None: ...
    def prepare_mannequin_export(self, options) -> None: ...
    def confirm_native_fbx_export(self) -> bool: ...
    def export_mannequin_fbx(self, destination: Path | None, options) -> Path | None: ...
    def finish_mannequin_export(self, options) -> None: ...


class ExportMannequin:
    def __init__(self, host: MannequinExportHost):
        self.host = host

    def apply(self, destination, template_path: str, *,
              options: MannequinExportOptions | None = None) -> Path | None:
        options = options or MannequinExportOptions()
        if not isinstance(options, MannequinExportOptions):
            raise TypeError('Mannequin 导出选项类型无效')
        destination = Path(destination) if destination is not None else None
        self.host.preflight_mannequin_export(destination, template_path, options)
        plan = plan_mannequin(options.template,
            scale_adv_to_template=options.scale_adv_to_template,
            match_template_pose=options.match_template_pose)
        with self.host.transaction('Mannequin export'):
            if not self.host.confirm_original_control_build_pose():
                return None
            self.host.clear_mannequin_export_assets()
            # Preflight names after the native cleanup, before importing.
            self.host.preflight(plan, template_path)
            build_mannequin(self.host, plan, template_path)
            self.host.transfer_skin()
            if options.remove_unused_joints:
                self.host.remove_unused_mannequin_joints()
            self.host.prepare_mannequin_export(options)
            if not self.host.confirm_native_fbx_export():
                self.host.finish_mannequin_export(options)
                return None
            result = self.host.export_mannequin_fbx(destination, options)
            self.host.finish_mannequin_export(options)
        return result
