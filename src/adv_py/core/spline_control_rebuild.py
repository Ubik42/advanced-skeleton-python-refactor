"""Explicit count changes with MEL's surviving-control connection reuse.

The Body and skin binding stay fixed. New controls and receivers are generated
from the requested count; this is not an animation retarget or a promise that
the changed IK graph deforms identically to the old graph.
"""
from dataclasses import dataclass, replace

from .body_spline import BodySplinePlan
from .character_registry import CharacterRegistryError
from .character_preservation import validate_rebuild_layout


def splines(registration):
    return tuple(plan for plan in (registration.spine,
        *registration.additional_spines) if isinstance(plan,BodySplinePlan))


def control_count(plan):
    return 2 if plan.fake_mid_control else len(plan.targets)


@dataclass(frozen=True)
class SplineControlRebuild:
    systems: tuple[tuple[str,int,int], ...]
    affected_names: frozenset[str]
    # Logical original plug -> replacement plug, or no longer generated.
    plugs: tuple[tuple[str,str | None], ...]
    removed_controls: frozenset[str]
    nodes: tuple[tuple[str,str | None], ...] = ()

    def destination(self,plug):
        mapping=dict(self.plugs)
        if plug in mapping:return mapping[plug]
        node,separator,attribute=plug.partition('.')
        target=dict(self.nodes).get(node,node)
        return target+separator+attribute if target is not None else None

    def node_destination(self,node):
        return dict(self.nodes).get(node,node)

    def affects(self,node):
        name=node.rsplit('|',1)[-1].rsplit(':',1)[-1]
        return name in self.affected_names or any(name==stem+'_'+output+'UC'
            for stem in self.affected_names
            for output in ('outputRotateX','outputRotateY','outputRotateZ',
                           'outputTranslateX','outputTranslateY','outputTranslateZ'))


def plan_spline_control_rebuild(before,after,counts):
    old={plan.system_name:plan for plan in splines(before)}
    new={plan.system_name:plan for plan in splines(after)}
    requested=dict(counts)
    if (len(requested)!=len(counts) or not requested
            or requested.keys()-old.keys() or old.keys()!=new.keys()
            or any(type(count) is not int or count<2 for count in requested.values())):
        raise CharacterRegistryError('Spline 数量变更必须指定现有系统和至少 2 的整数')
    changed=[];names=set();controls=set()
    for system,count in requested.items():
        left,right=old[system],new[system]
        if (not left.source_curve_points or control_count(right)!=count
                or left.body_joints!=right.body_joints
                or len(left.lengths)!=len(right.lengths)
                or any(abs(a-b)>1e-6 for a,b in zip(left.lengths,right.lengths))
                or left.source_mode!=right.source_mode):
            raise CharacterRegistryError('Spline 数量变更改变了系统、Body、绑定长度或模式身份')
        if control_count(left)!=count:
            changed.append((system,control_count(left),count))
            names.update(left.node_names);names.update(right.node_names)
            controls.update(left.targets);controls.update(left.sub_targets)
            controls.update(left.extra_targets)
            controls.update(left.cv_controls);controls.update(left.hybrid_controls)
            controls.update(left.cv_extras);controls.update(left.hybrid_extras)
    old_channels={row.key:row for row in before.channels}
    new_channels={row.key:row for row in after.channels}
    # Endpoint-only settings retain their semantic identity even when the
    # numeric end-control name changes. Indexed transforms keep their names.
    endpoint_aliases={}
    for system,_,_ in changed:
        left,right=old[system],new[system]
        for attribute in ('stiff',):
            endpoint_aliases[left.targets[-1]+'.'+attribute]=right.targets[-1]+'.'+attribute
    plugs=[]
    for key,row in old_channels.items():
        target=new_channels.get(key)
        endpoint=endpoint_aliases.get(row.node+'.'+row.attribute)
        if endpoint is not None:
            candidates=[item for item in after.channels
                        if item.node+'.'+item.attribute==endpoint]
            if len(candidates)!=1:
                raise CharacterRegistryError('Spline 末端属性没有唯一的替换通道：'+key)
            target=candidates[0]
        if target is None:
            if row.node not in controls:
                raise CharacterRegistryError('Spline 数量变更删除了其他系统通道：'+key)
            plugs.append((row.node+'.'+row.attribute,None));continue
        if (row.attribute,row.minimum,row.maximum)!=(target.attribute,target.minimum,target.maximum):
            raise CharacterRegistryError('Spline 数量变更改变了通道范围：'+key)
        if row.node!=target.node:
            if row.node not in controls:
                raise CharacterRegistryError('Spline 数量变更重定向了其他系统通道：'+key)
            plugs.append((row.node+'.'+row.attribute,target.node+'.'+target.attribute))
    for key,row in new_channels.items():
        if key not in old_channels and not row.node.rsplit('|',1)[-1] in names:
            raise CharacterRegistryError('Spline 数量变更新增了其他系统通道：'+key)
    # Compare the entire binding/space contract independently of channel
    # additions and removals permitted above. This keeps the ordinary gate.
    validate_rebuild_layout(before,replace(after,channels=before.channels))
    by_leaf={}
    for row in after.nodes:
        by_leaf.setdefault(row.path.rsplit('|',1)[-1],[]).append(row.path)
    nodes=[]
    for row in before.nodes:
        if row.path.rsplit('|',1)[-1] not in names:continue
        matches=by_leaf.get(row.path.rsplit('|',1)[-1],[])
        if len(matches)>1:
            raise CharacterRegistryError('Spline 同名生成节点有多个替换目标：'+row.path)
        target=matches[0] if matches else None
        if target!=row.path:nodes.append((row.path,target))
    return SplineControlRebuild(tuple(changed),frozenset(names),tuple(plugs),
        frozenset(node for node in controls
                  if dict(nodes).get(node,node) is None),tuple(nodes))
