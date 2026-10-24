"""Native four/eight eyelid-joint reduction, source MEL 75705–76095."""
from fnmatch import fnmatchcase

from adv_py.core.original_face_reduction import (
    original_lid_anchor_indices, original_lid_nearest_pair, original_lid_contact,
)
from .maya_original_control_identity import leaf


class MayaOriginalEyeLidReductionMixin:
    def capture_original_eye_lid_reduction(self):
        c = self._cmds
        if c.objExists('FaceDeformationSystem.asReduceEyeLidJoints'):
            raise ValueError('眼睑关节已经执行过缩减')
        if c.objExists('asFaceBS'):
            raise ValueError('关节缩减只用于原版 Joints 面部绑定')
        self._reduction_require_version()
        source = self._reduction_face_input()
        fit = self._fit(required=True)
        source['non_sym'] = bool(c.objExists(fit + '.NonSym') and c.getAttr(fit + '.NonSym'))
        source['lashes'] = self.original_face_part_text('Eyelash')
        source['modifier'] = getattr(c, 'raw', c).getModifiers()
        return source

    def _lid_reduction_contact_difference(self, vertex, opposite):
        c = self._cmds
        raw = getattr(c, 'raw', c)
        point = raw.xform(self.scene_address(vertex), query=True, worldSpace=True, translation=True)
        c.xform('tempXform', worldSpace=True, translation=point)
        c.setAttr('tempXform.tx', lock=True)
        c.setAttr('tempXform.tz', lock=True)
        try:
            c.delete(c.geometryConstraint(opposite, 'tempXform'))
            projected = c.xform('tempXform', query=True, worldSpace=True, translation=True)
        finally:
            c.setAttr('tempXform.tx', lock=False)
            c.setAttr('tempXform.tz', lock=False)
        return point[1] - projected[1]

    def _lid_reduction_fit_vertices(self, curve, geometry):
        from .maya_face_fit_selection import MayaFaceFitSelectionMixin
        # This branch samples a single authored Fit curve, including repeated
        # nearest vertices and periodic CVs; no set/deduplication is allowed.
        return MayaFaceFitSelectionMixin.sample_face_fit_vertices(self, curve, geometry)

    def _lid_reduction_rename(self, side, upper_lower, indices, upper_outer):
        c = self._cmds
        mid, mid1, mid4 = indices
        for node in c.listRelatives('LidSetup', 'EyeLidJoints_M', allDescendents=True,
                                    type='transform') or []:
            name = leaf(node)
            joint = c.objectType(node) == 'joint'
            new_name = None
            if fnmatchcase(name, 'upperLidMain0*' + side):
                new_name = name.replace('upper', 'inner', 1).replace('0', 'Joint' if joint else '', 1)
            elif fnmatchcase(name, 'upperLidMain' + str(upper_outer) + '*' + side):
                new_name = name.replace('upper', 'outer', 1).replace(str(upper_outer), 'Joint' if joint else '', 1)
            elif fnmatchcase(name, upper_lower + 'LidMain' + str(mid) + '*' + side):
                # Preserve the two source substitutions in their exact order.
                new_name = name.replace(str(mid), '', 1)
                new_name = new_name.replace(str(mid), 'Joint' if joint else '', 1)
            elif fnmatchcase(name, upper_lower + 'LidMain' + str(mid1) + '*' + side):
                new_name = name.replace(str(mid1), '1', 1)
                new_name = new_name.replace(str(mid1), 'Joint' if joint else '', 1)
            elif fnmatchcase(name, upper_lower + 'LidMain' + str(mid4) + '*' + side):
                new_name = name.replace(str(mid4), '4', 1)
                new_name = new_name.replace(str(mid4), 'Joint' if joint else '', 1)
            if new_name is not None:
                c.rename(node, new_name)

    def reduce_original_eye_lid_joints(self, source, count):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, 'raw', c)
        self._transaction_changed = True
        before = self.capture_face_build_node_ids()
        for name in ('closestSampler', 'tempXform'):
            if c.objExists(name):
                c.delete(name)
        c.createNode('closestPointOnMesh', name='closestSampler')
        raw.connectAttr(self.scene_address(source['geometry']) + '.outMesh',
                        self.scene_address('closestSampler.inMesh'), force=True)
        c.createNode('transform', name='tempXform')
        skin = source['skin']
        c.select('eyeLidArea', replace=True)
        vertices = c.ls(selection=True, flatten=True) or []
        c.select(clear=True)
        hammer = tuple(vertex for vertex in vertices if len(self._reduction_skin_percent(
            skin, vertex, ignoreBelow=.001, query=True, transform=None) or []) > 2)
        self._original_prefix_lock_joints(0)
        indices = (0, 0, 0)
        nearest = (0, 0)
        fit_vertices = ()
        movement = 0.
        last_indices = {}
        upper_outer = 0
        refresh = source['modifier'] != 4
        with self._reduction_progress(5) as step:
            for side in ('_R', '_L'):
                for upper_lower, factor in (('upper', 1), ('lower', -1)):
                    step()
                    opposite = 'lower' if upper_lower == 'upper' else 'upper'
                    opposite_curve = opposite + 'LidMainCurve' + side
                    control = upper_lower + 'Lid' + side
                    joints = list(c.ls(upper_lower + 'LidMain*' + side, type='joint') or [])
                    authored = side == '_R' or source['non_sym']
                    if authored:
                        fit_vertices = self._lid_reduction_fit_vertices(
                            upper_lower + 'EyeLidMainCurve' + ('' if side == '_R' else 'Left'), source['geometry'])
                        c.select(clear=True)
                    if upper_lower == 'lower':
                        upper = c.ls('upperLidMain*' + side, type='joint') or []
                        joints = [upper[0], *joints, upper[-1]]
                    anchors = tuple(c.xform(upper_lower + 'Lid' + suffix + side,
                        query=True, worldSpace=True, translation=True) for suffix in ('', '1', '4'))
                    positions = tuple(c.xform(joint, query=True, worldSpace=True, translation=True) for joint in joints)
                    indices = original_lid_anchor_indices(positions, anchors, indices)
                    mid, mid1, mid4 = indices
                    outer = len(joints) - 1
                    # Source retains only the most recently computed upper /
                    # lower indices (the left side) for its later rename pass.
                    last_indices[upper_lower] = indices
                    if upper_lower == 'upper':
                        upper_outer = outer
                    if authored:
                        if refresh:
                            raw.refresh()
                        for _ in range(99):
                            c.move(0, -.05 * factor, 0, control, relative=True, objectSpace=True)
                            movement = c.getAttr(control + '.ty')
                            if original_lid_contact(upper_lower,
                                    self._lid_reduction_contact_difference(fit_vertices[mid], opposite_curve)):
                                break
                        if refresh:
                            raw.refresh()
                        c.setAttr(control + '.ty', 0)
                    if authored and count == 4:
                        c.setAttr(control + '.ty', movement)
                        for index in range(1, outer):
                            influenced = self._reduction_influence_vertices(joints[index], skin, 1.)
                            if not influenced or index == mid:
                                continue
                            endpoint = joints[0] if index < mid else joints[outer]
                            self._reduction_set_weight(skin, influenced, endpoint, 1.)
                            for iteration in range(101):
                                self._reduction_set_weight(skin, influenced, joints[mid], iteration * .01)
                                if original_lid_contact(upper_lower,
                                        self._lid_reduction_contact_difference(fit_vertices[index], opposite_curve)):
                                    break
                            if refresh:
                                raw.refresh()
                        c.setAttr(control + '.ty', 0)
                    if count == 8:
                        retained = ('upperLidMain0' + side,
                            upper_lower + 'LidMain' + str(mid) + side,
                            upper_lower + 'LidMain' + str(mid1) + side,
                            upper_lower + 'LidMain' + str(mid4) + side,
                            'upperLidMain' + str(upper_outer) + side)
                        controls = ('innerLid' + side, control, upper_lower + 'Lid1' + side,
                                    upper_lower + 'Lid4' + side, 'outerLid' + side)
                        for index in range(1, outer):
                            joint = upper_lower + 'LidMain' + str(index) + side
                            influenced = self._reduction_influence_vertices(joint, skin, 1.)
                            if not influenced:
                                continue
                            point = c.xform(joint, query=True, worldSpace=True, translation=True)
                            control_positions = tuple(c.xform(node, query=True, worldSpace=True,
                                                               translation=True) for node in controls)
                            first, second, value = original_lid_nearest_pair(point, control_positions, nearest)
                            nearest = (first, second)
                            self._reduction_set_weight(skin, influenced, retained[first], 1.)
                            self._reduction_set_weight(skin, influenced, retained[second], 1. - value)
                            if authored:
                                c.setAttr(control + '.ty', movement)
                                for _ in range(101):
                                    weight = self._reduction_skin_percent(skin, fit_vertices[index],
                                        transform=retained[1], ignoreBelow=.001, query=True, value=True) + .01
                                    if weight > 1.:
                                        break
                                    self._reduction_set_weight(skin, influenced, retained[1], weight)
                                    if original_lid_contact(upper_lower,
                                            self._lid_reduction_contact_difference(fit_vertices[index], opposite_curve)):
                                        break
                                    if refresh:
                                        raw.refresh()
                                c.setAttr(control + '.ty', 0)
                    for index in range(1, len(joints) - 1):
                        if index == mid or count == 8 and index in (mid1, mid4):
                            continue
                        c.delete(joints[index])
                        c.delete(upper_lower + 'LidMain' + str(index) + 'Aim' + side)
                    self._reduction_skin_percent(skin, source['geometry'], normalize=True)
                    for index in (range(1, 5) if count == 4 else range(2, 4)):
                        c.delete(upper_lower + 'Lid' + str(index) + 'Offset' + side)
        for side in ('_R', '_L'):
            for upper_lower in ('upper', 'lower'):
                self._lid_reduction_rename(side, upper_lower, last_indices[upper_lower], upper_outer)
        c.select(hammer, replace=True) if hammer else c.select(clear=True)
        if c.ls(selection=True):
            self._reduction_hammer()
        c.select(clear=True)
        if not source['non_sym']:
            raw.copySkinWeights(sourceSkin=self.scene_address(skin), destinationSkin=self.scene_address(skin),
                mirrorMode='YZ', mirrorInverse=True, surfaceAssociation='closestPoint', influenceAssociation='closestJoint')
        c.delete('closestSampler', 'tempXform')
        self._original_prefix_lock_joints(0)
        if count == 4:
            for side in ('_R', '_L'):
                for upper_lower in ('upper', 'lower'):
                    stem = upper_lower + 'LidReduceReWiredRot'
                    offset = c.createNode('transform', name=stem + 'Offset' + side,
                                          parent=upper_lower + 'Lid' + side)
                    c.parent(offset, upper_lower + 'LidMainAim' + side)
                    rotation = c.createNode('transform', name=stem + side, parent=stem + 'Offset' + side)
                    for axis in 'XYZ':
                        c.connectAttr(upper_lower + 'Lid' + side + '.rotate' + axis, rotation + '.rotate' + axis)
                    unoffset = c.createNode('transform', name=stem + 'UnOffset' + side,
                                            parent=upper_lower + 'LidMainAim' + side)
                    c.parent(unoffset, rotation)
                    c.parent(upper_lower + 'LidMainAimEnd' + side, unoffset)
        if source['lashes'] and '.' not in source['lashes']:
            for mesh in source['lashes'].split():
                raw.select(self.scene_address(source['geometry']), self.scene_address(mesh), replace=True)
                raw.copySkinWeights(noMirror=True, surfaceAssociation='closestPoint', influenceAssociation='closestJoint')
        if c.objExists('upperLidOuter_R'):
            self._original_prefix_lock_joints(1)
            raw.setAttr(self.scene_address(source['head']) + '.lockInfluenceWeights', 0)
            c.select(c.ls('*Lid*Outer*_*', type='joint') or [], source['geometry'], replace=True)
            from maya import mel
            mel.eval('RemoveInfluence;')
            self._reduction_skin_percent(skin, source['geometry'], normalize=True)
            self._original_prefix_lock_joints(0)
            c.delete(c.ls('*Lid*Outer*_*', type='joint') or [], c.ls('*Lid*OuterOffset_*') or [])
        from .maya_game_rebuild import _operation_boundary
        from .maya_driving_systems import MayaDrivingSystemsHost
        _operation_boundary(self, MayaDrivingSystemsHost).update_original_driving_pose_attributes()
        c.addAttr('FaceDeformationSystem', longName='asReduceEyeLidJoints', attributeType='long', defaultValue=count)
        self.register_face_module_nodes(before, 'FaceJointReductionSet', reuse=True, production_skins=(skin,))
        c.select(clear=True)
        return count

    def _reduction_set_weight(self, skin, vertices, joint, value):
        raw = getattr(self._cmds, 'raw', self._cmds)
        raw.skinPercent(self.scene_address(skin), self._reduction_scene_components(vertices),
                        transformValue=(self.scene_address(joint), value))
