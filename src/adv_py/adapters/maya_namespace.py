"""Explicit command boundary for one character's logical scene.

Only declared node arguments/results are mapped. Attribute values, JSON,
filenames, tangent names, labels and node types are never rewritten.
"""
from contextlib import contextmanager

from adv_py.core.character_identity import CharacterIdentity, SHARED_NODES
from adv_py.core.character_registry import CharacterRegistryError

_NODE_ARGS = frozenset('ls objExists nodeType listRelatives listConnections listHistory referenceQuery lockNode xform delete deleteAttr rename parent connectAttr disconnectAttr isConnected connectionInfo getAttr addAttr attributeQuery joint circle makeIdentity exactWorldBoundingBox pointPosition polyEvaluate keyframe keyTangent setKeyframe skinCluster skinPercent orientConstraint parentConstraint pointConstraint scaleConstraint poleVectorConstraint ikHandle polyUnite'.split())
_NODE_RESULTS = frozenset('listRelatives listConnections listHistory rename parent createNode joint circle skinCluster orientConstraint parentConstraint pointConstraint scaleConstraint poleVectorConstraint ikHandle polyCylinder polyCube polyUnite'.split())
_GLOBAL = frozenset('currentTime currentUnit upAxis undoInfo undo file pluginInfo loadPlugin allNodeTypes'.split())
_READ = frozenset('ls listAttr objExists nodeType listRelatives listConnections listHistory referenceQuery connectionInfo getAttr attributeQuery isConnected exactWorldBoundingBox pointPosition polyEvaluate'.split())
_CREATE = frozenset('createNode joint circle ikHandle skinCluster orientConstraint parentConstraint pointConstraint scaleConstraint poleVectorConstraint polyCylinder polyCube polyUnite setKeyframe'.split())
_NODE_ARGS |= {'aimConstraint'}
_NODE_RESULTS |= {'aimConstraint'}
_CREATE |= {'aimConstraint'}


class MayaCharacterCommands:
    def __init__(self,commands,namespace):
        self.identity=CharacterIdentity(namespace)
        self.raw=commands
        if commands.namespace(query=True,relativeNames=True):
            raise CharacterRegistryError('角色适配要求 Maya relativeNames 关闭')
        if namespace and not commands.namespace(exists=namespace):
            raise CharacterRegistryError('角色命名空间不存在：'+namespace)

    def _map(self,value,fn):
        if isinstance(value,str):return fn(value)
        if isinstance(value,(tuple,list)):return type(value)(self._map(v,fn) for v in value)
        return value

    @contextmanager
    def _creation_namespace(self):
        c=self.raw
        previous=c.namespaceInfo(currentNamespace=True,absoluteName=True)
        target=':'+self.identity.namespace
        try:
            # These commands must remain in the same Undo chunk as creation:
            # Maya replays some node creation names relative to current namespace.
            c.namespace(setNamespace=target)
            yield
        finally:c.namespace(setNamespace=previous)

    def __getattr__(self,name):
        if name in _GLOBAL:return getattr(self.raw,name)
        if name not in _NODE_ARGS|_NODE_RESULTS|{'setAttr','select','listAttr'}:
            raise AttributeError('角色命名空间边界尚未声明命令：'+name)
        def call(*args,**kwargs):
            c=self.raw;identity=self.identity
            query=bool(kwargs.get('query',kwargs.get('q',False)))
            args=list(args);kwargs=dict(kwargs)
            addresses=[]
            default_solver=None
            def address(value):
                def convert(item):
                    actual=identity.to_scene(item)
                    if actual and not actual.startswith(('|',':')):actual=':'+actual
                    addresses.append(actual);return actual
                return self._map(value,convert)
            if name=='setAttr':
                if args:args[0]=address(args[0])
            elif name=='attributeQuery':
                pass  # First positional argument is an attribute identifier.
            elif name=='createNode':
                pass  # First positional argument is a node type.
            elif name in _NODE_ARGS or name in ('select','listAttr'):
                args=[address(a) for a in args]
            for flag in ('name','n','parent','p','node','startJoint','sj','endEffector','ee','worldUpObject'):
                if flag in kwargs and isinstance(kwargs[flag],str):kwargs[flag]=address(kwargs[flag])
            if name=='ikHandle' and isinstance(kwargs.get('solver'),str) and kwargs['solver'] not in SHARED_NODES:
                kwargs['solver']=identity.to_scene(kwargs['solver']).lstrip(':')
            elif name=='ikHandle' and not query and kwargs.get('solver') in SHARED_NODES:
                solver=kwargs['solver']
                # Maya lazily creates the default solver in the active namespace
                # and may then reuse that solver for every subsequent character.
                # Install the shared default explicitly in the root namespace.
                default_solver=solver
                kwargs['solver']=solver
            if name=='skinPercent':
                for flag in ('transform','t'):
                    if isinstance(kwargs.get(flag),str):kwargs[flag]=address(kwargs[flag])
                for flag in ('transformValue','tv'):
                    if flag in kwargs:kwargs[flag]=[(address(p),v) for p,v in kwargs[flag]]
            readonly=query or name in _READ or (name=='lockNode' and kwargs.get('query',kwargs.get('q')))
            if not readonly and name!='select':
                for item in addresses:
                    node=item.split('.',1)[0]
                    if not identity.owns(node) and not (name=='ikHandle' and node.lstrip(':') in SHARED_NODES):
                        raise CharacterRegistryError('拒绝写入目标角色之外的节点：'+item)
                if name in ('delete','parent','rename','makeIdentity') and not args:
                    raise CharacterRegistryError('角色写操作必须显式指定节点，不使用当前选择')
            if name=='ikHandle' and not query:
                # The first solver-system query lazily creates all default
                # solvers, outside normal node Undo. Initialize at scene root
                # before entering a character namespace, including after reopen.
                previous=c.namespaceInfo(currentNamespace=True,absoluteName=True)
                try:
                    c.namespace(setNamespace=':')
                    c.ikSystem(query=True,solverTypes=True)
                finally:c.namespace(setNamespace=previous)
            if default_solver and not c.objExists(':'+default_solver):
                c.createNode(default_solver,name=':'+default_solver,skipSelect=True)
            # Scene-wide discovery is scoped before UUID conversion, so Undo
            # checkpoints never touch another character's transforms.
            if name=='ls':
                selected=kwargs.get('selection',kwargs.get('sl',False))
                uuids=kwargs.pop('uuid',False)
                result=c.ls(*args,**kwargs) or []
                if not args and not selected and kwargs.get('type')!='animLayer':
                    result=[p for p in result if identity.owns(p)]
                if uuids:return c.ls(result,uuid=True) or [] if result else []
                return self._map(result,identity.to_local)
            with self._creation_namespace() if name in _CREATE and not query else _unchanged():
                result=getattr(c,name)(*args,**kwargs)
            if name=='connectionInfo' and (kwargs.get('sourceFromDestination') or kwargs.get('sfd') or
                    kwargs.get('destinationFromSource') or kwargs.get('dfs')):
                return self._map(result,identity.to_local)
            if name in _NODE_RESULTS:
                # Constraint weight aliases are attribute identifiers, not nodes.
                if query and (kwargs.get('weightAliasList') or kwargs.get('wal')):return result
                return self._map(result,identity.to_local)
            return result
        return call


@contextmanager
def _unchanged():
    yield
