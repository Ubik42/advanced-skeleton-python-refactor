"""Scene ports of asFaceFitJawCurves and asCurveOffsetMesh (6.925)."""
from __future__ import annotations
from math import isfinite
from adv_py.application.face_pre import FacePreRole
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.face_jaw_fit import JAW_FIT_CURVES, JAW_FIT_MARKERS
from .maya_face_pre import MayaFacePreHost

class MayaFaceJawFitHost(MayaFacePreHost):
    def _jaw_one(self, name, kind=None):
        paths = self._cmds.ls(name, long=True, **({"type":kind} if kind else {})) or []
        if len(paths) != 1:
            raise FitSkeletonValidationError("Jaw Fit 节点缺失或不唯一：" + name)
        return paths[0]

    def _jaw_curve_shape(self, curve):
        shapes = self._cmds.listRelatives(curve, shapes=True, noIntermediate=True,
                                         fullPath=True, type="nurbsCurve") or []
        if len(shapes) != 1:
            raise FitSkeletonValidationError("Jaw Fit 曲线 Shape 缺失或不唯一：" + curve)
        return shapes[0]

    def capture_jaw_fit_input(self):
        c = self._cmds
        fit = self._fit(required=True)
        meshes = self.read_face_objects(FacePreRole.FACE)
        if len(meshes) != 1:
            raise FitSkeletonValidationError("Jaw Fit 需要唯一 Face 网格")
        markers = tuple((name, self._jaw_one(name,"transform"),
                         tuple(c.xform(name,query=True,worldSpace=True,translation=True)))
                        for name in JAW_FIT_MARKERS)
        upper = self._jaw_one("upperLipOuterCurve","transform")
        shape = self._jaw_curve_shape(upper)
        # Original spans + 1 selects the end CV of its cubic outer lip curve.
        endpoint = int(c.getAttr(shape + ".spans")) + 1
        position = tuple(c.xform(upper + f".cv[{endpoint}]", query=True,
                                worldSpace=True, translation=True))
        scale = float(c.getAttr(fit + ".faceScale"))
        if not isfinite(scale) or scale <= 0:
            raise FitSkeletonValidationError("Jaw Fit faceScale 必须为正")
        return fit, meshes[0], scale, markers, position

    def _jaw_rebuild(self, curve, spans):
        self._cmds.rebuildCurve(curve,constructionHistory=False,replaceOriginal=True,
            rebuildType=0,endKnots=1,keepRange=0,keepControlPoints=False,
            keepEndPoints=True,keepTangents=False,spans=spans,degree=3,tolerance=.01)

    def offset_face_curve_to_mesh(self, curve, mesh, offset):
        """Sample 23 cubic CVs on the mesh normal, then restore end points."""
        self._require_transaction()
        c = self._cmds
        shape = self._jaw_curve_shape(curve)
        spans = int(c.getAttr(shape + ".spans"))
        degree = int(c.getAttr(shape + ".degree"))
        last = spans + degree - 1
        start = c.xform(curve + ".cv[0]",query=True,worldSpace=True,translation=True)
        end = c.xform(curve + f".cv[{last}]",query=True,worldSpace=True,translation=True)
        self._jaw_rebuild(curve,20)
        locator = c.spaceLocator(name="constraintLoc#")[0]
        offset_locator = c.spaceLocator(name="constraintLocOffset#")[0]
        offset_locator = c.parent(offset_locator,locator,relative=True)[0]
        c.setAttr(offset_locator + ".translateX",offset)
        c.geometryConstraint(mesh,locator,weight=1)
        c.normalConstraint(mesh,locator,weight=1,aimVector=(1,0,0),upVector=(0,1,0),
                           worldUpType="vector",worldUpVector=(0,1,0))
        for index in range(23):
            cv = curve + f".cv[{index}]"
            position = c.xform(cv,query=True,worldSpace=True,translation=True)
            c.xform(locator,worldSpace=True,translation=position)
            projected = c.xform(offset_locator,query=True,worldSpace=True,translation=True)
            c.xform(cv,worldSpace=True,translation=projected)
        self._jaw_rebuild(curve,spans)
        c.delete(locator)
        c.xform(curve + ".cv[0]",worldSpace=True,translation=start)
        c.xform(curve + f".cv[{spans+2}]",worldSpace=True,translation=end)

    def create_jaw_fit_curves(self, source):
        self._require_transaction()
        c = self._cmds
        fit, mesh, scale, markers, upper_endpoint = source
        positions = {name:pos for name,path,pos in markers}
        group = c.createNode("transform",name="FaceFitJawCurves",parent=fit)
        self._transaction_changed = True
        def curve(name,points,color,spans=None):
            node = c.curve(name=name,degree=1,point=points)
            shape = self._jaw_curve_shape(node)
            c.setAttr(shape + ".overrideEnabled",True)
            c.setAttr(shape + ".overrideColor",color)
            if spans is not None: self._jaw_rebuild(node,spans)
            return node
        pivot,corner,jaw,cheek = (positions[name] for name in ("JawPivot","JawCorner","Jaw","Cheek"))
        main = curve("JawCurve",(pivot,corner,jaw),14,3)
        for index,reference,axes in ((1,pivot,(0,2)),(3,cheek,(0,2)),(4,jaw,(2,))):
            value = list(c.xform(main + f".cv[{index}]",query=True,worldSpace=True,translation=True))
            for axis in axes: value[axis] = reference[axis]
            c.xform(main + f".cv[{index}]",worldSpace=True,translation=value)
        self.offset_face_curve_to_mesh(main,mesh,scale/150)
        middle = curve("JawCurveMid",(pivot,cheek,upper_endpoint),13,2)
        self.offset_face_curve_to_mesh(middle,mesh,scale/150)
        bone,nose,under = (positions[name] for name in ("CheekBone","NoseCorner","NoseUnder"))
        halfway = ((pivot[0]+cheek[0])/2,(pivot[1]+bone[1])/2,(pivot[2]+cheek[2])/2)
        top = curve("JawCurveTop",(pivot,halfway,bone,nose,(0,under[1],under[2])),6)
        self.offset_face_curve_to_mesh(top,mesh,scale/150)
        cv1 = c.xform(main + ".cv[1]",query=True,worldSpace=True,translation=True)
        behind = cv1[2]-scale/20
        bottom = curve("JawCurveBottom",(pivot,(cv1[0],cv1[1],behind),
            (pivot[0],jaw[1],behind),positions["Throat"]),6)
        self.offset_face_curve_to_mesh(bottom,mesh,scale/150)
        c.parent(JAW_FIT_CURVES,group,absolute=True)
        c.select(clear=True)
        return JAW_FIT_CURVES

    def validate_jaw_fit_curves(self):
        c = self._cmds
        group = self._jaw_one("FaceFitJawCurves","transform")
        fit = self._fit(required=True)
        if (c.listRelatives(group,parent=True,fullPath=True) or []) != [fit]:
            raise RuntimeError("Jaw Fit 曲线容器没有保留在 Face Fit 中")
        for name,spans in zip(JAW_FIT_CURVES,(3,2,4,3)):
            node = self._jaw_one(name,"transform")
            shape = self._jaw_curve_shape(node)
            if (int(c.getAttr(shape+".spans")) != spans or int(c.getAttr(shape+".degree")) != 3
                    or (c.listRelatives(node,parent=True,fullPath=True) or []) != [group]):
                raise RuntimeError("Jaw Fit 曲线分段或层级与原版不一致："+name)
