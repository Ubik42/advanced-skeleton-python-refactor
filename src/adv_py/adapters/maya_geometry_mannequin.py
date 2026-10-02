"""Original ADV Mannequin: templates, native constraints and fixed Skin rules."""
from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4
import re

from adv_py.core.geometry_mannequin import MannequinPiece, MannequinSegment
from adv_py.core.adv_icon_axis import icon_axis_offset
from .maya_geometry_skeleton import MayaSkeletonGeometryHost, geometry_asset


class MayaMannequinHost(MayaSkeletonGeometryHost):
    def __init__(self, namespace: str = '') -> None:
        super().__init__(namespace)
        self._mannequin_created=[]

    @contextmanager
    def transaction(self,label):
        from .maya_fit_geometry import MayaFitGeometryHost
        with super().transaction(label):
            with MayaFitGeometryHost(self.namespace).namespace_scope():yield

    def _main(self):
        for name in ('Main','AdvPy_Global'):
            if self.cmds.objExists(self._name(name)):return self._name(name)
        raise ValueError('Mannequin 缺少角色主控制器')

    def _source_offset(self,joint):
        from .maya_original_axes import original_axes
        return icon_axis_offset(*original_axes(self.cmds,joint,self._main(),
                                              fit_skeleton=self._name('FitSkeleton')))

    def _rla_child(self,joint,tolerance):
        c=self.cmds;children=c.listRelatives(joint,children=True,type='joint',fullPath=True) or []
        x=c.xform(joint,q=True,ws=True,t=True)[0];center=-tolerance<x<tolerance;result=''
        for child in children:
            x=c.xform(child,q=True,ws=True,t=True)[0]
            if center==(-tolerance<x<tolerance):result=child;break
        leaf=self._leaf(joint)
        for parent_token,child_token in (('Head','Head'),('Ankle','Toes'),('Toes','Toes'),('Root','Spine')):
            if parent_token in leaf:
                for child in children:
                    if child_token in self._leaf(child):result=child
        if leaf.startswith('Wrist_'):
            for child in children:
                if self._leaf(child).startswith('MiddleFinger1_'):result=child
        return result

    def _fit_heel(self,joint):
        c=self.cmds;fit_joint=self._name(self._leaf(joint)[:-2])
        if 'Ankle' not in self._leaf(joint) or not c.objExists(fit_joint):return None
        result=None
        for child in c.listRelatives(fit_joint,children=True,fullPath=True) or []:
            label=(str(c.getAttr(child+'.otherType') or '') if c.objExists(child+'.drawLabel') and c.getAttr(child+'.drawLabel') and c.getAttr(child+'.type')==18 else '')
            if 'Heel' in label:result=child
        if result:
            point=c.xform(result,q=True,ws=True,t=True)
            return (point[0]*(-1 if self._leaf(joint).endswith('_L') else 1),point[1],point[2])
        return None

    def capture_mannequin_input(self):
        c=self.cmds;deform=self._name('DeformSet')
        if not c.objExists(deform):raise ValueError('Mannequin 缺少 DeformSet')
        # Keep Maya's set member ordering, including the source side order.
        joints=[node for node in c.sets(deform,q=True) or [] if c.nodeType(node)=='joint']
        fit=self._name('FitSkeleton');tolerance=.01*(c.getAttr(fit+'.scaleX') if c.objExists(fit) else 1.)
        segments=[]
        for joint in joints:
            child=self._rla_child(joint,tolerance)
            if not child or re.search(r'Part\d',self._leaf(joint)):continue
            while child and re.search(r'Part\d',self._leaf(child)):
                children=c.listRelatives(child,children=True,type='joint',fullPath=True) or []
                child=children[0] if children else ''
            if not child:raise ValueError('Mannequin Part 链缺少子关节：'+joint)
            segments.append(MannequinSegment(self._leaf(joint),self._leaf(child),
                tuple(c.xform(joint,q=True,ws=True,t=True)),tuple(c.xform(child,q=True,ws=True,t=True)),self._fit_heel(joint)))
        return tuple(segments),float(c.getAttr(self._main()+'.height'))

    def preflight_mannequin(self,plan):
        c=self.cmds
        if not c.objExists(self._name('Geometry')):raise ValueError('Mannequin 缺少 Geometry')
        if c.objExists(self._name('MannequinGeometry')):raise ValueError('MannequinGeometry 已存在')
        for item in plan:
            if not c.objExists(self._name(item.joint)):raise ValueError('Mannequin 来源关节丢失：'+item.joint)
            if c.objExists(self._name(item.name)):raise ValueError('Mannequin 名称已占用：'+item.name)
        self._asset=geometry_asset()

    def _place_piece(self,mesh,piece):
        c=self.cmds;joint=self._name(piece.joint)
        if piece.source=='Mannequin_Foot':
            holder=c.createNode('transform',name=self._name('AdvPy_MannequinFootTarget'))
            try:
                center=tuple((a+b)/2 for a,b in zip(piece.start,piece.end))
                c.xform(mesh,ws=True,t=(center[0],0,center[2]))
                c.xform(mesh,os=True,scale=piece.scale)
                mesh=c.parent(mesh,self._name('MannequinGeometry'))[0]
                c.xform(holder,ws=True,t=(piece.end[0],0,piece.end[2]))
                c.delete(c.aimConstraint(holder,mesh,offset=(0,0,0),weight=1,
                    aimVector=(0,0,1),upVector=(0,1,0),worldUpType='vector',worldUpVector=(0,1,0)))
            finally:
                if c.objExists(holder):c.delete(holder)
        else:
            c.xform(mesh,os=True,scale=piece.scale)
            if piece.source=='Mannequin_Limb' and piece.joint.endswith('_L'):
                c.polyNormal(mesh,normalMode=0,userNormalMode=0,constructionHistory=False)
            constraint=c.parentConstraint(joint,mesh)[0]
            c.setAttr(constraint+'.target[0].targetOffsetRotate',*self._source_offset(joint),type='float3')
            c.delete(constraint)
            mesh=c.parent(mesh,self._name('MannequinGeometry'))[0]
        try:c.makeIdentity(mesh,apply=True,translate=False,rotate=False,scale=True)
        except RuntimeError:pass  # original catchQuiet
        if piece.source=='Mannequin_Limb':
            for shape in c.listRelatives(mesh,shapes=True,noIntermediate=True,type='mesh') or []:c.setAttr(shape+'.opposite',False)
        return mesh

    def create_mannequin(self,plan):
        c=self.cmds;temporary='AdvPyMannequinTemplate_'+uuid4().hex[:12]
        imported=c.file(str(self._asset),i=True,namespace=temporary,returnNewNodes=True,ignoreVersion=True)
        imported_ids=tuple(c.ls(imported,uuid=True))
        try:
            root=c.createNode('transform',name=self._name('MannequinGeometry'))
            c.parent(root,self._name('Geometry'))
            layer=self._name('Mannequin')
            if not c.objExists(layer):
                c.createDisplayLayer(name=layer,empty=True);c.setAttr(layer+'.color',24);c.setAttr(layer+'.displayType',2)
                c.editDisplayLayerMembers(layer,root,noRecurse=True)
            c.setAttr(temporary+':Mannequin_Geometry.visibility',False)
            c.setAttr(temporary+':Skeleton_Geometry.visibility',False)
            for template in c.listRelatives(temporary+':Mannequin_Geometry',children=True,type='transform') or []:c.setAttr(template+'.visibility',True)
            self._mannequin_created=[]
            for piece in plan:
                mesh=c.duplicate(temporary+':'+piece.source,name=self._name(piece.name))[0]
                self._take_ownership(mesh,temporary)
                mesh=self._place_piece(mesh,piece)
                c.select(self._name(piece.joint),mesh,replace=True)
                skin=c.skinCluster(toSelectedBones=True,maximumInfluences=3,dropoffRate=4,removeUnusedInfluence=False)[0]
                self._mannequin_created.append((mesh,skin));c.refresh()
            for name in ('shaderMannequin','shaderMannequinSG'):
                if c.objExists(self._name(name)):c.delete(self._name(name))
            shader=c.shadingNode('lambert',asShader=True,name=self._name('shaderMannequin'))
            sg=c.sets(renderable=True,noSurfaceShader=True,empty=True,name=self._name('shaderMannequinSG'))
            c.connectAttr(shader+'.outColor',sg+'.surfaceShader',force=True)
            c.setAttr(shader+'.color',.78,.63,.42,type='float3')
            c.setAttr(shader+'.ambientColor',.53,.42,.25,type='double3')
            c.sets(root,edit=True,forceElement=sg);c.select(clear=True)
            return len(self._mannequin_created)
        finally:
            originals=c.ls(imported_ids,long=True) or []
            if originals:c.delete(originals)
            if c.namespace(exists=temporary):c.namespace(removeNamespace=temporary,mergeNamespaceWithRoot=True)

    def capture_mannequin(self,count):
        c=self.cmds;root=self._name('MannequinGeometry');layer=self._name('Mannequin')
        return (count==len(self._mannequin_created) and c.objExists(root) and c.objExists(layer)
            and c.objExists(self._name('shaderMannequinSG')) and all(c.objExists(mesh) and c.objExists(skin)
            and skin in (c.listHistory(mesh) or []) for mesh,skin in self._mannequin_created))

    def mannequin_exists(self):
        return any(self.cmds.objExists(self._name(name)) for name in ('MannequinGeometry','Mannequin'))

    def delete_mannequin(self):
        # Original delete deliberately leaves shaderMannequin and its SG.
        for name in ('MannequinGeometry','Mannequin_Geometry','Mannequin','wood','woodSG','woodShader'):
            node=self._name(name)
            if self.cmds.objExists(node):self.cmds.delete(node)
