"""Native asFitSDKCreateAttribute capture and key-writing host boundary."""
from adv_py.core.source_fit_sdk import (
    SourceFitSDKOptions, SourceFitSDKPlan, source_fit_sdk_driven,
)


class MayaSourceFitSDKMixin:
    def capture_source_fit_sdk(self):
        c = self._cmds
        selected = tuple(c.ls(selection=True) or ())
        if not selected:
            raise ValueError('Nothing selected, you should select a SDK Object first')
        control = selected[0]
        children = c.listRelatives(control, children=True) or ()
        if not children or c.objectType(children[0]) != 'nurbsCurve':
            raise ValueError('Selected Object is not a nurbsCurve')
        pose = c.getAttr(control+'.defaultPose')
        samples = tuple((joint, kind+axis, float(c.getAttr(joint+'.'+kind+axis)))
            for joint in c.listRelatives('FitSkeleton', allDescendents=True, type='joint') or ()
            for kind in 'trs' for axis in 'xyz')
        identity = getattr(c, 'identity', None)
        driven = source_fit_sdk_driven(pose, samples,
            map_address=identity.to_local if identity is not None else lambda value: value)
        if not driven:
            raise ValueError('Found No attributes changed from Default Pose')
        return SourceFitSDKPlan(control, selected, driven)

    def create_source_fit_sdk_attribute(self, plan, options):
        self._require_transaction()
        if not isinstance(plan, SourceFitSDKPlan) or not isinstance(options, SourceFitSDKOptions):
            raise ValueError('Fit SDK 创建需要原版姿态计划和选项')
        if not plan.driven:
            raise ValueError('Found No attributes changed from Default Pose')
        c = self._cmds
        self._transaction_changed = True
        driver = plan.control+'.'+options.attribute
        if c.attributeQuery(options.attribute, node=plan.control, exists=True):
            c.deleteAttr(driver)
        c.addAttr(plan.control, longName=options.attribute, attributeType='double', keyable=True)
        if options.soft_min is not None:
            c.addAttr(driver, edit=True, softMinValue=options.soft_min)
        if options.soft_max is not None:
            c.addAttr(driver, edit=True, softMaxValue=options.soft_max)
        for row in plan.driven:
            c.setDrivenKeyframe(row.plug, inTangentType='linear', outTangentType='linear',
                value=row.default_value, driverValue=0., currentDriver=driver)
            c.setDrivenKeyframe(row.plug, inTangentType='linear', outTangentType='linear',
                value=row.posed_value, driverValue=options.driver_value, currentDriver=driver)
        c.select(tuple(row.joint for row in plan.driven), replace=True)
        c.setInfinity(preInfinite='cycleRelative', postInfinite='cycleRelative')
        c.select(plan.selection, replace=True)
        return len(plan.driven)
