"""Original BlendShape target filtering and eye mirror naming."""
from fnmatch import fnmatchcase

BLENDED_FACE_TARGETS = ("txPos_tyPos", "txPos_tyNeg", "txNeg_tyPos", "txNeg_tyNeg",
                       "smile", "frown", "narrowSmile", "narrowFrown")


def original_face_bs_mirror_name(name):
    mirrored = name.replace("_R", "_L", 1)
    if fnmatchcase(name, "ctrlEyetranslateXNeg_R*"):
        mirrored = mirrored.replace("Neg_", "Pos_", 1)
    if fnmatchcase(name, "ctrlEyetranslateXPos_R*"):
        mirrored = mirrored.replace("Pos_", "Neg_", 1)
    if "eye_right_" in name:
        mirrored = mirrored.replace("_right_", "_left_", 1)
    if "eye_left_" in name:
        mirrored = mirrored.replace("_left_", "_right_", 1)
    return mirrored
