"""Read-only deletion boundary audit against a freshly built replacement graph.

Namespace membership alone never establishes ownership. Automatic root-level
unit conversions are paired by their exclusive input/output boundary.
"""
from hashlib import sha256

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.character_preservation import RebuildOwnership
from .maya_character_preservation import connections


def _curve_topology(host,node):
    from maya.api import OpenMaya as om
    selection=om.MSelectionList();selection.add(host.scene_address(node))
    curve=om.MFnNurbsCurve(selection.getDagPath(0))
    if any(abs(point.w-1.)>1e-12 for point in curve.cvPositions(om.MSpace.kObject)):
        raise CharacterRegistryError('有理控制曲线需要权重迁移协议：'+node)
    return tuple(curve.knots())


def _graph(host,names):
    c=host._cmds
    nodes={name:name for name in names}
    edges=set()
    for name in names:edges.update(connections(host,name))
    outside={p.split('.',1)[0] for edge in edges for p in edge}-set(names)
    for node in sorted(outside):
        if c.nodeType(node)!='unitConversion':continue
        links=connections(host,node)
        # Only a conversion entirely between known rig nodes is owned. A
        # conversion shared with an external consumer must block the audit.
        peers={p.split('.',1)[0] for edge in links for p in edge}-{node}
        if not peers or not peers<=set(names):continue
        incoming=tuple(sorted(a for a,b in links if b==node+'.input'))
        outgoing=tuple(sorted(b for a,b in links if a==node+'.output'))
        if len(incoming)!=1 or not outgoing:continue
        role='@conversion:'+sha256(repr((incoming,outgoing)).encode('utf8')).hexdigest()
        if role in nodes:raise CharacterRegistryError('单位转换归属存在歧义')
        nodes[role]=node
        edges.update(links)
    aliases={node:role for role,node in nodes.items()}
    def normalize(plug):
        node,attr=plug.split('.',1)
        return aliases.get(node,node)+'.'+attr
    return nodes,tuple(sorted((normalize(a),normalize(b)) for a,b in edges))


def audit(host,staged):
    """Reject unhandled connections or children before any deletion is possible."""
    from .maya_body import MayaBodyBuildHost
    target=MayaBodyBuildHost(namespace=staged.namespace)
    reg=target.read_character_registration()
    fit=reg.container
    names=tuple(n for n in target._cmds.ls(long=True)
                if not (n==fit or n.startswith(fit+'|')))
    # Audit applies to the pristine stage, before preserved curves move there.
    for node in names:
        if target._cmds.nodeType(node).startswith('animCurve'):
            raise CharacterRegistryError('所有权审计需要尚未交接动画的暂存角色')
        if not host._cmds.objExists(node):
            raise CharacterRegistryError('原 Rig 缺少暂存结构节点：'+node)
    old_nodes,old_edges=_graph(host,names)
    new_nodes,new_edges=_graph(target,names)
    if set(old_nodes)!=set(new_nodes):
        raise CharacterRegistryError('新旧 Rig 的独占单位转换边界不一致')
    rows=[];shapes=[]
    original=staged.original
    extensions={row.path for row in original.extensions}
    properties={row.path:{a[0] for a in row.attributes} for row in original.properties}
    for role in sorted(old_nodes):
        old,new=old_nodes[role],new_nodes[role]
        a,b=host._cmds,target._cmds
        kind=a.nodeType(old)
        if kind!=b.nodeType(new):raise CharacterRegistryError('新旧 Rig 节点类型不同：'+role)
        if a.referenceQuery(old,isNodeReferenced=True) or any(a.lockNode(old,q=True,lock=True) or []):
            raise CharacterRegistryError('旧 Rig 节点被引用或锁定：'+old)
        extra=set(a.listAttr(old,userDefined=True) or [])-set(b.listAttr(new,userDefined=True) or [])
        if extra-properties.get(old,set()):
            raise CharacterRegistryError('旧 Rig 节点有未采集的附加属性：'+old)
        if kind=='unitConversion' and a.getAttr(old+'.conversionFactor')!=b.getAttr(new+'.conversionFactor'):
            raise CharacterRegistryError('单位转换系数被修改：'+old)
        if kind=='nurbsCurve':
            shape_a=a.xform(old+'.cv[*]',q=True,objectSpace=True,t=True) or []
            shape_b=b.xform(new+'.cv[*]',q=True,objectSpace=True,t=True) or []
            if (len(shape_a)!=len(shape_b)
                    or _curve_topology(host,old)!=_curve_topology(target,new)
                    or any(a.getAttr(old+'.'+attr)!=b.getAttr(new+'.'+attr) for attr in ('degree','form','spans'))):
                raise CharacterRegistryError('控制形状拓扑不同，需要显式形状迁移：'+old)
            settings=[]
            for attr in ('overrideEnabled','overrideDisplayType','overrideLevelOfDetail','overrideShading',
                         'overrideTexturing','overridePlayback','overrideVisibility','overrideColor',
                         'overrideRGBColors','overrideColorRGB','lineWidth'):
                if not a.objExists(old+'.'+attr):continue
                value=a.getAttr(old+'.'+attr)
                if isinstance(value,list):value=tuple(value[0])
                settings.append((attr,value,bool(a.getAttr(old+'.'+attr,lock=True))))
            shapes.append((role,tuple(shape_a),tuple(settings),_curve_topology(host,old)))
        if 'dagNode' in (a.nodeType(old,inherited=True) or []):
            children=set(a.listRelatives(old,children=True,fullPath=True) or [])
            if children-set(old_nodes.values())-extensions:
                raise CharacterRegistryError('旧 Rig 存在未声明保留的子节点：'+old)
        rows.append((role,a.ls(old,uuid=True)[0],b.ls(new,uuid=True)[0],kind))
    permitted={pair for row in (*original.skins,*original.extensions,*staged.custom_properties) for pair in row.connections}
    for curve in original.curves:
        permitted.update((curve.node+'.output',plug) for plug in curve.outputs)
    # Bind-pose records belong to retained skin, not to the rig being deleted.
    for skin in original.skins:
        for pose in host._cmds.listConnections(skin.node+'.bindPose',s=True,d=False) or []:
            if host._cmds.nodeType(pose)!='dagPose':raise CharacterRegistryError('蒙皮绑定姿态类型无效')
            permitted.update(connections(host,pose))
    extra=set(old_edges)-set(new_edges)-permitted
    missing=set(new_edges)-set(old_edges)
    if extra or missing:
        raise CharacterRegistryError('旧 Rig 连接不符合重建边界：'+repr((sorted(extra)[:3],sorted(missing)[:3])))
    result=RebuildOwnership(tuple(rows),old_edges,tuple(shapes))
    if staged.ownership is not None and result!=staged.ownership:
        raise CharacterRegistryError('暂存后的节点归属、形状或连接发生变化')
    return result


def transfer_shapes(target,ownership):
    if ownership is None:return
    c=target._cmds
    for node,points,settings,knots in ownership.shapes:
        for index in range(len(points)//3):
            c.xform(node+f'.cv[{index}]',objectSpace=True,t=points[index*3:index*3+3])
        for attribute,value,locked in settings:
            plug=node+'.'+attribute
            c.setAttr(plug,lock=False)
            if isinstance(value,tuple):c.setAttr(plug,*value,type='double3')
            else:c.setAttr(plug,value)
            c.setAttr(plug,lock=locked)


def verify_shapes(target,ownership):
    if ownership is None:return
    c=target._cmds
    for node,points,settings,knots in ownership.shapes:
        current=tuple(c.xform(node+'.cv[*]',q=True,objectSpace=True,t=True) or [])
        if (len(current)!=len(points) or any(abs(a-b)>1e-8 for a,b in zip(current,points))
                or _curve_topology(target,node)!=knots):
            raise RuntimeError('控制形状保留复检失败：'+node)
        for attr,value,locked in settings:
            actual=c.getAttr(node+'.'+attr)
            if isinstance(actual,list):actual=tuple(actual[0])
            if actual!=value or bool(c.getAttr(node+'.'+attr,lock=True))!=locked:
                raise RuntimeError('控制形状显示属性保留复检失败：'+node+'.'+attr)
