"""Native Fit pole-plane graph: weighted baseline, distances and aim."""
from adv_py.core.source_fit_pole_vectors import source_fit_pole_vectors


def ensure_fit_shaders(c, address=lambda name: name):
    from adv_py.core.face_fit_markers import FIT_MATERIALS
    for leaf, color in FIT_MATERIALS:
        name = address(leaf)
        group = address(leaf+'SG')
        if c.objExists(name) and c.objExists(group):
            continue
        for node in (name, group):
            if c.objExists(node):
                c.delete(node)
        surface = leaf == 'asRedSS'
        c.shadingNode('surfaceShader' if surface else 'lambert', name=name, asShader=True)
        c.sets(renderable=True, noSurfaceShader=True, empty=True, name=group)
        c.connectAttr(name+'.outColor', group+'.surfaceShader', force=True)
        c.setAttr(name+('.outColor' if surface else '.color'), *color, type='float3')


class MayaSourceFitPoleVectorsMixin:
    def _ensure_source_fit_display_settings(self):
        from adv_py.application.fit_settings import EnsureFitSkeletonSettings
        raw = getattr(self._cmds, 'raw', self._cmds)
        gap = (float(raw.optionVar(query='asFitSkeletonGap'))
               if raw.optionVar(exists='asFitSkeletonGap') else .75)
        settings = EnsureFitSkeletonSettings(self).plan(vis_gap_default=gap)
        for setting in settings.additions:
            self.add_fit_skeleton_setting(settings.before.container, setting)

    def display_fit_joint_axes(self, enabled):
        self._require_transaction()
        if type(enabled) is not bool:
            raise ValueError('Fit joint-axis 显示必须是布尔值')
        c = self._cmds
        if not c.objExists('FitSkeleton'):
            return 0
        self._ensure_source_fit_display_settings()
        self._transaction_changed = True
        changed = 0
        for joint in c.listRelatives('FitSkeleton', allDescendents=True,
                                    type='joint', fullPath=True) or ():
            if enabled and not c.listRelatives(joint, children=True, type='joint'):
                continue
            c.setAttr(joint+'.displayLocalAxis', enabled)
            changed += 1
        if c.objExists('FitSkeleton.visJointAxis'):
            c.setAttr('FitSkeleton.visJointAxis', enabled)
        return changed

    def display_fit_joint_orient(self, enabled):
        self._require_transaction()
        if type(enabled) is not bool:
            raise ValueError('Fit joint-orient 显示必须是布尔值')
        c = self._cmds
        if not c.objExists('FitSkeleton'):
            return 0
        self._ensure_source_fit_display_settings()
        joints = tuple(c.listRelatives('FitSkeleton', allDescendents=True,
                                      type='joint', fullPath=True) or ())
        self._transaction_changed = True
        for joint in joints:
            for axis in 'XYZ':
                c.setAttr(joint+'.jointOrient'+axis, keyable=enabled)
        if c.objExists('FitSkeleton.visJointOrient'):
            c.setAttr('FitSkeleton.visJointOrient', enabled)
        return len(joints)

    def straighten_fit_pole_vector(self, limb):
        self._require_transaction()
        if limb not in ('Arm','Leg'):
            raise ValueError('原版 Fit PoleVector 拉直需要 Arm 或 Leg')
        from .maya_fit_auto_place_projection import straight_pole
        return straight_pole(self, limb)

    def display_fit_pole_vectors(self, enabled):
        self._require_transaction()
        if type(enabled) is not bool:
            raise ValueError('Fit PoleVector 显示必须是布尔值')
        c = self._cmds
        if not c.objExists('FitSkeleton'):
            return 0
        self._transaction_changed = True
        if not enabled:
            if c.objExists('FitSkeletonPoleVectors'):
                c.delete('FitSkeletonPoleVectors')
            if c.objExists('FitSkeletonVisualizers'):
                if not c.listRelatives('FitSkeletonVisualizers', children=True):
                    c.delete('FitSkeletonVisualizers')
                if c.objExists('FitSkeleton.visPoleVector'):
                    c.setAttr('FitSkeleton.visPoleVector', False)
            return 0
        if c.objExists('FitSkeletonPoleVectors'):
            return 0
        hierarchy = self.capture_fit_hierarchy('FitSkeleton')
        labels = {joint.path: self.read_joint_label(joint.path) for joint in hierarchy.joints}
        order = tuple(c.listRelatives(hierarchy.container, allDescendents=True,
                                      type='joint', fullPath=True) or ())
        plans = source_fit_pole_vectors(hierarchy, labels, order)
        selected = tuple(c.ls(selection=True, long=True) or ())
        for plan in plans:
            if not c.objExists('FitSkeletonVisualizers'):
                c.createNode('transform', name='FitSkeletonVisualizers')
            if not c.objExists('FitSkeletonPoleVectors'):
                group = c.createNode('transform', name='FitSkeletonPoleVectors', parent='FitSkeletonVisualizers')
                c.setAttr(group+'.inheritsTransform', False)
            ensure_fit_shaders(c)
            self._ensure_source_fit_display_settings()
            c.setAttr('FitSkeleton.visPoleVector', True)
            self._create_fit_pole_vector(plan)
        try:
            c.select(selected, replace=True) if selected else c.select(clear=True)
        except RuntimeError:
            pass
        return len(plans)

    def _create_fit_pole_vector(self, plan):
        c = self._cmds
        stem = plan.stem
        facet = c.polyCreateFacet(name=stem, constructionHistory=False, texture=1,
            subdivision=1, point=((0.,0.,0.),)*4)[0]
        if plan.name == 'Leg':
            c.polyNormal(facet, normalMode=0, userNormalMode=0, constructionHistory=False)
        facet = c.parent(facet, 'FitSkeletonPoleVectors')[0]
        c.sets(facet, edit=True, forceElement='asRedSG')
        c.setAttr(facet+'.overrideEnabled', True)
        c.setAttr(facet+'.overrideDisplayType', 2)
        parent = c.spaceLocator()[0]
        parent = c.rename(parent, stem+'IKParent')
        parent = c.parent(parent, facet)[0]
        c.setAttr(parent+'.visibility', False)
        nodes = {'IKParent': parent}
        for suffix in ('IKChild','IKMid','IKMidFloat','IKPoleVec'):
            nodes[suffix] = c.duplicate(parent, name=stem+suffix)[0]
        nodes['IKPoleVec'] = c.parent(nodes['IKPoleVec'], nodes['IKMidFloat'])[0]
        distances = {}
        for suffix in ('IKDist','IKDistA','IKDistB','IKDistC'):
            distances[suffix] = c.createNode('distanceBetween', name=stem+suffix)
        for distance, first, second in (
                ('IKDist','IKParent','IKChild'),('IKDistA','IKParent','IKMid'),
                ('IKDistB','IKChild','IKMid'),('IKDistC','IKMid','IKMidFloat')):
            c.connectAttr(nodes[first]+'.worldMatrix[0]', distances[distance]+'.inMatrix1')
            c.connectAttr(nodes[second]+'.worldMatrix[0]', distances[distance]+'.inMatrix2')
        total = c.createNode('plusMinusAverage', name=stem+'PMA')
        c.connectAttr(distances['IKDist']+'.distance', total+'.input1D[0]', force=True)
        c.connectAttr(distances['IKDistC']+'.distance', total+'.input1D[1]', force=True)
        c.connectAttr(total+'.output1D', nodes['IKPoleVec']+'.tx')
        c.pointConstraint(plan.start, nodes['IKParent'])
        c.pointConstraint(plan.end, nodes['IKChild'])
        c.pointConstraint(plan.middle, nodes['IKMid'])
        constraint = c.pointConstraint(plan.start, plan.end, nodes['IKMidFloat'])[0]
        aliases = tuple(c.pointConstraint(constraint, query=True, weightAliasList=True) or ())
        if len(aliases) != 2:
            raise RuntimeError('Fit PoleVector 中间基线约束目标数量错误')
        c.connectAttr(distances['IKDistB']+'.distance', constraint+'.'+aliases[0])
        c.connectAttr(distances['IKDistA']+'.distance', constraint+'.'+aliases[1])
        c.aimConstraint(plan.middle, nodes['IKMidFloat'], offset=(0.,0.,0.), weight=1.,
            aimVector=(1.,0.,0.), upVector=(0.,0.,1.), worldUpType='objectrotation',
            worldUpObject=plan.start, worldUpVector=(0.,0.,1.))
        shapes = tuple(c.listRelatives(facet, shapes=True, type='mesh', fullPath=True) or ())
        if len(shapes) != 1:
            raise RuntimeError('Fit PoleVector 缺少唯一网格 Shape')
        for index, suffix in enumerate(('IKParent','IKPoleVec','IKChild','IKMid')):
            c.connectAttr(nodes[suffix]+'.worldPosition[0]', shapes[0]+'.controlPoints['+str(index)+']')
