"""Native old-Fit gate before Choose Input and the Face build Prep stage."""
from adv_py.core.fit_settings import FitSkeletonValidationError


def check_original_face_input_upgrade(host):
    check = getattr(host, 'check_original_face_fit_upgrade', None)
    if check is None:
        return
    result = check()
    if result and result.get('requires_pre_fit'):
        # The native procedure finishes the conversion, then reports an
        # error to stop the caller. Raise AFTER its transaction has committed.
        raise FitSkeletonValidationError(
            'FaceFitSkeleton updated.\nNext complete the "Pre" and "Fit" section, '
            'before building the FaceSetup.\n')
