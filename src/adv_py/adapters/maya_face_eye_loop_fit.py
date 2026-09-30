"""asCreateFaceFit Pupil/Iris complete-loop traversal and tube preview."""
from adv_py.core.fit_settings import FitSkeletonValidationError

class MayaFaceEyeLoopFitMixin:
    def create_original_eye_loop_fit(self,section):
        self._require_transaction()
        if section not in ("Pupil","Iris"): raise ValueError("眼球边环 Fit 类型无效")
        c=self._cmds; raw=getattr(c,"raw",c)
        fit,scale,suffix,holder=self._marker_context(section)
        selection=tuple(raw.ls(selection=True,long=True,flatten=True) or [])
        if not selection or any(".e[" not in p for p in selection): raise FitSkeletonValidationError("请选择完整 Pupil／Iris 边环")
        vertices=raw.ls(raw.polyListComponentConversion(selection,toVertex=True),long=True,flatten=True) or []
        if len({p.split(".",1)[0] for p in vertices})!=1: raise FitSkeletonValidationError("眼球边环必须位于同一个网格")
        positions={p:raw.xform(p,query=True,worldSpace=True,translation=True) for p in vertices}
        eligible=[p for p in vertices if positions[p][0]<(9999 if suffix else .001)]
        if not eligible: raise FitSkeletonValidationError("Pupil／Iris 需要当前侧对应的眼球边环")
        start=min(vertices,key=lambda p:positions[p][0]) if suffix else max(eligible,key=lambda p:positions[p][0])
        raw.select(start,replace=True)
        incident=raw.ls(raw.polyListComponentConversion(start,toEdge=True),long=True,flatten=True) or []
        chosen=[edge for edge in incident if edge in selection]
        if len(chosen)!=2: raise FitSkeletonValidationError("Pupil／Iris 起点必须有两个所选相邻边")
        a=raw.xform(chosen[0],query=True,worldSpace=True,translation=True)
        b=raw.xform(chosen[1],query=True,worldSpace=True,translation=True)
        swap=(a[0]+a[3])>(b[0]+b[3])
        if suffix: swap=not swap
        if swap: chosen.reverse()
        excluded=chosen[1]; previous=[start]; covered=[]; points=[positions[start]]; end=None
        raw.select(start,replace=True)
        for _ in range(199):
            incident=raw.ls(raw.polyListComponentConversion(raw.ls(selection=True,long=True,flatten=True),toEdge=True),long=True,flatten=True) or []
            edges=[p for p in incident if p in selection and p!=excluded]
            if not edges: break
            covered.append(edges[0])
            current=raw.ls(raw.polyListComponentConversion(edges,toVertex=True),long=True,flatten=True) or []
            remaining=[p for p in current if p not in previous]; previous=current
            if not remaining: break
            points.append(raw.xform(remaining[0],query=True,worldSpace=True,translation=True))
            raw.select(current,replace=True)
            if len(covered)==len(selection): end=remaining[0]; break
        if end is None: points.append(positions[start])
        self._marker_containers(fit,section,suffix,holder)
        c.addAttr(holder,longName="selection",dataType="string")
        c.setAttr(holder+".selection"," ".join(selection)+" ",type="string")
        curve=c.curve(name=section+"Curve"+suffix,degree=1,point=points)
        c.parent(curve,"FaceFit"+section+"Curve"+suffix)
        shape=c.listRelatives(curve,shapes=True,fullPath=True)[0]
        c.setAttr(shape+".overrideEnabled",True); c.setAttr(shape+".overrideColor",17)
        profile=c.circle(name=section+"Profile"+suffix,normal=(0,1,0),radius=scale/400,degree=3,sections=8,constructionHistory=False)[0]
        tube=c.extrude(profile,curve,name=section+"Cylinder"+suffix,constructionHistory=False,extrudeType=2,
                       useComponentPivot=True,fixedPath=True,useProfileNormal=True,rotation=0,scale=1)[0]
        c.delete(profile); c.parent(tube,"FaceFit"+section+"Geo"+suffix)
        c.setAttr(tube+".overrideEnabled",True); c.setAttr(tube+".overrideDisplayType",2)
        c.setAttr(c.listRelatives(tube,shapes=True,fullPath=True)[0]+".curvePrecisionShaded",4)
        a=c.xform(tube+".cv[6][0]",query=True,worldSpace=True,translation=True)
        b=c.xform(tube+".cv[6][1]",query=True,worldSpace=True,translation=True)
        if a[1]>b[1]: c.reverseSurface(tube,direction=0,constructionHistory=False,replaceOriginal=True)
        c.sets(tube,edit=True,forceElement="asRedSG" if section=="Pupil" else "asGreenSG")
        c.select(holder,replace=True)
        return curve
