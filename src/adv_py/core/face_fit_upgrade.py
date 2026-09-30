"""Original pre-5.743 Face Fit field migration and naming rules."""
LEGACY_FACE_INPUTS = (("Geometry", "Face"), ("AllFaceGeo", "AllHead"),
    ("Eye_R", "RightEye"), ("Eye_L", "LeftEye"), ("UpperTeeth", "UpperTeeth"),
    ("LowerTeeth", "LowerTeeth"), ("HeadJoint", "HeadJoint"), ("SkinCluster", "SkinCluster"))
OBSOLETE_FACE_FITS = ("FaceFitCheekRaiser", "FaceFitSmileBulge", "FaceFitFrownBulge")


def original_face_fit_needs_upgrade(version, translate_y):
    if version is None:
        return float(translate_y) > 1
    return float(version) <= 5.743
