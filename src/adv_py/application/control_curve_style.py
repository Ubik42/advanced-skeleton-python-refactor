"""Original curve style actions in a single undo and rollback transaction."""
from adv_py.core.control_curve_style import ControlCurvePalette,validate_curve_width,snap_rotation


class SetControlCurvePalette:
    def __init__(self,host):self._host=host

    def apply(self,controls,index,*,rgb=None):
        palette=ControlCurvePalette(index,tuple(rgb) if rgb is not None else None)
        with self._host.transaction('设置控制曲线原版调色板颜色'):
            return self._host.set_original_control_curve_palette(tuple(controls),palette)


class SetControlCurveWidth:
    def __init__(self,host):self._host=host

    def apply(self,controls,width):
        width=validate_curve_width(width)
        with self._host.transaction('设置控制曲线宽度'):
            return self._host.set_original_control_curve_width(tuple(controls),width)


class SnapRotateControlCurves:
    def __init__(self,host):self._host=host

    def apply(self,controls,axis):
        snap_rotation(axis)
        with self._host.transaction('按原版旋转控制曲线 90 度'):
            return self._host.snap_rotate_control_curves(tuple(controls),axis)
