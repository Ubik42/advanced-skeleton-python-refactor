"""Original asCreateFaceFit sphere sections and fitting material catalogue."""
MARKER_SHADERS = {
    "EyeBrowInner":"asGreenSG", "EyeBrowOuter":"asRedSG",
    "EyeBrowCenter":"asBlueSG", "EyeBrowMid1":"asRedSG", "EyeBrowMid2":"asRedSG",
    "EyeBrowMid3":"asRedSG",
    "JawPivot":"asBlue2SG", "JawCorner":"asBlue2SG", "JawLine":"asBlue2SG",
    "Jaw":"asBlue2SG", "Nose":"asGreenSG", "ChinCrease":"asBlueSG",
    "Throat":"asBlue2SG", "NoseUnder":"asBlueSG", "NoseBridge":"asBlueSG",
    "Cheek":"asGreenSG", "CheekBone":"asBlue2SG", "SmileBulge":"asBlueSG",
    "FrownBulge":"asBlueSG", "NoseCorner":"asRedSG", "NoseSide":"asBlueSG",
    "Nostril":"asBlueSG",
}
CENTER_MARKERS = frozenset(("Nose","Jaw","ChinCrease","NoseUnder","Throat"))
FIT_MATERIALS = (
    ("asRed",(1,0,0)), ("asRed2",(1,0,1)), ("asGreen",(0,1,0)),
    ("asGreen2",(1,1,0)), ("asBlue",(0,0,1)), ("asBlue2",(0,1,1)),
    ("asWhite",(1,1,1)), ("asBlack",(0,0,0)), ("asBones",(.78,.76,.72)),
    ("asRedSS",(1,0,0)),
)
