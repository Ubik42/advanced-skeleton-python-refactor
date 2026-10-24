"""Native component-center Snap, Copy and Paste placement operations."""
from math import isfinite


class MayaSourceFitPlacementMixin:
    def _source_fit_move_context(self):
        raw = getattr(self._cmds,'raw',self._cmds)
        raw.setToolTo('moveSuperContext')
        return raw

    def snap_source_fit_placement(self):
        self._require_transaction()
        raw = self._source_fit_move_context()
        c = self._cmds
        selected = tuple(c.ls(selection=True,long=True) or ())
        if not selected:
            return None
        joint = selected[-1]
        c.select(joint,deselect=True)
        position = tuple(raw.manipMoveContext('Move',query=True,position=True))
        self._transaction_changed = True
        c.xform(joint,worldSpace=True,translation=position)
        return joint

    def copy_source_fit_placement(self):
        raw = self._source_fit_move_context()
        return tuple(float(value) for value in raw.manipMoveContext('Move',query=True,position=True))

    def paste_source_fit_placement(self, position):
        self._require_transaction()
        if len(position) != 3 or any(not isfinite(value) for value in position):
            raise ValueError('Fit 粘贴位置必须是三个有限数值')
        c = self._cmds
        raw = getattr(c,'raw',c)
        pivot = bool(raw.manipMoveContext('Move',query=True,editPivotMode=True))
        selected = tuple(c.ls(selection=True,long=True) or ())
        for node in selected:
            self._transaction_changed = True
            if pivot:
                c.move(*position,node+'.scalePivot',node+'.rotatePivot',absolute=True)
            else:
                c.move(*position,node,absolute=True)
        return len(selected)
