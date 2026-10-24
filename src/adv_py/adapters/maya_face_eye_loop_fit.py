"""asCreateFaceFit Pupil/Iris complete-loop traversal and tube preview."""
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_original_face_fit_tube import create_original_face_fit_tube

class MayaFaceEyeLoopFitMixin:
    def create_original_eye_loop_fit(self,section):
        self._require_transaction()
        if section not in ("Pupil","Iris"): raise ValueError("眼球边环 Fit 类型无效")
        c=self._cmds; raw=getattr(c,"raw",c)
        fit,scale,suffix,holder=self._marker_context(section)
        selection=tuple(raw.ls(selection=True,long=True,flatten=True) or [])
        if not selection or '.' not in selection[0]:
            raise FitSkeletonValidationError("请选择 Pupil／Iris 多边形组件")
        self._marker_containers(fit,section,suffix,holder)
        if any(token in p for p in selection for token in ('.e[','.vtx[','.f[')):
            c.addAttr(holder,longName="selection",dataType="string")
            c.setAttr(holder+".selection"," ".join(selection)+" ",type="string")
        # Native face-only selection creates the holder and returns at 29647.
        if not any('.e[' in p or '.vtx[' in p for p in selection):
            return holder
        vertices=raw.ls(raw.polyListComponentConversion(selection,toVertex=True),long=True,flatten=True) or []
        if len({p.split(".",1)[0] for p in vertices})!=1: raise FitSkeletonValidationError("眼球边环必须位于同一个网格")
        positions={p:raw.xform(p,query=True,worldSpace=True,translation=True) for p in vertices}
        minimum=999.; maximum=-999.; min_vertex=None; max_vertex=None
        for vertex in vertices:
            x=positions[vertex][0]
            if x<minimum:
                minimum=x; min_vertex=vertex
            if x>maximum and x<(9999 if suffix else .001):
                maximum=x; max_vertex=vertex
        start=min_vertex if suffix else max_vertex
        if start is None:
            raise FitSkeletonValidationError("Pupil／Iris 没有原版阈值内的起点")
        raw.select(start,replace=True)
        incident=raw.ls(raw.polyListComponentConversion(start,toEdge=True),long=True,flatten=True) or []
        chosen=[edge for edge in incident if edge in selection]
        if not chosen:
            raise FitSkeletonValidationError("Pupil／Iris 起点没有所选相邻边")
        if len(chosen)>1:
            a=raw.xform(chosen[0],query=True,worldSpace=True,translation=True)
            b=raw.xform(chosen[1],query=True,worldSpace=True,translation=True)
            swap=(a[0]+a[3])>(b[0]+b[3])
            if suffix: swap=not swap
            if swap: chosen[0],chosen[1]=chosen[1],chosen[0]
        excluded=chosen[1] if len(chosen)>1 else None
        previous=[start]; covered=[]; points=[positions[start]]; end=None
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
        curve=c.curve(name=section+"Curve"+suffix,degree=1,point=points)
        c.parent(curve,"FaceFit"+section+"Curve"+suffix)
        c.makeIdentity(holder,apply=True,translate=True,rotate=True,scale=True)
        shape=c.listRelatives(curve,shapes=True,fullPath=True)[0]
        # MEL creates faceLoopCurve1 then renames its transform. Maya renames
        # the matching Shape as well. Python curve(name=...) leaves curveShapeN,
        # which becomes ambiguous after the source Prep duplicates both sides.
        shape=c.rename(shape,section+"Curve"+suffix+"Shape")
        shape=c.listRelatives(curve,shapes=True,fullPath=True)[0]
        c.setAttr(shape+".overrideEnabled",True); c.setAttr(shape+".overrideColor",17)
        create_original_face_fit_tube(self,section,'',suffix,'',scale,
            'asRedSG' if section=='Pupil' else 'asGreenSG')
        c.select(holder,replace=True)
        return curve
