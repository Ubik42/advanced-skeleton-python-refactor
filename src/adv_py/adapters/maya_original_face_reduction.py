"""Custom Face Joint Reduce: native selection, influence removal and hammer."""
from contextlib import contextmanager
from fnmatch import fnmatchcase

from adv_py.core.original_face_reduction import (
    custom_face_reduction, reduction_balance_threshold,
    original_lip_anchor_indices, original_lip_anchor_letter,
)
from .maya_face_original_build import MayaOriginalFaceBuildHost
from .maya_original_control_identity import leaf, source_main
from .maya_original_eye_lid_reduction import MayaOriginalEyeLidReductionMixin


class MayaOriginalFaceReductionHost(MayaOriginalEyeLidReductionMixin, MayaOriginalFaceBuildHost):
    def original_custom_face_reduction_counts(self, kind, every):
        # asCustomReduceCC queries children only; opening the dialog must not
        # invoke apply preflight or change selection, joints, or the scene.
        if kind not in ('EyeLid', 'Lip') or type(every) is not int or every not in (2, 3, 4, 5):
            raise ValueError('未知面部缩减对象或保留间隔')
        parent = 'EyeLidJoints_M' if kind == 'EyeLid' else 'LipJoints_M'
        count = len(self._cmds.listRelatives(parent, children=True, type='joint') or [])
        return count, int(count / every)

    def _reduction_require_version(self):
        c = self._cmds
        if c.objExists('FaceGroup.version') and float(c.getAttr('FaceGroup.version')) < 6.:
            raise ValueError('此功能要求 Face 绑定版本至少为 6.000，请先按原版重建 Face')

    def capture_original_custom_face_reduction(self, kind, every):
        c = self._cmds
        self._reduction_require_version()
        if kind not in ('EyeLid', 'Lip'):
            raise ValueError('未知面部关节缩减对象')
        marker = 'asReduceEyeLidJoints' if kind == 'EyeLid' else 'asReduceLipJoints'
        if c.objExists('FaceDeformationSystem.' + marker):
            raise ValueError('该面部关节链已经执行过缩减')
        self._unique('FaceJoint_M', 'joint')
        parent = 'EyeLidJoints_M' if kind == 'EyeLid' else 'LipJoints_M'
        count = len(c.listRelatives(parent, children=True, type='joint') or [])
        joints = tuple(leaf(joint) for joint in c.listRelatives(
            'FaceJoint_M', allDescendents=True, type='joint') or [])
        return custom_face_reduction(kind, every, joints, c.objExists, count)

    def _reduction_face_input(self):
        from adv_py.application.face_pre import FacePreRole
        c = self._cmds
        meshes = self.read_face_objects(FacePreRole.FACE)
        if len(meshes) != 1:
            raise ValueError('面部关节缩减需要唯一主网格')
        geometry = meshes[0]
        fit = self._fit(required=True)
        head = c.getAttr(fit + '.HeadJoint')
        skin = c.getAttr(fit + '.SkinCluster') if c.objExists(fit + '.SkinCluster') else ''
        if not skin:
            skin = self.original_face_production_skin(geometry, head)
        return dict(geometry=geometry, skin=skin, head=head)

    def capture_original_lip_reduction(self):
        c = self._cmds
        if c.objExists('FaceDeformationSystem.asReduceLipJoints'):
            raise ValueError('唇部关节已经执行过缩减')
        if c.objExists('asFaceBS'):
            raise ValueError('关节缩减只用于原版 Joints 面部绑定')
        self._reduction_require_version()
        self._unique('LipJoints_M', 'joint')
        return self._reduction_face_input()

    def _reduction_influence_vertices(self, joint, skin, threshold):
        """asInfluenceVerts, source 76542–76567, preserving actual selection."""
        c = self._cmds
        selected = c.ls(selection=True) or []
        vertices = []
        try:
            c.select(clear=True)
            self._reduction_skin_edit(skin, selectInfluenceVerts=joint)
            for vertex in c.ls(selection=True, flatten=True) or []:
                if '.' not in vertex:
                    continue
                influences = self._reduction_skin_percent(skin, vertex,
                    ignoreBelow=threshold, query=True, transform=None) or []
                for influence in influences:
                    if self.scene_address(influence) == self.scene_address(joint):
                        vertices.append(vertex)
        finally:
            c.select(selected, replace=True) if selected else c.select(clear=True)
        return tuple(vertices)

    def reduce_original_lip_joints(self, source, count=14):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, 'raw', c)
        self._transaction_changed = True
        before = self.capture_face_build_node_ids()
        holder = c.createNode('transform', name='LipJointReducedNoLongerDeformJoints', parent='LipJoints_M')
        holder = c.parent(holder, 'LipSetup')[0]
        self.constrain_original_face('LipJoints_M', holder, force_matrix=False)
        retained, removed, hammer_in, hammer_out = [], [], [], []
        indices = (0, 0, 0)
        skin = source['skin']
        with self._reduction_progress(5) as step:
            for side in ('_R', '_L'):
                for upper_lower in ('upper', 'lower'):
                    step()
                    # Source asks Maya to filter its selected native child list.
                    c.select(c.listRelatives('LipJoints_M', children=True, type='joint') or [], replace=True)
                    joints = c.ls(upper_lower + '*' + side, selection=True) or []
                    c.select(joints, replace=True)
                    positions = tuple(c.xform(joint, query=True, worldSpace=True, translation=True) for joint in joints)
                    anchors = tuple(c.xform(upper_lower + 'Lip' + letter + side,
                        query=True, worldSpace=True, translation=True) for letter in 'ABC')
                    indices = original_lip_anchor_indices(positions, anchors, indices)
                    branch_removed = [upper_lower + 'LipJoint0_M'] if side == '_R' else []
                    for index, joint in enumerate(joints):
                        letter = original_lip_anchor_letter(index, indices)
                        if letter is not None:
                            name = upper_lower + 'Lip' + letter + 'Joint' + side
                            c.rename(joint, name)
                            retained.append(name)
                        else:
                            branch_removed.append(joint)
                    # inJoints is deliberately cumulative across all branches.
                    for joint in retained:
                        hammer_in.extend(self._reduction_influence_vertices(joint, skin, 1.))
                    for joint in branch_removed:
                        hammer_out.extend(self._reduction_influence_vertices(joint, skin, 1.))
                        self._reduction_skin_edit(skin, removeInfluence=joint)
                        c.parent(joint, holder)
                        removed.append(joint)
        for vertices in (hammer_out, hammer_in):
            c.select(vertices, replace=True) if vertices else c.select(clear=True)
            if c.ls(selection=True):
                self._reduction_hammer()
        c.select('lipFalloffArea', replace=True)
        if c.ls(selection=True):
            self._reduction_hammer()
        self._original_prefix_lock_joints(0)
        # Preserve the original all-directions connection query and forward
        # history order when updating mustache/other influenced geometry.
        for node in c.listConnections('upperLipJoint0_M.worldMatrix') or []:
            if self.scene_address(node) == self.scene_address(skin):
                continue
            for history in c.listHistory(node, interestLevel=2, future=True) or []:
                if c.objectType(history) == 'mesh':
                    raw.select(self.scene_address(source['geometry']),
                               self.scene_address(history), replace=True)
                    raw.copySkinWeights(noMirror=True, surfaceAssociation='closestPoint',
                                        influenceAssociation='closestJoint')
        constraints = c.listRelatives('FaceJoint_M', allDescendents=True, type='constraint') or []
        if constraints:
            c.parent(constraints, 'DeformJointConstraints')
        c.addAttr('FaceDeformationSystem', longName='asReduceLipJoints',
                  attributeType='long', defaultValue=count)
        self.register_face_module_nodes(before, 'FaceJointReductionSet', reuse=True,
                                        production_skins=(skin,))
        c.select(clear=True)
        return dict(kept=tuple(retained), removed=tuple(removed), reported_count=count)

    @contextmanager
    def _reduction_progress(self, maximum):
        raw = getattr(self._cmds, 'raw', self._cmds)
        progress = None
        if not raw.about(batch=True):
            from maya import mel
            progress = mel.eval('$advPyProgress = $gMainProgressBar')
            raw.progressBar(progress, edit=True, status='Reducing number of joints',
                            beginProgress=True, isInterruptable=True,
                            minValue=0, maxValue=max(1, maximum))
        def step():
            if progress:
                raw.progressBar(progress, edit=True, step=1)
        try:
            yield step
        finally:
            if progress:
                raw.progressBar(progress, edit=True, endProgress=True)

    def _reduction_skin_percent(self, skin, components, **flags):
        # The original traverses all Skin outputs of these joints, including
        # production models outside the character's namespace. Their explicit
        # Skin and component addresses are retained at the host boundary.
        raw = getattr(self._cmds, 'raw', self._cmds)
        if 'transform' in flags and isinstance(flags['transform'], str):
            flags['transform'] = self.scene_address(flags['transform'])
        return raw.skinPercent(self.scene_address(skin),
                               self._reduction_scene_components(components), **flags)

    def _reduction_scene_components(self, value):
        if isinstance(value, (list, tuple)):
            return type(value)(self._reduction_scene_components(item) for item in value)
        return self.scene_address(value)

    def _reduction_skin_edit(self, skin, **flags):
        raw = getattr(self._cmds, 'raw', self._cmds)
        for flag in ('selectInfluenceVerts', 'removeInfluence'):
            if flag in flags:
                flags[flag] = self.scene_address(flags[flag])
        return raw.skinCluster(self.scene_address(skin), edit=True, **flags)

    @staticmethod
    def _reduction_hammer():
        from maya import mel
        mel.eval('weightHammerVerts;')

    def apply_original_custom_face_reduction(self, plan, *, preview=False):
        self._require_transaction()
        c = self._cmds
        self._transaction_changed = True
        if c.objExists('asCustomReducePreview'):
            c.delete('asCustomReducePreview')
        if preview:
            main = source_main(self)
            if c.objExists(main + '.jointVis') and not c.getAttr(main + '.jointVis'):
                c.setAttr(main + '.jointVis', 1)
        c.select(plan.kept, replace=True) if plan.kept else c.select(clear=True)
        if preview:
            return plan
        if not plan.removed:
            raise RuntimeError('原版缩减没有找到可移除的关节')
        before = self.capture_face_build_node_ids()
        holder = c.createNode('transform', name=plan.holder, parent=plan.parent)
        holder = c.parent(holder, plan.setup)[0]
        if plan.kind == 'Lip':
            # Native flags are empty, so preserve its OPM/native-constraint
            # branch instead of forcing the Face graph's matrix-only shortcut.
            self.constrain_original_face(plan.parent, holder, force_matrix=False)
        skins = list(c.listConnections(plan.removed[0] + '.worldMatrix', source=False,
                                       destination=True, type='skinCluster') or [])
        index = 0
        while index < len(skins):
            if fnmatchcase(skins[index], '*LipRibbonCurveSC'):
                skins = [skin for skin in skins if skin != skins[index]]
            index += 1
        sets = []
        for index, skin in enumerate(skins):
            names = ('asCustomReduceVtxSet' + str(index), 'asCustomReduceBalanceVtxSet' + str(index))
            for name in names:
                if c.objExists(name):
                    c.delete(name)
                c.sets(empty=True, name=name)
            sets.append(names)
        with self._reduction_progress(len(plan.removed) * 2) as step:
            for joint in plan.removed:
                step()
                for index, skin in enumerate(skins):
                    c.select(clear=True)
                    self._reduction_skin_edit(skin, selectInfluenceVerts=joint)
                    c.select(joint, deselect=True)
                    objects = c.ls(selection=True, objectsOnly=True) or []
                    if objects:
                        c.select(objects, deselect=True)
                    selected = c.ls(selection=True) or []
                    if selected:
                        c.sets(selected, add=sets[index][0])
            c.select(clear=True)
            for ordinary, balance in sets:
                c.select(ordinary, add=True)
            vertices = c.ls(selection=True, flatten=True) or []
            for names in sets:
                for name in names:
                    c.sets(clear=name)
            for vertex in vertices:
                for index, skin in enumerate(skins):
                    c.select(vertex, replace=True)
                    influences = self._reduction_skin_percent(skin, vertex,
                        ignoreBelow=.001, query=True, transform=None) or []
                    influences = [joint for joint in influences if leaf(joint) not in ('LipJoint_R', 'LipJoint_L')]
                    if influences:
                        c.sets(c.ls(selection=True) or [], add=sets[index][len(influences) == 1])
            for joint in plan.removed:
                step()
                for skin in skins:
                    self._reduction_skin_edit(skin, removeInfluence=joint)
            moved = c.parent(plan.removed, holder) or []
            renamed = [c.rename(joint, 'LJRNLDJ' + leaf(joint)) for joint in moved]
            for index, skin in enumerate(skins):
                c.select(sets[index][1], replace=True)
                if not c.ls(selection=True):
                    continue
                self._reduction_hammer()
                for vertex in c.ls(selection=True, flatten=True) or []:
                    weights = self._reduction_skin_percent(skin, vertex,
                        ignoreBelow=.001, query=True, value=True) or []
                    threshold = reduction_balance_threshold(weights)
                    if threshold is not None:
                        self._reduction_skin_percent(skin, vertex, pruneWeights=threshold)
            for ordinary, _ in sets:
                c.select(ordinary, replace=True)
                if c.ls(selection=True):
                    self._reduction_hammer()
            for names in sets:
                c.delete(names)
        # Source compares the renamed removal array against original names.
        # Keep its first-gap termination rather than silently compressing all
        # remaining names through a different renumbering algorithm.
        main = 'Main' if plan.kind == 'EyeLid' else 'Joint'
        token = 'Lid' if plan.kind == 'EyeLid' else 'Lip'
        for side in ('_R', '_L'):
            for upper_lower in ('upper', 'lower'):
                number = 1
                for index in range(1, 999):
                    joint = upper_lower + token + main + str(index) + side
                    if joint not in renamed and not c.objExists(joint):
                        break
                    if joint not in renamed:
                        c.rename(joint, upper_lower + token + main + str(number) + side)
                        number += 1
        c.addAttr('FaceDeformationSystem', longName=plan.marker,
                  attributeType='long', defaultValue=plan.reported_count)
        self.register_face_module_nodes(before, 'FaceJointReductionSet', reuse=True,
                                        production_skins=tuple(skins))
        c.select(clear=True)
        return plan
