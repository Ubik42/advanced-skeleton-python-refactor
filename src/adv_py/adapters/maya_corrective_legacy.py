"""Pre-2017 corrective inverse using the original sampled XYZ matrix graph."""
from adv_py.core.fit_settings import FitSkeletonValidationError

class MayaCorrectiveLegacyMixin:
    def calculate_original_corrective_legacy_delta(self, original, corrective, delta, geometry, *, delete_mode=False):
        c=self._cmds;raw=self._corrective_raw()
        shapes=raw.listRelatives(geometry,shapes=True,fullPath=True) or []
        pre=next((shape for shape in reversed(shapes) if raw.getAttr(shape+".intermediateObject")),None)
        if pre is None:
            raise FitSkeletonValidationError("Corrective 反算缺少变形前 Shape")
        c.createNode("transform",name="correctiveMatrixUtilities")
        for kind,name,parent in (("parentConstraint","matrix2xform",None),("scaleConstraint","matrix2scale",None),
            ("transform","invMReaderOffset",None),("transform","invMReader","invMReaderOffset"),
            ("transform","invMNewPos","invMReader"),("transform","defOffset",None),
            ("transform","corPos","defOffset"),("transform","matrixInverter",None),
            ("parentConstraint","matrix2xform2",None),("scaleConstraint","matrix2scale2",None)):
            c.createNode(kind,name=name,**({"parent":parent} if parent else {}))
        c.addAttr("invMReaderOffset",longName="theMatrix",dataType="matrix")
        for channel in ("translate","rotate","scale"):
            c.connectAttr("corPos."+channel,"invMNewPos."+channel,force=True)
        for matrix,pc,sc,destination in (("invMReaderOffset.theMatrix","matrix2xform2","matrix2scale2","matrixInverter"),
            ("matrixInverter.inverseMatrix","matrix2xform","matrix2scale","invMReader")):
            c.connectAttr(matrix,pc+".target[0].targetParentMatrix")
            c.connectAttr(matrix,sc+".target[0].targetParentMatrix")
            for channel in ("Translate","Rotate"):
                for axis in "XYZ":
                    c.connectAttr(pc+".constraint"+channel+axis,destination+"."+channel.lower()+axis)
            c.connectAttr(sc+".constraintScale",destination+".scale")
        c.parent(["matrix2xform","matrix2scale","invMReaderOffset","defOffset","matrixInverter","matrix2xform2","matrix2scale2"],"correctiveMatrixUtilities")
        components=pre+".vtx[0:999999]"
        raw.move(1,0,0,components,relative=True)
        c.duplicate(original,name="xOffsetts")
        raw.move(-1,1,0,components,relative=True)
        c.duplicate(original,name="yOffsetts")
        raw.move(0,-1,1,components,relative=True)
        c.duplicate(original,name="zOffsetts")
        raw.move(0,0,-1,components,relative=True)
        for node in ("xOffsetts","yOffsetts","zOffsetts"):
            for kind in ("t","r","s"):
                for axis in "xyz":
                    c.setAttr(node+"."+kind+axis,lock=False)
            c.parent(node,"correctiveMatrixUtilities")
        moved=0
        for index in range(int(raw.polyEvaluate(self.scene_address(delta),vertex=True))):
            if delete_mode:
                break
            component=".vtx["+str(index)+"]"
            deformed=raw.xform(original+component,query=True,worldSpace=True,translation=True)
            sculpted=c.xform(corrective+component,query=True,worldSpace=True,translation=True)
            if all(abs(a-b)<.001 for a,b in zip(deformed,sculpted)):
                continue
            moved+=1
            neutral=raw.xform(pre+component,query=True,worldSpace=True,translation=True)
            c.xform("invMReaderOffset",worldSpace=True,translation=neutral)
            c.xform("defOffset",worldSpace=True,translation=deformed)
            c.xform("corPos",worldSpace=True,translation=sculpted)
            xyz=[c.xform(node+component,query=True,worldSpace=True,translation=True) for node in ("xOffsetts","yOffsetts","zOffsetts")]
            matrix=[value-deformed[axis] for point in xyz for axis,value in enumerate(point)]
            full=matrix[:3]+[0]+matrix[3:6]+[0]+matrix[6:9]+[0]+[0,0,0,1]
            c.setAttr("invMReaderOffset.theMatrix",*full,type="matrix")
            position=c.xform("invMNewPos",query=True,worldSpace=True,translation=True)
            c.xform(delta+component,worldSpace=True,translation=position)
        c.delete("correctiveMatrixUtilities")
        return moved
