"""Python scene port of asNameMatcherAutoFaceFitting, MEL 51099–51738."""
from adv_py.application.face_pre import (
    CreateFaceEyeLidFit, EyeLidLayer, OptionalEyeLidLayer, FacePreRole,
    RecordFacePreInput,
)
from adv_py.core.original_auto_face_fitting import (
    ORIGINAL_AUTO_FACE_PROFILES, ORIGINAL_AUTO_FACE_EXTRAS,
    detect_original_auto_face_profile, original_auto_face_input,
    original_auto_face_tongue_points,
)
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_fit_markers import MayaFaceFitMarkersHost
from .maya_original_skin_history import related_skin_cluster


class MayaOriginalAutoFaceFittingHost(MayaFaceFitMarkersHost):
    def _auto_face_host(self, host_class):
        # Share the existing transaction, namespace adapter and ownership
        # state rather than opening an independent host/undo chunk per row.
        joined = host_class.__new__(host_class)
        joined.__dict__ = self.__dict__
        return joined

    @property
    def _auto_face_raw(self):
        return getattr(self._cmds, 'raw', self._cmds)

    def detect_original_auto_face_profile(self):
        raw = self._auto_face_raw
        counts = {}
        for profile in ORIGINAL_AUTO_FACE_PROFILES:
            if profile.geometry not in counts and raw.objExists(profile.geometry):
                counts[profile.geometry] = int(raw.polyEvaluate(profile.geometry, vertex=True))
        return detect_original_auto_face_profile(counts)

    def confirm_original_auto_face_fitting(self, profile):
        return self._auto_face_raw.confirmDialog(title='Auto Face Setup ?',
            message=profile.title+' .. detected.\n\nApply FaceFitting?',
            button=['Yes', 'No'], defaultButton='Yes', dismissString='No') == 'Yes'

    def _auto_face_select(self, selection):
        raw = self._auto_face_raw
        raw.select(selection, replace=True) if selection else raw.select(clear=True)

    def _record_auto_face_part(self, attribute, *, allow_empty=False):
        from .maya_face_jaw import MayaFaceJawHost
        return self._auto_face_host(MayaFaceJawHost).record_original_face_parts(
            attribute, allow_empty=allow_empty, new_skin_head_joint='Head_M')

    def _remove_original_metahuman_face(self):
        """Keep native all-joint locks and catchQuiet only around skinPercent."""
        raw = self._auto_face_raw
        root = 'DHIhead:FACIAL_C_FacialRoot'
        if not raw.objExists(root):
            return True
        if raw.confirmDialog(title='Face ?',
                message='MetaHuman FaceRig detected.\nThis must be deleted before adding Face-Fitting',
                button=['OK', 'Cancel']) != 'OK':
            return False
        self._transaction_changed = True
        joints = tuple(raw.ls(type='joint') or [])
        for joint in joints:
            if raw.attributeQuery('lockInfluenceWeights', node=joint, exists=True):
                raw.setAttr(joint+'.lockInfluenceWeights', 1)
        raw.setAttr('DHIhead:head.liw', 0)
        for joint in raw.listRelatives(root, allDescendents=True, type='joint') or []:
            if raw.attributeQuery('liw', node=joint, exists=True):
                raw.setAttr(joint+'.liw', 0)
        for mesh in raw.ls(noIntermediate=True, type='mesh') or []:
            skin = related_skin_cluster(mesh)
            if not skin:
                continue
            if 'DHIhead:head' not in (raw.listConnections(skin, type='joint') or []):
                raw.skinCluster(skin, edit=True, lockWeights=False,
                                weight=0, addInfluence='DHIhead:head')
            try:
                raw.skinPercent(skin, mesh, transformValue=('DHIhead:head', 1))
            except RuntimeError:
                pass  # Only this native command is wrapped in catchQuiet.
        for joint in joints:
            if raw.attributeQuery('lockInfluenceWeights', node=joint, exists=True):
                raw.setAttr(joint+'.lockInfluenceWeights', 0)
        raw.delete(root)
        if raw.objExists('headRig_grp'):
            raw.delete('headRig_grp')
        return True

    def prepare_original_auto_face_inputs(self, profile):
        self._require_transaction()
        raw = self._auto_face_raw
        self._auto_face_select(original_auto_face_input(profile, 'Mask'))
        if not self.prepare_original_face_mask():
            return False
        mesh, faces, bounds = self.selected_mask()
        self.store_face_mask(mesh, faces, bounds)
        self._auto_face_select((profile.geometry,))
        RecordFacePreInput(self).objects(FacePreRole.FACE, None)
        self._auto_face_select((profile.head_joint,) if profile.head_joint else ())
        if raw.ls(selection=True):
            self.record_original_face_head_joint()
        if profile.code == 'MH' and not self._remove_original_metahuman_face():
            return False
        self._auto_face_select(tuple(node for node in profile.all_head if raw.objExists(node)))
        RecordFacePreInput(self).objects(FacePreRole.ALL_HEAD, 'Head_M')
        for side, eye in (('Right', profile.right_eye), ('Left', profile.left_eye)):
            self._auto_face_select(eye)
            self.record_original_face_eye_input(side)
        for attribute in ('UpperTeeth', 'LowerTeeth', 'Tongue'):
            selection = ((profile.tongue_object,) if attribute == 'Tongue' and profile.tongue_object
                         else original_auto_face_input(profile, attribute))
            self._auto_face_select(selection)
            self._record_auto_face_part(attribute)
        self._auto_face_select(())
        for node in ('Eyebrows', 'Brows'):
            if raw.objExists(node):
                self._auto_face_select((node,))  # Native Brows replaces Eyebrows.
        if raw.ls(selection=True):
            self._record_auto_face_part('Eyebrow')
        if profile.code == 'CC4':
            self._auto_face_select((profile.geometry+'.f[13446:14045]',))
        elif profile.code == 'MH':
            self._auto_face_select(('eyelashes_lod0_mesh',))
        elif profile.code == 'CC5':
            self._auto_face_select(('Eyelash_Low', 'Eyelash_Up'))
        # GNM inherits the preceding eyebrow selection, including empty.
        self._record_auto_face_part('Eyelash', allow_empty=True)
        self._auto_face_select(tuple(node for node in ORIGINAL_AUTO_FACE_EXTRAS if raw.objExists(node)))
        self._record_auto_face_part('Extras', allow_empty=True)
        options = self.read_original_face_options()
        options.update(getattr(self, '_auto_face_options', {}))
        options['NonSym'] = True
        self.write_original_face_options(options, complete=True)
        c = self._cmds
        fit = self._fit(required=True)
        if not c.objExists(fit+'.NonSym'):
            c.addAttr(fit, longName='NonSym', attributeType='bool')
        if not c.objExists(fit+'.NonSymSide'):
            c.addAttr(fit, longName='NonSymSide', dataType='string')
        c.setAttr(fit+'.NonSym', True)
        self._transaction_changed = True
        return True

    def set_original_auto_face_side(self, side):
        if side not in ('Right', 'Left'):
            raise ValueError('原版 AutoFit 侧别无效')
        return self.switch_original_face_fit_side(1 if side == 'Right' else 0)

    def _create_auto_face_step(self, step):
        section, part = step.section, step.part
        if section == 'EyeBall':
            c = self._cmds
            fit = self._fit(required=True)
            side = self.active_face_side()
            attribute = side.value+'Eye'
            return self.create_original_eye_ball_fit(c.getAttr(fit+'.'+attribute),
                c.getAttr(fit+'.HeadJoint'), side)
        if section == 'EyeLid':
            layer = OptionalEyeLidLayer.MAIN2 if part == 'Main2' else EyeLidLayer(part)
            return CreateFaceEyeLidFit(self).execute(layer, native_main2_part=part == 'Main2')
        if section == 'Lip':
            from .maya_face_lip_fit import MayaFaceLipFitHost
            from adv_py.core.face_lip_fit import plan_lip_fit
            joined = self._auto_face_host(MayaFaceLipFitHost)
            plan = plan_lip_fit(joined.capture_lip_fit_input(part))
            joined.preflight_lip_fit(plan)
            return joined.create_lip_fit(plan)
        if section == 'ForeHead':
            return self.create_original_face_forehead_fit()
        if section in ('Pupil', 'Iris'):
            return self.create_original_eye_loop_fit(section)
        return self.create_face_fit_marker(section, shading_group=step.shading_group)

    def create_original_auto_face_step(self, step):
        self._require_transaction()
        c = self._cmds
        batch = None
        if step.batch:
            if self.find_name_collisions('asBatch'):
                raise FitSkeletonValidationError('asBatch 名称已被场景节点占用')
            self._transaction_changed = True
            batch = c.createNode('transform', name='asBatch')
        try:
            # createNode selects asBatch. Native Jaw selects its component
            # after making this sentinel, not before it.
            if step.section != 'EyeBall':
                self._auto_face_select(step.selection)
            return self._create_auto_face_step(step)
        finally:
            if batch is not None and c.objExists(batch):
                c.delete(batch)

    def finish_original_auto_face_fitting(self, profile):
        self._require_transaction()
        self.switch_original_face_fit_side(1)
        self.show_original_face_fit_both_sides()
        self._auto_face_select(())
        from .maya_face_tongue import MayaFaceTongueHost
        self._auto_face_host(MayaFaceTongueHost).create_tongue_fit()
        for index, (component, offset) in enumerate(original_auto_face_tongue_points(profile)):
            position = self._auto_face_raw.xform(component, query=True, worldSpace=True, translation=True)
            self._cmds.xform('Tongue'+str(index), worldSpace=True,
                            translation=(0, position[1]+offset, position[2]))

    def build_original_auto_face_if_confirmed(self):
        raw = self._auto_face_raw
        raw.refresh()
        if raw.confirmDialog(title='Build ?', message='Proceed to Build Face ?',
                button=['Yes', 'No'], defaultButton='Yes', dismissString='No') != 'Yes':
            return None
        from .maya_face_original_build import MayaOriginalFaceBuildHost
        from adv_py.application.face_original_build import BuildOriginalFace
        return BuildOriginalFace(self._auto_face_host(MayaOriginalFaceBuildHost)).apply()
