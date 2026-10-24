"""The common asCreateFaceFit preview extrusion, MEL 30363–30435."""


def create_original_face_fit_tube(host, section, part, suffix, upper_lower,
                                  face_scale, shading_group):
    host._require_transaction()
    c=host._cmds
    curve=upper_lower+section+part+'Curve'+suffix
    profile=section+'Profile'+part+suffix
    cylinder=upper_lower+section+'Cylinder'+part+suffix
    curve_holder='FaceFit'+section+part+'Curve'+suffix
    geo_holder='FaceFit'+section+part+'Geo'+suffix
    host._transaction_changed=True
    profile=c.circle(name=profile,center=(0,0,0),normal=(0,1,0),sweep=360,
        radius=face_scale/400.,degree=3,useTolerance=False,
        tolerance=.000393701,sections=8,constructionHistory=False)[0]
    profile=c.parent(profile,curve_holder)[0]
    # Preserve native short flags, including Maya's output/range and reverse
    # surface policy. These are the flags in the source extrude statement.
    tube=c.extrude(profile,curve,name=cylinder,ch=False,rn=False,po=0,
        et=2,ucp=True,fpt=True,upn=True,rotation=0,scale=1,rsp=0)[0]
    c.delete(profile)
    c.setAttr(tube+'.overrideEnabled',1)
    c.setAttr(tube+'.overrideDisplayType',2)
    shape=c.listRelatives(tube,shapes=True,fullPath=True)[0]
    c.rename(shape,cylinder+'Shape')
    shape=c.listRelatives(tube,shapes=True,fullPath=True)[0]
    c.setAttr(shape+'.curvePrecisionShaded',4)
    tube=c.parent(tube,geo_holder)[0]
    first=c.xform(tube+'.cv[6][0]',query=True,worldSpace=True,translation=True)
    second=c.xform(tube+'.cv[6][1]',query=True,worldSpace=True,translation=True)
    if first[1]>second[1]:
        c.reverseSurface(tube,direction=0,constructionHistory=False,replaceOriginal=True)
    if shading_group:
        c.sets(tube,edit=True,forceElement=shading_group)
    return tube
