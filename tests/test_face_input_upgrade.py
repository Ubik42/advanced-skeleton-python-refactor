"""Old Fit conversion commits before its native stop prevents the next action."""
import unittest
from contextlib import contextmanager
from types import SimpleNamespace as NS

from adv_py.application.face_input_upgrade import check_original_face_input_upgrade
from adv_py.application.face_original_build import UpgradeOriginalFaceFit
from adv_py.application.face_pre import RecordFacePreInput, FacePreRole
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.adapters.maya_face_fit_upgrade import MayaFaceFitUpgradeMixin


class UpgradeHost:
    def __init__(self, needed=True, approved=True):
        self.needed, self.approved = needed, approved
        self.calls = []
        self.converted = False
    def original_face_fit_upgrade_needed(self):return self.needed
    def confirm_original_face_fit_upgrade(self):
        self.calls.append('confirm')
        if not self.approved:raise FitSkeletonValidationError('cancel')
    def capture_original_face_fit_upgrade(self):
        self.calls.append('capture');return {'fit':'old'}
    @contextmanager
    def transaction(self, label):
        self.calls.append('begin')
        try:
            yield
        except Exception:
            self.calls.append('rollback');self.converted=False;raise
        else:self.calls.append('commit')
    def upgrade_original_face_fit(self, source):
        self.converted=True;self.calls.append('upgrade')
        return {'upgraded':True,'requires_pre_fit':True}
    def check_original_face_fit_upgrade(self):return UpgradeOriginalFaceFit(self).apply()


class FaceInputUpgradeTests(unittest.TestCase):
    def test_conversion_commits_before_native_stop(self):
        host=UpgradeHost()
        with self.assertRaisesRegex(FitSkeletonValidationError, 'complete the'):
            check_original_face_input_upgrade(host)
        self.assertTrue(host.converted)
        self.assertEqual(host.calls,['confirm','capture','begin','upgrade','commit'])

    def test_cancel_never_captures_or_opens_a_conversion_transaction(self):
        host=UpgradeHost(approved=False)
        with self.assertRaises(FitSkeletonValidationError):
            check_original_face_input_upgrade(host)
        self.assertEqual(host.calls,['confirm'])
        self.assertFalse(host.converted)

    def test_current_fit_has_no_confirmation_or_mutation(self):
        host=UpgradeHost(needed=False)
        check_original_face_input_upgrade(host)
        self.assertEqual(host.calls,[])

    def test_every_pre_input_stops_before_reading_selection(self):
        for action in ('mask','eye','head','objects'):
            host=UpgradeHost()
            service=RecordFacePreInput(host)
            with self.subTest(action=action), self.assertRaises(FitSkeletonValidationError):
                if action=='mask':service.mask()
                elif action=='head':service.head_joint()
                elif action=='eye':
                    from adv_py.application.face_pre import FaceSide
                    service.eye(FaceSide.RIGHT)
                else:service.objects(FacePreRole.FACE,None)
            self.assertEqual(host.calls[-1],'commit')

    def test_native_detector_uses_version_then_unbuilt_fit_ty(self):
        class Commands:
            def __init__(self,version,ty):self.version,self.ty=version,ty
            def objExists(self,plug):return self.version is not None
            def getAttr(self,plug):return self.version if plug=='FaceGroup.version' else self.ty
        for version, ty, expected in ((5.743,0,True),(5.744,10,False),
                                     (None,1,False),(None,1.001,True)):
            host=NS(_cmds=Commands(version,ty),_fit=lambda:'FaceFitSkeleton')
            self.assertEqual(MayaFaceFitUpgradeMixin.original_face_fit_upgrade_needed(host),expected)

    def test_native_dialog_cancel_uses_original_error(self):
        commands=NS(confirmDialog=lambda **flags:'Cancel')
        with self.assertRaisesRegex(FitSkeletonValidationError,'older version'):
            MayaFaceFitUpgradeMixin.confirm_original_face_fit_upgrade(NS(_cmds=commands))


if __name__=='__main__':unittest.main()
