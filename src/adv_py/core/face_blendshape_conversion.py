"""Source naming and sample amplitudes for asBSConvertDStoBS."""
from dataclasses import dataclass


@dataclass(frozen=True)
class FaceBlendShapeConversionOptions:
    keep_joints: bool = False
    keep_targets: bool = False


def original_face_bs_target_name(control, attr, sign, positive_only=False, user_attribute=False):
    stem, side = control[:-2], control[-2:]
    suffix = "" if positive_only else "Pos" if sign == 1 else "Neg"
    name = stem + attr + suffix + side
    pairs = {
        "ctrlBrow": {("translateX", 1): "brow_innerRaiser", ("translateX", -1): "brow_innerlower",
                     ("translateY", 1): "brow_raiser", ("translateY", -1): "brow_lower",
                     ("squeeze", 1): "brow_squeeze", ("outerUpDown", 1): "brow_outerUpDown"},
        "ctrlCheek": {("translateX", 1): "cheek_out", ("translateX", -1): "cheek_in", ("translateY", 1): "cheek_raiser"},
        "ctrlNose": {("translateX", 1): "nose_wide", ("translateX", -1): "nose_narrow", ("translateY", 1): "nose_raiser"},
        "ctrlMouthCorner": {("translateX", 1): "mouth_wide", ("translateX", -1): "mouth_narrow",
                            ("translateY", 1): "mouth_raiser", ("translateY", -1): "mouth_lower",
                            ("txPos_tyPos", 1): "mouth_smileBulge", ("txPos_tyNeg", 1): "mouth_frownBulge"},
        "ctrlEye": {("translateX", 1): "eye_left", ("translateX", -1): "eye_right",
                    ("translateY", 1): "eye_up", ("translateY", -1): "eye_down",
                    ("blink", 1): "blink", ("squint", 1): "squint"},
        "ctrlLips": {("translateX", 1): "lip_left", ("translateX", -1): "lip_right",
                     ("translateY", 1): "lip_up", ("translateY", -1): "lip_down"},
        "ctrlMouth": {("translateX", 1): "mouth_wide", ("translateX", -1): "mouth_narrow",
                      ("translateY", 1): "mouth_close", ("translateY", -1): "mouth_open"}}
    override = pairs.get(stem, {}).get((attr, sign))
    if override:
        name = override + side
    if control == "ctrlLips_M" and user_attribute:
        name = "lip_" + attr + suffix + side
    if control == "ctrlMouth_M" and attr not in ("translateX", "translateY"):
        name = "mouth_" + attr + ("In" if sign == 1 else "Out") + side
    if control in ("ctrlPhonemes_M", "ctrlEmotions_M"):
        name = attr + side
    if control == "ctrlARKit_M":
        name = attr
    return name


def original_face_bs_driving_value(attribute, sign, blended=False):
    if attribute in ("translateX", "translateY") or blended:
        return sign
    if attribute in ("rotateX", "rotateY"):
        return 30 * sign
    return 10 * sign
