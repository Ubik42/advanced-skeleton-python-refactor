"""Literal ADV 6.925 ARKit and SnapChat names and driving magnitudes.

SnapChat's final MouthUpLeft/Right entries have no ARKit equivalents and are
not iterated by the original asConnectARKit loop.
"""
ARKIT_SHAPES = ('eyeBlinkLeft', 'eyeLookDownLeft', 'eyeLookInLeft', 'eyeLookOutLeft', 'eyeLookUpLeft', 'eyeSquintLeft', 'eyeWideLeft', 'eyeBlinkRight', 'eyeLookDownRight', 'eyeLookInRight', 'eyeLookOutRight', 'eyeLookUpRight', 'eyeSquintRight', 'eyeWideRight', 'jawForward', 'jawLeft', 'jawRight', 'jawOpen', 'mouthClose', 'mouthFunnel', 'mouthPucker', 'mouthLeft', 'mouthRight', 'mouthSmileLeft', 'mouthSmileRight', 'mouthFrownLeft', 'mouthFrownRight', 'mouthDimpleLeft', 'mouthDimpleRight', 'mouthStretchLeft', 'mouthStretchRight', 'mouthRollLower', 'mouthRollUpper', 'mouthShrugLower', 'mouthShrugUpper', 'mouthPressLeft', 'mouthPressRight', 'mouthLowerDownLeft', 'mouthLowerDownRight', 'mouthUpperUpLeft', 'mouthUpperUpRight', 'browDownLeft', 'browDownRight', 'browInnerUp', 'browOuterUpLeft', 'browOuterUpRight', 'cheekPuff', 'cheekSquintLeft', 'cheekSquintRight', 'noseSneerLeft', 'noseSneerRight', 'tongueOut')
SNAPCHAT_SHAPES = ('EyeBlinkLeft', 'EyeDownLeft', 'EyeInLeft', 'EyeOutLeft', 'EyeUpLeft', 'EyeSquintLeft', 'EyeOpenLeft', 'EyeBlinkRight', 'EyeDownRight', 'EyeInRight', 'EyeOutRight', 'EyeUpRight', 'EyeSquintRight', 'EyeOpenRight', 'JawForward', 'JawLeft', 'JawRight', 'JawOpen', 'MouthClose', 'LipsFunnel', 'LipsPucker', 'MouthLeft', 'MouthRight', 'MouthSmileLeft', 'MouthSmileRight', 'MouthFrownLeft', 'MouthFrownRight', 'MouthDimpleLeft', 'MouthDimpleRight', 'MouthStretchLeft', 'MouthStretchRight', 'LowerLipClose', 'UpperLipClose', 'LowerLipRaise', 'UpperLipRaise', 'LowerLipDownLeft', 'LowerLipDownRight', 'UpperLipUpLeft', 'UpperLipUpRight', 'BrowsDownLeft', 'BrowsDownRight', 'BrowsUpCenter', 'BrowsUpLeft', 'BrowsUpRight', 'Puff', 'CheekSquintLeft', 'CheekSquintRight', 'SneerLeft', 'SneerRight', 'MouthUpLeft', 'MouthUpRight')
SNAPCHAT_ARKIT_SHAPES = tuple(name for name in ARKIT_SHAPES
    if name not in ("mouthPressLeft", "mouthPressRight", "tongueOut"))


def original_arkit_driver_rows(name, *, jaw_forward=True):
    """Yield (driven plug, driver value override, driven value) in source order."""
    rows = []
    for sign, side, label in ((1, "_R", "Right"), (-1, "_L", "Left")):
        eye = {"eyeBlink": ("blink", 10), "eyeLookDown": ("ty", -1),
               "eyeLookIn": ("tx", sign), "eyeLookOut": ("tx", -sign),
               "eyeLookUp": ("ty", 1), "eyeSquint": ("squint", 10), "eyeWide": ("wide", 10)}
        for prefix, (attr, value) in eye.items():
            if name == prefix + label:
                rows.append(("ctrlEye" + side + "." + attr, None, value))
        single = {"mouthDimple": ("ctrlMouthCorner", "tx", .3),
                  "browOuterUp": ("ctrlBrow", "outerUpDown", 7.5),
                  "noseSneer": ("ctrlNose", "ty", .5)}
        for prefix, (control, attr, value) in single.items():
            if name == prefix + label:
                rows.append((control + side + "." + attr, None, value))
        if name == "mouth" + label:
            rows.append(("ctrlLips_M.tx", None, -1 if label == "Right" else 1))
        for prefix, x, y in (("mouthSmile", .75, .75), ("mouthFrown", .25, -.25), ("mouthStretch", .5, -.5)):
            if name == prefix + label:
                rows.extend((("ctrlMouthCorner" + side + ".tx", None, x),
                             ("ctrlMouthCorner" + side + ".ty", None, y)))
        # Source repeats these central press rows inside both side iterations.
        if name in ("mouthPressRight", "mouthPressLeft"):
            rows.extend((("ctrlLips_M.upperSqueeze", None, 1.5), ("ctrlLips_M.lowerSqueeze", None, 1.5),
                         ("SDKLipRegion_M.ty", None, .1)))
        if name == "mouthPress" + label:
            rows.append(("ctrlMouthCorner" + side + ".ty", None, .25))
        if name == "mouthLowerDown" + label:
            rows.extend((("SDKlowerLipA" + side + ".ty", None, -.4), ("SDKlowerLip_M.ty", 10, -.3)))
        if name == "mouthUpperUp" + label:
            rows.extend((("SDKupperLipA" + side + ".ty", 10, .4), ("SDKupperLip_M.ty", None, .3)))
        if name == "browDown" + label:
            rows.extend((("ctrlBrow" + side + ".ty", None, -.75), ("ctrlBrow" + side + ".squeeze", None, 7.5)))
        if name == "cheekSquint" + label:
            rows.extend((("ctrlEye" + side + ".squint", None, 3), ("SDKCheek" + side + ".ty", None, .1)))
    center = {
        "jawOpen": (("ctrlMouth_M.ty", -1),),
        "mouthPucker": (("ctrlLips_M.upperPucker", 10), ("ctrlLips_M.lowerPucker", 10)),
        "mouthFunnel": (("ctrlLips_M.upperPucker", 10), ("ctrlLips_M.lowerPucker", 10),
                        ("SDKupperLip_M.ty", .3), ("SDKlowerLip_M.ty", -.3)),
        "mouthRollUpper": (("ctrlLips_M.upperRoll", -5),), "mouthRollLower": (("ctrlLips_M.lowerRoll", -5),),
        "mouthShrugUpper": (("SDKupperLip_M.ty", .3),), "mouthShrugLower": (("SDKlowerLip_M.ty", .3),),
        "browInnerUp": (("ctrlBrow_R.tx", 1), ("ctrlBrow_L.tx", 1)),
        "cheekPuff": (("ctrlCheek_R.tx", .4), ("ctrlCheek_L.tx", .4), ("ctrlMouth_M.tx", -.2)),
        "tongueOut": (("SDKTongue0_M.tx", 1.5), ("SDKTongue0_M.rz", 15))}
    if jaw_forward:
        center.update(jawForward=(("ctrlMouth_M.jawForward", 5),),
                      jawRight=(("ctrlMouth_M.jawSide", -5),), jawLeft=(("ctrlMouth_M.jawSide", 5),))
    rows.extend((plug, None, value) for plug, value in center.get(name, ()))
    return tuple(rows)
