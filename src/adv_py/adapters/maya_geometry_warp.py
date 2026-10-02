"""Source PolyBoxes Warp: constraint-first subdivision and material sampling."""
from .maya_geometry_boolean import MayaBooleanHost

class MayaWarpHost(MayaBooleanHost):
    def __init__(self,namespace=''):
        super().__init__(namespace);self._created_warps=()

    def capture_warp_names(self):
        c=self.cmds;group=self._name('WarpGeometry')
        return frozenset(self._leaf(node) for node in c.listRelatives(group,children=True,type='transform') or []) if c.objExists(group) else frozenset()

    def warp_exists(self):return any(self.cmds.objExists(self._name(name)) for name in ('Warp','WarpGeometry'))

    def preflight_warp(self,plan):
        self.preflight_boolean(plan)
        for name in ('AdvPy_WarpClosestSampler','AdvPy_WarpMaterialMesh'):
            if self.cmds.objExists(self._name(name)):raise ValueError('Warp 临时名称已占用：'+name)

    def _next_warp_name(self,box):
        c=self.cmds;stem,side=box.rsplit('_',1)
        for index in range(1,99):
            candidate=self._name(f'{stem}Warp{index}_{side}')
            if not c.objExists(candidate):return candidate
        return self._name(f'{stem}Warp99_{side}')

    def _material_source(self,source,sampler,multiple,copies):
        c=self.cmds;shape=c.listRelatives(source,shapes=True,noIntermediate=True,type='mesh',fullPath=True)[0]
        direct=c.listConnections(shape+'.instObjGroups') or []
        if direct:return direct[0]
        count=c.getAttr(shape+'.instObjGroups.objectGroups',size=True)
        for index in range(count):
            if index==0:
                copy=c.duplicate(source,name=self._name('AdvPy_WarpMaterialMesh'))[0];copies.append(copy)
                # Native tempMesh literal keeps addressing the first copy
                # across source meshes. Retain that material-sampling choice.
                first=self._name('AdvPy_WarpMaterialMesh')
                self.unlock_geometry_transform(first);c.setAttr(first+'.visibility',0)
                if c.listRelatives(first,parent=True):c.parent(first,world=True)
                c.makeIdentity(first,apply=True,translate=True,rotate=True,scale=True)
                shape_copy=c.listRelatives(first,shapes=True,noIntermediate=True,type='mesh')[0]
                c.connectAttr(shape_copy+'.outMesh',sampler+'.inMesh',force=True)
            engines=c.listConnections(shape+f'.instObjGroups.objectGroups[{index}].objectGrpColor',type='shadingEngine') or []
            if engines:multiple.append(engines[0])
        return None

    def _project_warp(self,spec,group,layer,sampler,multiple,single):
        c=self.cmds;box=self._name(spec.box);joint=self._name(spec.joint)
        warp=c.duplicate(box,name=self._next_warp_name(spec.box))[0]
        self.unlock_geometry_transform(warp);warp=c.parent(warp,group)[0]
        c.parentConstraint(joint,warp);c.scaleConstraint(joint,warp)
        try:
            c.polySmooth(warp,mth=0,dv=spec.divisions,bnr=1,c=1,kb=1,ksb=1,khe=1,kt=1,kmb=1,
                         suv=1,peh=0,sl=1,dpe=1,ps=.1,ro=1,ch=True)
        except RuntimeError:pass  # native catch, followed by the same projection
        c.scale(1,.7,.7,warp+'.e[0:15]',relative=True,objectCenterPivot=True)
        c.scale(1,.9,.9,*[warp+'.vtx'+suffix for suffix in
            ('[34:50]','[52]','[54]','[56]','[58]','[60]','[62]','[64]','[74:89]')],
            relative=True,objectCenterPivot=True)
        c.select(spec.source,warp,replace=True)
        c.transferAttributes(transferPositions=1,transferNormals=0,transferUVs=2,transferColors=2,
            sampleSpace=0,sourceUvSpace='map1',targetUvSpace='map1',searchMethod=3,flipUVs=False,colorBorders=True)
        c.delete(warp,constructionHistory=True)
        if c.polyEvaluate(warp,area=True)<1.:
            c.delete(warp);return None
        if multiple:
            for face in range(c.polyEvaluate(warp,face=True)):
                positions=c.xform(warp+f'.f[{face}]',query=True,worldSpace=True,translation=True)
                center=tuple(sum(positions[axis::3])/(len(positions)//3) for axis in range(3))
                c.setAttr(sampler+'.inPosition',*center,type='double3')
                nearest=c.getAttr(sampler+'.closestFaceIndex')
                for engine in multiple:
                    if c.sets(spec.source+f'.f[{nearest}]',isMember=engine):
                        c.sets(warp+f'.f[{face}]',edit=True,forceElement=engine)
        elif single:
            shape=c.listRelatives(warp,shapes=True,noIntermediate=True)[0]
            c.sets(shape,edit=True,forceElement=single)
        c.editDisplayLayerMembers(layer,warp,noRecurse=True);c.refresh()
        return warp

    def create_warp(self,plan):
        c=self.cmds;self.refresh_hidden_boxes(refresh_after_hide=False)
        group,layer=self.ensure_geometry_group('Warp',28)
        states=self.hide_geometry_sources(plan);created=[];copies=[];multiple=[];single=None
        sampler=c.createNode('closestPointOnMesh',name=self._name('AdvPy_WarpClosestSampler'))
        try:
            for source in dict.fromkeys(spec.source for spec in plan):
                shader=self._material_source(source,sampler,multiple,copies)
                if shader:single=shader
                for spec in (spec for spec in plan if spec.source==source):
                    mesh=self._project_warp(spec,group,layer,sampler,multiple,single)
                    if mesh:created.append(mesh)
        finally:
            if c.objExists(sampler):c.delete(sampler)
            for copy in copies:
                if c.objExists(copy):c.delete(copy)
            self.restore_geometry_visibility(states)
        c.select(clear=True);self._created_warps=tuple(created)
        return len(created)

    def capture_warp(self,count):
        c=self.cmds;group=self._name('WarpGeometry');layer=self._name('Warp')
        return (c.objExists(group) and c.objExists(layer) and c.getAttr(layer+'.color')==28
                and c.getAttr(layer+'.displayType')==2 and count==len(self._created_warps)
                and all(self.assert_driven_mesh(node,group) for node in self._created_warps))

    def delete_warp(self):self.delete_geometry_family('Warp','*Warp*_*')
