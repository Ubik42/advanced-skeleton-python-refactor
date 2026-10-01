"""Record Maya's implicit native unit conversions as part of owned graphs."""
from dataclasses import replace
from adv_py.core.source_rp_dynamics import SourceRpNode
from adv_py.core.character_registry import CharacterRegistryError


class SourceGraphConnections:
    def __init__(self,host,stem):
        self.host,self.c,self.stem=host,host._cmds,stem
        self.nodes=[]
        self.sources={}
        # Maya may reuse a converter already serving another graph. Renaming
        # it would invalidate that graph's persisted addresses. Only name
        # converters created by this connection owner.
        self.existing_conversions=frozenset(self.c.ls(type='unitConversion') or ())

    def connect(self,source,target):
        self.c.connectAttr(source,target)
        actual=self.c.connectionInfo(target,sourceFromDestination=True)
        if not actual:
            raise CharacterRegistryError('来源原生图连接没有实际输入：'+target)
        name,attr=actual.split('.',1)
        name=self.host._resolve_connected_node(name)
        actual=name+'.'+attr
        if (self.c.nodeType(name)=='unitConversion' and actual!=source
                and name not in self.existing_conversions
                and name not in {node.name for node in self.nodes}):
            incoming=self.c.connectionInfo(name+'.input',sourceFromDestination=True)
            if incoming:
                node,attribute=incoming.split('.',1)
                incoming=self.host._resolve_connected_node(node)+'.'+attribute
            if incoming==source:
                owned=self.stem+'_Units'+str(len(self.nodes))
                if self.host.find_name_collisions(owned):
                    raise CharacterRegistryError('来源原生图单位转换名称被占用')
                name=self.c.rename(name,owned)
                if name!=owned:
                    raise CharacterRegistryError('来源原生图单位转换名称漂移')
                self.nodes.append(SourceRpNode(name,'unitConversion',
                    (('conversionFactor',float(self.c.getAttr(name+'.conversionFactor'))),),
                    ((source,'input'),)))
                actual=name+'.'+attr
        self.sources[target]=actual
        return actual

    def describe_nodes(self,nodes):
        return tuple(replace(node,connections=tuple(
            (self.sources.get(node.name+'.'+attribute,source),attribute)
            for source,attribute in node.connections)) for node in nodes)+tuple(self.nodes)

    def describe_outputs(self,outputs):
        return tuple((self.sources.get(target,source),target) for source,target in outputs)
