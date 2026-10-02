"""Original controller selector; this action changes selection only."""
from adv_py.core.control_curve_selection import select_curve_members


class SelectControlCurves:
    def __init__(self,host):self._host=host

    def apply(self,controller_type='FK',side='*All'):
        # Validate before touching Maya selection.
        select_curve_members((),controller_type,side)
        return self._host.select_original_control_curves(controller_type,side)
