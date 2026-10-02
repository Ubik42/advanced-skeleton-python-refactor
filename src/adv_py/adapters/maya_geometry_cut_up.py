"""Source CutUp: ControlMeshes face dispatch, local Shapes and Body constraints."""
from adv_py.core.geometry_cut_up import CutUpMeshPlan
from .maya_geometry_driven import MayaDrivenGeometryHost
from .maya_geometry_control_mapping import SourceGeometryControlMapping

class MayaGeometryCutUpHost(MayaDrivenGeometryHost):
    def __init__(self,namespace=''):
        super().__init__(namespace);self._created=[];self._pending=[];self._control_roles={}

    def capture_cut_up_inputs(self,*,cut_up=True):
        from maya.api import OpenMaya as om,OpenMayaAnim as oma
        c=self.cmds;selected=c.ls(selection=True,long=True) or []
        if not selected or any('.' in node for node in selected):raise ValueError('请选择已蒙皮的网格对象')
        mapping=SourceGeometryControlMapping(self);self._mapping=mapping;rows=[]
        for mesh in dict.fromkeys(self._mesh(node) for node in selected):
            history=c.listHistory(mesh,pruneDagObjects=True,interestLevel=2) or []
            skins=[node for node in history if c.nodeType(node)=='skinCluster']
            if not skins:raise ValueError('CutUp 来源没有 SkinCluster：'+mesh)
            skin=skins[-1]
            selection=om.MSelectionList();selection.add(mesh);path=selection.getDagPath(0);path.extendToShape()
            fn=om.MFnMesh(path)
            selection=om.MSelectionList();selection.add(skin);skin_fn=oma.MFnSkinCluster(selection.getDependNode(0))
            api_influences=tuple(node.fullPathName() for node in skin_fn.influenceObjects())
            influences=tuple(c.ls(node,long=True)[0] for node in c.listConnections(skin+'.matrix') or [])
            order=[api_influences.index(node) for node in influences]
            component=om.MFnSingleIndexedComponent();obj=component.create(om.MFn.kMeshVertComponent)
            component.addElements(range(fn.numVertices));flat,width=skin_fn.getWeights(path,obj)
            weights=tuple(tuple(float(flat[vertex*width+index]) for index in order) for vertex in range(fn.numVertices))
            faces=[];eligible=[]
            for face in range(fn.numPolygons):
                vertices=c.ls(c.polyListComponentConversion(mesh+f'.f[{face}]',fromFace=True,toVertex=True),flatten=True) or []
                faces.append(tuple(int(vertex.rsplit('[',1)[1][:-1]) for vertex in vertices))
                queried=c.skinPercent(skin,vertices,ignoreBelow=.001,query=True,transform=None) or []
                eligible.append(tuple(influences.index(c.ls(joint,long=True)[0]) for joint in queried))
            anchors=tuple(mapping.anchor(joint,cut_up=cut_up) for joint in influences)
            for joint,control in zip(influences,anchors):
                if control:
                    fk=mapping.fk(joint)
                    if fk and self._leaf(fk)==self._leaf(control):self._control_roles[control]=self._leaf(joint)
            rows.append((mesh,influences,tuple(faces),weights,anchors,tuple(eligible)))
        return tuple(rows)

    def preflight_cut_up(self,plans):
        if not plans:raise ValueError('没有可创建的 CutUp 输入')
        if not self.cmds.objExists(self._name('Geometry')):raise ValueError('角色没有 Geometry 组')
        for plan in plans:
            for piece in plan.pieces:
                if not self.cmds.objExists(piece.joint):raise ValueError('CutUp 控制来源丢失：'+piece.joint)

    def _main(self):
        for name in ('Main','AdvPy_Global'):
            if self.cmds.objExists(self._name(name)):return self._name(name)
        raise ValueError('CutUp 缺少主控制器')

    def create_cut_up(self,plan):
        from .maya_control_mesh import MayaControlMeshHost
        from adv_py.core.control_mesh import ControlMeshSource,plan_control_mesh
        c=self.cmds;group,layer=self.ensure_geometry_group('CutUp',29)
        c.editDisplayLayerMembers(layer,group,noRecurse=True)
        helper=MayaControlMeshHost();helper._in_transaction=True
        source=c.listRelatives(plan.mesh,shapes=True,noIntermediate=True,type='mesh',fullPath=True)[0]
        try:
            for piece in plan.pieces:
                item=plan_control_mesh(ControlMeshSource(source,piece.joint,self._main(),piece.faces,plan.face_count),
                                       helper.existing_control_mesh_names())[0]
                helper.create_control_mesh(item);self._pending.append(item.shape_name)
        finally:helper._in_transaction=False
        return len(plan.pieces)

    def _joint_for_control(self,control):
        c=self.cmds
        if c.nodeType(control)=='joint':return control,self._leaf(control)
        leaf=self._leaf(control);joint=self._control_roles.get(control)
        if joint is None:
            for source,fk in self._mapping.bindings.items():
                if self._leaf(fk)==leaf:joint=source;break
        if joint is None:joint=leaf[2:]
        return self._name(joint),'FK'+joint if self._mapping.fk(joint) else leaf

    def _group(self,control):
        from .maya_body import MayaBodyBuildHost
        from adv_py.core.body_parent_constraint import plan_body_parent_constraint
        c=self.cmds;joint,semantic=self._joint_for_control(control)
        if not c.objExists(joint):raise ValueError('CutUp 找不到绑定关节：'+joint)
        stem,separator,side=semantic.rpartition('_');stem=stem if separator else semantic;side='_'+side if separator else ''
        group=self._name(stem+'CutUp'+side)
        if c.objExists(group):return group,stem,side
        group=c.createNode('transform',name=group,parent=joint)
        fk=self._mapping.fk(joint)
        if fk:c.delete(c.orientConstraint(fk,group))
        group=c.parent(group,self._name('CutUpGeometry'))[0]
        fit=self._name('FitSkeleton')
        helper=MayaBodyBuildHost(namespace=self.namespace,use_offset_parent_matrix=bool(
            c.getAttr(fit+'.useOffsetParentMatrix')) if c.objExists(fit+'.useOffsetParentMatrix') else False)
        helper._transaction_active=True
        try:
            driver=helper._cmds.identity.to_local(c.ls(joint,long=True)[0])
            driven=helper._cmds.identity.to_local(c.ls(group,long=True)[0])
            plan=plan_body_parent_constraint(helper.capture_parent_constraint_input(driver,driven,True))
            helper.preflight_parent_constraint(plan);helper.create_parent_constraint(plan)
        finally:helper._transaction_active=False
        return group,stem,side

    def finalize_cut_up(self,plans):
        c=self.cmds;self._created=[]
        shapes=c.ls(self._name('*MeshCtrl*'),type='mesh',noIntermediate=True) or []
        for shape in shapes:
            control=c.listRelatives(shape,parent=True,fullPath=True)[0]
            group,stem,side=self._group(control)
            for index in range(1,99):
                name=self._name(f'{stem}CutUp{index}{side}')
                if not c.objExists(name):break
            piece=c.createNode('transform',name=name,parent=group)
            shape=c.parent(shape,piece,shape=True,relative=True)[0]
            shape=c.rename(shape,self._name(self._leaf(piece)+'Shape'))
            c.delete(piece,constructionHistory=True)
            self._created.append((piece,group,c.polyEvaluate(piece,face=True)))
        c.select(clear=True);return len(self._created)

    def capture_cut_up(self,plans):
        c=self.cmds
        if len(self._created)<sum(len(plan.pieces) for plan in plans):return False
        for piece,group,count in self._created:
            if not c.objExists(piece) or not c.objExists(group):return False
            if c.polyEvaluate(piece,face=True)!=count:return False
            if any(c.nodeType(node)=='skinCluster' for node in c.listHistory(piece) or []):return False
            if not c.listConnections(group,source=True,destination=False,type='parentConstraint') and not c.connectionInfo(group+'.offsetParentMatrix',isDestination=True):return False
        return self.cut_up_exists()

    def cut_up_exists(self):return any(self.cmds.objExists(self._name(name)) for name in ('CutUp','CutUpGeometry'))

    def delete_cut_up(self):
        c=self.cmds;layer=self._name('CutUp')
        if not c.objExists(layer):return
        members=c.listConnections(layer+'.drawInfo') or []
        if members:c.delete(members)
        c.delete(layer)
        if c.objExists(self._name('CutUpGeometry')):c.delete(self._name('CutUpGeometry'))
