"""Source Boolean intersection and world BlendShape joint-space bake."""
from .maya_geometry_driven import MayaDrivenGeometryHost

class MayaBooleanHost(MayaDrivenGeometryHost):
    def __init__(self,namespace=''):
        super().__init__(namespace);self._created_boolean=()

    def preflight_boolean(self,plan):
        c=self.cmds
        for name in ('Geometry','BoxesGeometry'):
            if not c.objExists(self._name(name)):raise ValueError('Boolean 缺少 '+name)
        for item in plan:
            for node in (item.source,self._name(item.box),self._name(item.joint)):
                if not c.objExists(node):raise ValueError('Boolean 来源已丢失：'+node)
            if not c.getAttr(item.source+'.visibility',settable=True):raise ValueError('来源可见性不可写')
        for name in ('AdvPy_BoolObjectTemp','AdvPy_BoolBoxTemp'):
            if c.objExists(self._name(name)):raise ValueError('Boolean 临时名称已占用')

    def boolean_exists(self):
        return any(self.cmds.objExists(self._name(name)) for name in ('Bool','BoolGeometry'))

    def create_boolean(self,plan):
        c=self.cmds;self.refresh_hidden_boxes(refresh_after_hide=True)
        group,layer=self.ensure_geometry_group('Bool',21)
        states=self.hide_geometry_sources(plan);created=[]
        try:
            c.dgdirty(allPlugs=True)
            for spec in plan:
                # The source allocates a transform, deletes it, and then uses
                # the actual Maya-generated name for this mesh (also on append).
                name=c.createNode('transform',name=self._name(spec.name));c.delete(name)
                obj=c.duplicate(spec.source,name=self._name('AdvPy_BoolObjectTemp'))[0]
                box=c.duplicate(self._name(spec.box),name=self._name('AdvPy_BoolBoxTemp'))[0]
                try:
                    self.unlock_geometry_transform(obj);self.unlock_geometry_transform(box)
                    if c.listRelatives(obj,parent=True):obj=c.parent(obj,world=True)[0]
                    box=c.parent(box,world=True)[0]
                    c.setAttr(obj+'.visibility',0)
                    c.select(obj,box,replace=True);c.refresh()
                    result=c.polyBoolOp(obj,box,name=obj,operation=3,constructionHistory=False)[0]
                finally:
                    for copy in (obj,box):
                        if c.objExists(copy):c.delete(copy)
                world=c.rename(result,name+'WS')
                c.duplicate(world,name=name)
                mesh=name
                joint=self._name(spec.joint)
                c.parent(mesh,joint,relative=True);c.parent(mesh,world=True)
                c.blendShape(world,mesh,frontOfChain=True,origin='world',weight=[(0,1.)])
                c.delete(mesh,constructionHistory=True);c.delete(world)
                if not c.polyEvaluate(mesh,vertex=True):c.delete(mesh);continue
                mesh=c.parent(mesh,group)[0]
                c.parentConstraint(joint,mesh);c.scaleConstraint(joint,mesh)
                c.editDisplayLayerMembers(layer,mesh,noRecurse=True);created.append(mesh)
        finally:self.restore_geometry_visibility(states)
        c.select(clear=True);self._created_boolean=tuple(created)
        return len(created)

    def capture_boolean(self,count):
        c=self.cmds;group=self._name('BoolGeometry');layer=self._name('Bool')
        return (c.objExists(group) and c.objExists(layer) and c.getAttr(layer+'.color')==21
                and c.getAttr(layer+'.displayType')==2 and count==len(self._created_boolean)
                and all(self.assert_driven_mesh(node,group) for node in self._created_boolean))

    def delete_boolean(self):self.delete_geometry_family('Bool','*Bool_*')
