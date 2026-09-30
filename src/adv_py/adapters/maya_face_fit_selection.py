"""asGetFaceFitSelection sampling without evaluating generated MEL text."""
from adv_py.core.fit_settings import FitSkeletonValidationError

class MayaFaceFitSelectionMixin:
    def sample_face_fit_vertices(self,object_name,geometry):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        shapes=c.listRelatives(geometry,shapes=True,noIntermediate=True,fullPath=True,type="mesh") or []
        if len(shapes)!=1: raise FitSkeletonValidationError("Face 采样几何体需要唯一 Mesh Shape")
        sampler=c.createNode("closestPointOnMesh",name="closestSamplerFitSelection#")
        raw.connectAttr(self.scene_address(shapes[0])+".outMesh",self.scene_address(sampler)+".inMesh",force=True)
        result=[]
        def sample(point):
            c.setAttr(sampler+".inPosition",*point,type="float3")
            result.append(geometry+f".vtx[{int(c.getAttr(sampler+'.closestVertexIndex'))}]")
        def visit(node):
            if "." in node:
                sample(c.xform(node,query=True,worldSpace=True,translation=True)); return
            local_shapes=c.listRelatives(node,shapes=True,noIntermediate=True,fullPath=True) or []
            if not local_shapes:
                for child in c.listRelatives(node,children=True,fullPath=True,type="transform") or []:
                    if "Profile" not in child: visit(child)
                return
            kind=c.nodeType(local_shapes[0])
            if kind=="locator": sample(c.xform(node,query=True,worldSpace=True,translation=True))
            elif kind=="nurbsCurve":
                count=int(c.getAttr(local_shapes[0]+".spans"))+int(c.getAttr(local_shapes[0]+".degree"))
                for index in range(count): sample(c.xform(node+f".cv[{index}]",query=True,worldSpace=True,translation=True))
            elif kind=="mesh":
                extrusion=node+"PolyExtrudeFacet"
                if c.objExists(extrusion): c.setAttr(extrusion+".nodeState",1)
                try:
                    for index in range(int(c.polyEvaluate(node,vertex=True))):
                        sample(c.xform(node+f".vtx[{index}]",query=True,worldSpace=True,translation=True))
                finally:
                    if c.objExists(extrusion): c.setAttr(extrusion+".nodeState",0)
            else: raise FitSkeletonValidationError("不支持的 Face Fit 采样类型："+kind)
        try: visit(object_name)
        finally: c.delete(sampler)
        return tuple(result)
