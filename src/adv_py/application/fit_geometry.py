"""Display and rebuild the source FitGeometry visualizer graph."""
from contextlib import nullcontext

class UpdateFitGeometry:
    def __init__(self,host):self.host=host

    def execute(self,*,visible=True,geometry_type='boxes',gap=None):
        if type(visible) is not bool or geometry_type not in ('boxes','cylinders','spheres','bones'):
            raise ValueError('Fit 几何显示选项无效')
        if gap is not None and (isinstance(gap,bool) or not isinstance(gap,(int,float))
                                or not 0<=gap<=1):
            raise ValueError('Fit 几何间距必须在 0 到 1 之间')
        mode_scope = getattr(self.host, 'fit_geometry_mode_scope', None)
        with mode_scope(visible) if mode_scope is not None else nullcontext():
            return self._execute(visible, geometry_type, gap)

    def _execute(self, visible, geometry_type, gap):
        with self.host.transaction('更新 Fit 几何显示'):
            # File import must precede Fit edits: Maya import Undo restores
            # the pre-import scene, including its attributes and orientation.
            with self.host.fit_geometry_assets(visible):
                self.host.ensure_fit_geometry_profiles()
                self.host.set_fit_geometry_display(visible,geometry_type,gap)
                if not visible:
                    self.host.delete_fit_geometry()
                    return 0
                self.host.update_fit_geometry_orientation()
                plans=self.host.capture_fit_geometry()
                self.host.create_fit_geometry(plans)
                self.host.set_fit_geometry_display(visible,geometry_type,gap)
        return len(plans)
