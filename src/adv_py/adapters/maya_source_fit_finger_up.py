"""Literal native Finger-up locator/triangle display; no extra pose edits."""
from math import dist

from adv_py.core.source_fit_finger_up import (
    SOURCE_FINGER_CHECK_CHANNELS, source_fit_finger_confirmation,
    source_fit_finger_off_axis, source_fit_fingers,
)
from .maya_source_fit_pole_vectors import ensure_fit_shaders


class MayaSourceFitFingerUpMixin:
    def display_fit_finger_up(self, enabled, *, confirm=None):
        self._require_transaction()
        if type(enabled) is not bool:
            raise ValueError('Fit Finger-up 显示必须是布尔值')
        c = self._cmds
        selected = tuple(c.ls(selection=True, long=True) or ())
        if not c.objExists('FitSkeleton'):
            return False
        self._transaction_changed = True
        # Native Finger-up owns the entire visualizer container and clears
        # PoleVector/geometry displays too. Do not retain an invented subgroup.
        if c.objExists('FitSkeletonVisualizers'):
            c.delete('FitSkeletonVisualizers')
        if not enabled:
            return False
        self.manual_update_fit('FitSkeleton')
        candidates = tuple(finger+'Finger'+str(index)
            for finger in ('Thumb','Pinky','Ring','Middle','Index') for index in range(5))
        fingers = source_fit_fingers(name for name in candidates if c.objExists(name))
        samples = []
        for finger in fingers:
            for index in finger.indices:
                joint = finger.joint(index)
                parents = c.listRelatives(joint, parent=True) or ()
                if not parents or 'Finger' not in parents[0]:
                    continue
                for channel in SOURCE_FINGER_CHECK_CHANNELS:
                    samples.append((joint, channel, c.getAttr(joint+'.'+channel)))
        prompt = source_fit_finger_confirmation(source_fit_finger_off_axis(samples))
        if prompt:
            if confirm is None:
                raw = getattr(c, 'raw', c)
                proceed = raw.confirmDialog(title='Confirm', message=prompt,
                    button=('Proceed','Cancel'), defaultButton='Cancel',
                    dismissString='Cancel') == 'Proceed'
            else:
                proceed = confirm(prompt)
            if not proceed:
                return False
        ensure_fit_shaders(c)
        c.createNode('transform', name='FitSkeletonVisualizers')
        c.createNode('transform', name='FitSkeletonFingerUp', parent='FitSkeletonVisualizers')
        for finger in fingers:
            self._create_source_fit_finger_up(finger)
        try:
            c.select(selected, replace=True) if selected else c.select(clear=True)
        except RuntimeError:
            pass
        return True

    def _create_source_fit_finger_up(self, finger):
        c = self._cmds
        start, end = finger.joint(finger.first), finger.joint(finger.last)
        distance = dist(c.xform(start, query=True, worldSpace=True, translation=True),
                        c.xform(end, query=True, worldSpace=True, translation=True))
        up = c.spaceLocator(name=finger.name+'UpLocator')[0]
        up = c.parent(up, 'FitSkeletonFingerUp')[0]
        c.setAttr(up+'.localScale', *((distance/4.,)*3), type='float3')
        c.delete(c.pointConstraint(start, end, up))
        up = c.parent(up, start)[0]
        c.setAttr(up+'.tz', distance/2.)
        up = c.parent(up, 'FitSkeletonFingerUp')[0]
        for index in finger.indices:
            joint = finger.joint(index)
            locator = c.spaceLocator(name=finger.name+str(index)+'JointLocator')[0]
            locator = c.parent(locator, 'FitSkeletonFingerUp')[0]
            c.setAttr(locator+'.visibility', False)
            c.pointConstraint(joint, locator)
            if index <= finger.first:
                continue
            facet = c.polyCreateFacet(name='VisualizeFingerUp_'+joint,
                constructionHistory=False, texture=1, subdivision=1,
                point=((0.,0.,0.),)*3)[0]
            facet = c.parent(facet, 'FitSkeletonFingerUp')[0]
            c.sets(facet, edit=True, forceElement='asRedSSSG')
            c.setAttr(facet+'.overrideEnabled', True)
            c.setAttr(facet+'.overrideDisplayType', 2)
            shape = c.listRelatives(facet, shapes=True, type='mesh', fullPath=True)[0]
            # Consecutive index, even if missing: source does not bridge gaps.
            previous = finger.name+str(index-1)+'JointLocator'
            for vertex, node in enumerate((locator, previous, up)):
                c.connectAttr(node+'.worldPosition[0]', shape+'.pnts['+str(vertex)+']', force=True)
