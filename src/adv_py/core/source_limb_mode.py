"""Original RP Advanced FKIK controls and automatic/manual visibility.

MEL 81808–81969. The user control keeps 0–10 while the existing solver
boundary consumes the source unitConversion output in 0–1.
"""
from dataclasses import dataclass, fields
from .source_spline_mode import SourceSplineModePlan,source_mode_icon_scale
from .source_fit_identity import source_fit_reference,source_fit_side_sign


@dataclass(frozen=True,slots=True)
class SourceLimbModePlan:
    source_mode: SourceSplineModePlan
    body_joints: tuple[str,...]
    use_offset_parent_matrix: bool
    blend_plug: str
    root_frame: str | None = None
    visibility_targets: tuple[tuple[str,str],...] = ()

    @property
    def mode_plug(self):
        return self.source_mode.control+'.FKIKBlend'

    @property
    def condition(self):
        stem,side=self.source_mode.token.rsplit('_',1)
        return 'FKIKBlend'+stem+'Condition_'+side

    @property
    def side(self):
        return self.source_mode.name.rsplit('_',1)[-1]

    @property
    def visibility_ik(self):return self.condition+'.outColorR'

    @property
    def visibility_fk(self):return self.condition+'.outColorG'


def plan_source_limb_modes(limb,body,hierarchy,instances,root_follow,use_opm,fk):
    by_path={joint.path:joint for joint in body.joints}
    mechanisms={joint.path:joint for joint in limb.mechanisms.joints}
    icon_scale=source_mode_icon_scale(hierarchy)
    rows=[]
    for ik in limb.ik.limbs:
        joints=tuple(mechanisms[path].source_joint for path in ik.chain)
        start,middle,end=(by_path[path] for path in joints)
        parent=start.parent_path
        if parent==body.root:
            parent=root_follow
        elif parent is None:
            parent=start.path
        # Parts are physical parents even when the semantic Body snapshot
        # excludes them. asRlaParent does not fall back to the start joint.
        fit=source_fit_reference(start.name,instances) or start.name.rsplit('_',1)[0]
        mode=SourceSplineModePlan('FKIK'+limb.label+'_'+ik.side.value,
            fit.rsplit('|',1)[-1].rsplit(':',1)[-1],parent,icon_scale,
            ik.source_pole_length,
            start.name.rsplit('_',1)[0],middle.name.rsplit('_',1)[0],
            end.name.rsplit('_',1)[0],source_fit_side_sign(start.name,instances))
        blend=next(side for side in limb.blend.sides if side.side is ik.side)
        frame=next((frame.frame for frame in limb.root_frames if frame.joint==ik.chain[0]),None)
        targets=[('ik',ik.wrist_offset_path),('ik',ik.pole_offset_path)]
        if frame:targets.append(('ik',frame))
        drivers={joint.fk_driver for joint in blend.joints}
        targets.extend(('fk',control.offset_path) for control in fk.controls
            if control.driven_joint in drivers and control.control_path not in fk.hidden_controls)
        rows.append(SourceLimbModePlan(mode,joints,use_opm,
            limb.blend.settings_path+'.'+blend.attribute,frame,tuple(targets)))
    return tuple(rows)


def decode_source_limb_mode(text):
    """Read saved graph identity without recomputing layout from today's Fit."""
    from .character_registry import safe_json,exact,path,identifier,CharacterRegistryError
    raw=exact(safe_json(text),(field.name for field in fields(SourceLimbModePlan)))
    mode=exact(raw['source_mode'],(field.name for field in fields(SourceSplineModePlan)))
    if type(raw['use_offset_parent_matrix']) is not bool:
        raise CharacterRegistryError('来源 RP FKIK OPM 标记无效')
    if not isinstance(raw['body_joints'],list) or len(raw['body_joints'])!=3:
        raise CharacterRegistryError('来源 RP FKIK 骨链必须登记起点、中点与终点')
    if not isinstance(raw['visibility_targets'],list) or not raw['visibility_targets']:
        raise CharacterRegistryError('来源 RP FKIK 显示目标缺失')
    targets=[]
    for row in raw['visibility_targets']:
        if not isinstance(row,list) or len(row)!=2 or row[0] not in ('fk','ik'):
            raise CharacterRegistryError('来源 RP FKIK 显示目标无效')
        targets.append((row[0],path(row[1])))
    if len({node for _,node in targets})!=len(targets):
        raise CharacterRegistryError('来源 RP FKIK 显示目标重复')
    blend=raw['blend_plug']
    if not isinstance(blend,str) or '.' not in blend:
        raise CharacterRegistryError('来源 RP FKIK 内部接口无效')
    node,attribute=blend.rsplit('.',1)
    path(node);identifier(attribute)
    if '.' in attribute:
        raise CharacterRegistryError('来源 RP FKIK 内部属性无效')
    try:
        source_mode=SourceSplineModePlan(**{**mode,'parent_source':path(mode['parent_source'])})
    except (TypeError,ValueError,AttributeError) as exc:
        raise CharacterRegistryError('来源 RP FKIK 控制器保存数据无效') from exc
    root=path(raw['root_frame']) if raw['root_frame'] is not None else None
    if root and ('ik',root) not in targets:
        raise CharacterRegistryError('来源 RP FKIK 起点显示目标缺失')
    joints=tuple(path(node) for node in raw['body_joints'])
    side=source_mode.name.rsplit('_',1)[-1]
    expected=tuple(name+'_'+side for name in
        (source_mode.start_joint,source_mode.middle_joint,source_mode.end_joint))
    if (tuple(node.rsplit('|',1)[-1] for node in joints)!=expected
            or joints[0]==joints[-1] or len(set(joints))<2):
        raise CharacterRegistryError('来源 RP FKIK 骨链名称、侧别或端点无效')
    return SourceLimbModePlan(source_mode,joints,
                              raw['use_offset_parent_matrix'],blend,root,tuple(targets))
