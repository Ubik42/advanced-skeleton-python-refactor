"""Source geometry helpers shared by Boolean and Warp scene boundaries."""
from .maya_geometry_poly_boxes import MayaPolyBoxesHost

from .maya_original_transform_channels import lock_original_transform_channels

class MayaDrivenGeometryHost(MayaPolyBoxesHost):
    def refresh_hidden_boxes(self, *, refresh_after_hide):
        c=self.cmds;plug=self._name('BoxesGeometry')+'.visibility'
        if not c.getAttr(plug):
            # asHidePolyBoxes toggles the visibility lock along with visibility.
            c.setAttr(plug,lock=False);c.setAttr(plug,True);c.refresh()
            c.setAttr(plug,False);c.setAttr(plug,lock=True)
            if refresh_after_hide:c.refresh()

    def source_box_names(self):
        c=self.cmds
        group=self._name('BoxesGeometry')
        if not c.objExists(group):raise ValueError('请先创建 PolyBoxes')
        return tuple(self._leaf(node) for node in c.listRelatives(group,allDescendents=True,type='transform') or []
                     if c.listRelatives(node,shapes=True,noIntermediate=True))

    def all_box_names(self):return self.source_box_names()

    def unlock_geometry_transform(self,node):
        c=self.cmds
        lock_original_transform_channels(c, node)

    def capture_selected_meshes(self):
        c=self.cmds
        selected=c.ls(selection=True,long=True) or []
        if not selected or any('.' in node for node in selected):
            raise ValueError('请选择多边形网格对象')
        meshes=[]
        for node in selected:
            if c.nodeType(node)=='mesh':node=c.listRelatives(node,parent=True,fullPath=True)[0]
            if c.nodeType(node)!='transform' or not c.listRelatives(node,shapes=True,noIntermediate=True,type='mesh'):
                raise ValueError('选择项不是多边形网格：'+node)
            meshes.append(node)
        return tuple(dict.fromkeys(meshes))

    def ensure_geometry_group(self,label,color):
        c=self.cmds;layer=self._name(label);group=self._name(label+'Geometry')
        if not c.objExists(layer):
            c.createDisplayLayer(empty=True,name=layer)
            c.setAttr(layer+'.color',color);c.setAttr(layer+'.displayType',2)
        if not c.objExists(group):c.createNode('transform',name=group,parent=self._name('Geometry'))
        return group,layer

    def hide_geometry_sources(self,plan):
        c=self.cmds
        nodes=list(dict.fromkeys(item.source for item in plan))
        if c.objExists(self._name('PolyBoxes')):nodes.append(self._name('PolyBoxes'))
        states={node:c.getAttr(node+'.visibility') for node in nodes}
        for node in nodes:c.setAttr(node+'.visibility',0)
        return states

    def restore_geometry_visibility(self,states):
        for node,value in states.items():
            if self.cmds.objExists(node):self.cmds.setAttr(node+'.visibility',value)

    def assert_driven_mesh(self,node,group):
        c=self.cmds
        return (c.objExists(node) and c.listRelatives(node,shapes=True,noIntermediate=True,type='mesh')
                and self._leaf(c.listRelatives(node,parent=True)[0])==self._leaf(group)
                and c.listConnections(node,source=True,destination=False,type='parentConstraint')
                and c.listConnections(node,source=True,destination=False,type='scaleConstraint'))

    def delete_geometry_family(self,label,pattern):
        c=self.cmds
        from adv_py.core.character_identity import CharacterIdentity
        identity=CharacterIdentity(self.namespace)
        for node in c.ls(self._name(pattern),type='transform',recursive=True) or []:
            if identity.owns(node) and c.objExists(node):c.delete(node)
        for leaf in (label+'Geometry',label):
            if c.objExists(self._name(leaf)):c.delete(self._name(leaf))
