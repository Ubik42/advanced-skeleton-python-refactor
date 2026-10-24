"""Python port of asBuildFitEyeBall, ADV 6.925 MEL 46772–46930."""
from contextlib import nullcontext
from .maya_face_body_roles import face_body_main, face_body_fk_offset, face_body_aim_root

from adv_py.application.face_pre import FaceSide
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_original_skin_history import remove_unused_selected_skin_influences


def remove_original_skin_influence(commands, joint, skin):
    """asRemoveInfluence: matrix members, then removal, then empty-skin deletion."""
    if not commands.objExists(skin):
        return
    influences = commands.listConnections(skin + '.matrix', source=True,
                                           destination=False) or []
    joint_ids = set(commands.ls(joint, uuid=True) or [])
    if not any(joint_ids & set(commands.ls(node, uuid=True) or []) for node in influences):
        return
    commands.skinCluster(skin, edit=True, removeInfluence=joint)
    if len(influences) == 1:
        commands.delete(skin)


class MayaOriginalEyeBallFitMixin:
    def _remove_original_body_eyes_for_face(self, head_joint):
        c = self._cmds
        raw = getattr(c, 'raw', c)
        fit = self._fit(required=True)
        geometry = []
        for attribute in ('LeftEye', 'RightEye'):
            if c.objExists(fit + '.' + attribute):
                geometry.extend(self.scene_address(token) for token in
                                (c.getAttr(fit + '.' + attribute) or '').split())
        raw.select(geometry, replace=True) if geometry else raw.select(clear=True)
        selected = raw.ls(selection=True) or []
        if selected and '.' not in selected[0]:
            remove_unused_selected_skin_influences(raw)
        for skin in raw.ls(type='skinCluster') or []:
            for joint in ('EyeEnd_R', 'EyeEnd_L', 'EyeEnd_M', 'JawEnd_M'):
                if c.objExists(joint):
                    remove_original_skin_influence(raw, self.scene_address(joint), skin)
            if not raw.objExists(skin):
                continue
            influences = raw.listConnections(skin + '.matrix') or []
            if len(influences) == 1 and influences[0].rsplit('|', 1)[-1].rsplit(':', 1)[-1].startswith('Eye_'):
                raw.skinCluster(skin, edit=True, addInfluence=self.scene_address(head_joint),
                                lockWeights=False, weight=1)
            for joint in ('Eye_R', 'Eye_L', 'Eye_M'):
                if c.objExists(joint):
                    remove_original_skin_influence(raw, self.scene_address(joint), skin)
        position = None
        for joint in ('Eye_R', 'Eye_M'):
            if c.objExists(joint):
                position = c.xform(joint, query=True, worldSpace=True, translation=True)
        offsets = tuple(face_body_fk_offset(self, 'Eye_' + side) for side in ('R', 'L', 'M'))
        aim_root = face_body_aim_root(self, 'Eye')
        for node in (*offsets,
                     'FKAimEye_R', 'FKAimEye_L', 'FKAimEye_M',
                     'Eye_R', 'Eye_L', 'Eye_M', aim_root, 'Eye'):
            if c.objExists(node):
                c.delete(node)
        from .maya_face_body_jaw import MayaFaceBodyJawMixin
        MayaFaceBodyJawMixin._prune_original_body_pose_after_jaw(self)
        return position

    def _original_eye_fit_geometry(self, tokens):
        """Keep source first-object/component extraction and temporary names."""
        c = self._cmds
        raw = getattr(c, 'raw', c)
        objects = [token for token in tokens if '.' not in token]
        extracted = None
        if not objects and tokens and '.' in tokens[0]:
            source = tokens[0].split('.', 1)[0]
            raw.select(raw.ls(source, objectsOnly=True), replace=True)
            duplicate = raw.duplicate()[0]
            extracted = c.rename(duplicate, 'asDuplicatedEye')
            actual = self.scene_address(extracted)
            cast = [token.replace(source, actual, 1) for token in tokens]
            raw.select(cast, replace=True)
            selected = raw.ls(selection=True) or []
            owner = (raw.ls(selection=True, objectsOnly=True) or [actual])[0]
            kind = next((kind for kind in ('vtx', 'f', 'e')
                         if '.' + kind in selected[0]), None)
            if kind is None:
                raise FitSkeletonValidationError('Eye 组件类型无效')
            raw.select(owner + '.' + kind + '[0:999999]', replace=True)
            raw.select(selected, deselect=True)
            raw.delete()
            objects = [actual]
            tokens = [actual]
        if not objects:
            return None, None, extracted
        # $eyeVis is initially zero in MEL, so this edit is intentional.
        raw.setAttr(tokens[0] + '.v', 1)
        temporary = c.duplicate(objects[0], name='tempEye')[0]
        try:
            if c.listRelatives(temporary, parent=True):
                temporary = c.parent(temporary, world=True)[0]
            visible = c.getAttr(temporary + '.v')
            c.xform(temporary, centerPivots=True)
            if not visible:
                c.setAttr(temporary + '.v', 0)
            position = c.xform(temporary, query=True, worldSpace=True, pivots=True)
            bounds = c.xform(temporary, query=True, worldSpace=True, boundingBox=True)
        finally:
            if c.objExists(temporary):
                c.delete(temporary)
        return position, bounds, extracted

    def create_original_eye_ball_fit(self, eye_text, head_joint, side=FaceSide.RIGHT):
        c = self._cmds
        raw = getattr(c, 'raw', c)
        fit = self._fit(required=True)
        suffix = 'Left' if side is FaceSide.LEFT else ''
        if not eye_text:
            raise FitSkeletonValidationError('No Eye Geometry choosen')
        if c.objExists('FitEyeBall' + suffix):
            raise FitSkeletonValidationError('FitEyeBall' + suffix + ' already exists')
        had_body_eye = c.objExists('Eye_R') or c.objExists('Eye_M')
        if had_body_eye and not c.objExists('headTopology') and not c.objExists('asBatch'):
            if raw.confirmDialog(title='Confirm', message='This will replace the Eyes from the Body-setup',
                    button=['OK', 'Cancel'], defaultButton='OK', dismissString='Cancel') != 'OK':
                return None
        with (nullcontext() if self._transaction_active else self.transaction('Build FitEyeBall')):
            from .maya_face_base import MayaFaceBaseMixin
            from .maya_original_control_identity import registration
            before = registration(self) if had_body_eye else None
            self._transaction_changed = True
            body_position = self._remove_original_body_eyes_for_face(head_joint) if had_body_eye else None
            MayaFaceBaseMixin.ensure_face_fit_shaders(self)
            main = face_body_main(self)
            height = float(c.getAttr(main + '.height')) if c.objExists(main) else 10.0
            locator = 'FitEyeBall' + suffix
            holder = 'FaceFitEyeBall' + suffix
            sphere = 'FitEyeSphere' + suffix
            c.spaceLocator(name=locator)
            c.addAttr(locator, longName='version', attributeType='double')
            c.setAttr(locator + '.version', 6.925, lock=True)
            c.setAttr(locator + '.rotateOrder', 2)
            c.setAttr(locator + '.rz', lock=True)
            c.setAttr(locator + 'Shape.localScale', 1.5, 1.5, 1.5, type='float3')
            c.createNode('transform', name=holder, parent=fit)
            c.parent(locator, holder)
            c.polySphere(name=sphere, radius=.5, subdivisionsX=8, subdivisionsY=8,
                         axis=(0, 1, 0), createUVs=2, constructionHistory=False)
            c.setAttr(sphere + '.overrideEnabled', 1)
            c.setAttr(sphere + '.overrideDisplayType', 2)
            c.parent(sphere, locator)
            c.sets(sphere, edit=True, forceElement='asWhiteSG')
            c.sets(sphere + '.f[56:63]', edit=True, forceElement='asBlackSG')
            c.setAttr(sphere + '.r', 90, 0, 0, type='float3')
            c.setAttr(locator + '.s', *(height * .025,) * 3, type='float3')
            if had_body_eye:
                c.xform(locator, worldSpace=True, translation=body_position)
            else:
                position = c.xform(head_joint, query=True, worldSpace=True, translation=True)
                c.xform(locator, worldSpace=True, translation=position)
                c.setAttr(locator + '.t', position[1] / -50., position[1] / 15.,
                          position[1] / 15., type='float3')
            tokens = [self.scene_address(token) for token in eye_text.split()]
            position, bounds, extracted = self._original_eye_fit_geometry(tokens)
            if position is not None and position[1] > 0:
                c.parent(locator, world=True)
                if not had_body_eye:
                    c.xform(locator, worldSpace=True, translation=position[:3])
                c.xform(locator, objectSpace=True, scale=(bounds[4] - bounds[1],) * 3)
                c.parent(locator, holder)
            if extracted and c.objExists(extracted):
                c.delete(extracted)
            for channel in ('translate', 'rotate', 'scale'):
                for axis in 'XYZ':
                    c.setAttr(fit + '.' + channel + axis, lock=True, keyable=False)
            if before is not None:
                from .maya_original_export_preparation import MayaOriginalExportPreparationHost
                joined = MayaOriginalExportPreparationHost.__new__(MayaOriginalExportPreparationHost)
                joined.__dict__ = self.__dict__
                joined._remember_export_preparation(before)
            c.select(locator, replace=True)
            return (c.ls(locator, long=True) or [locator])[0]
