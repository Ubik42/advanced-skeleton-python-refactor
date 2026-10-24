"""Reapply existing original Face Fitting after a model edit."""
from adv_py.application.face_pre import CreateFaceEyeLidFit, EyeLidLayer, OptionalEyeLidLayer
from adv_py.core.original_face_fitting_update import (
    ORIGINAL_FACE_FITTING_UPDATE_ROWS, ORIGINAL_FACE_FITTING_MANUAL_TRANSFORMS,
    original_face_fit_row,
)
from .maya_face_fit_markers import MayaFaceFitMarkersHost


class MayaOriginalFaceFittingUpdateHost(MayaFaceFitMarkersHost):
    def confirm_original_face_fitting_update(self):
        raw = getattr(self._cmds, 'raw', self._cmds)
        return raw.confirmDialog(title='Confirm',
            message='For use when Model has changed.\n\nRe-apply all FaceFitting ?',
            button=['Continue', 'Cancel'], defaultButton='Cancel') == 'Continue'

    def _face_fitting_update_host(self, host_class):
        joined = host_class.__new__(host_class)
        joined.__dict__ = self.__dict__
        return joined

    def _recreate_original_face_fit_row(self, section, part):
        if section == 'EyeBall':
            c = self._cmds
            fit = self._fit(required=True)
            side = self.active_face_side()
            attribute = 'LeftEye' if side.value == 'Left' else 'RightEye'
            return self.create_original_eye_ball_fit(c.getAttr(fit + '.' + attribute),
                c.getAttr(fit + '.HeadJoint'), side)
        if section in ('EyeLid', 'EyeLidMain2'):
            layer = OptionalEyeLidLayer.MAIN2 if section == 'EyeLidMain2' else EyeLidLayer(part)
            return CreateFaceEyeLidFit(self).execute(layer)
        if section == 'Lip':
            from .maya_face_lip_fit import MayaFaceLipFitHost
            from adv_py.core.face_lip_fit import plan_lip_fit
            joined = self._face_fitting_update_host(MayaFaceLipFitHost)
            plan = plan_lip_fit(joined.capture_lip_fit_input(part))
            joined.preflight_lip_fit(plan)
            return joined.create_lip_fit(plan)
        if section == 'Tongue':
            from .maya_face_tongue import MayaFaceTongueHost
            return self._face_fitting_update_host(MayaFaceTongueHost).create_tongue_fit()
        if section == 'UpMidLo':
            return self.create_face_up_mid_lo_fit()
        if section == 'ForeHead':
            return self.create_original_face_forehead_fit()
        if section in ('Pupil', 'Iris'):
            return self.create_original_eye_loop_fit(section)
        return self.create_face_fit_marker(section)

    def update_original_face_fitting(self):
        self._require_transaction()
        c = self._cmds
        self._transaction_changed = True
        if c.objExists('FaceFitJawCurves'):
            c.delete('FaceFitJawCurves')
        matrices = []
        for node in ORIGINAL_FACE_FITTING_MANUAL_TRANSFORMS:
            # FitEyeBall is mandatory in the original, including its native error.
            if node == 'FitEyeBall' or c.objExists(node):
                matrices.append((node, c.xform(node, query=True, objectSpace=True, matrix=True)))
        updated = []
        for label in ORIGINAL_FACE_FITTING_UPDATE_ROWS:
            holder = 'FaceFit' + label
            # Native update tests the unsuffixed holder even when Left is active.
            if not c.objExists(holder):
                continue
            section, part = original_face_fit_row(label)
            self.reselect_original_face_fit(section, part)
            c.refresh()
            c.delete(holder)
            self._recreate_original_face_fit_row(section, part)
            updated.append(label)
        for node, matrix in matrices:
            c.xform(node, matrix=matrix)
        return tuple(updated)
