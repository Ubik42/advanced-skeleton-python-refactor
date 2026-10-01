"""Original RP stretchy/antiPop/Pole.lock/volume graph, MEL 82895–83042.

Length spellings intentionally retain the original public ``LenghtN`` names.
The adapter supplies the final solver chain after Part/Inbetween insertion.
"""
from dataclasses import dataclass
from math import isfinite,sqrt


@dataclass(frozen=True,slots=True)
class SourceRpSegment:
    joint: str
    previous: str
    translation: tuple[float,float,float]
    length_attribute: str
    fatness_attribute: str


@dataclass(frozen=True,slots=True)
class SourceRpNode:
    name: str
    kind: str
    values: tuple[tuple[str,float],...] = ()
    connections: tuple[tuple[str,str],...] = ()


@dataclass(frozen=True,slots=True)
class SourceRpDynamicsPlan:
    label: str
    side: str
    control: str
    pole: str
    start_anchor: str
    target_anchor: str
    rest_length: float
    segments: tuple[SourceRpSegment,...]
    nodes: tuple[SourceRpNode,...]
    ratio: str
    volume: str
    normal_curve: str
    anti_pop_curve: str
    outputs: tuple[tuple[str,str],...] = ()


def plan_source_rp_dynamics(label,side,control,pole,start_anchor,target_anchor,
                            global_inverse,global_scale,chain,translations):
    if (len(chain)<3 or len(translations)!=len(chain)-1
            or len(set(chain))!=len(chain)
            or any(len(vector)!=3 or any(not isfinite(v) for v in vector)
                   or sqrt(sum(v*v for v in vector))<=1e-8 for vector in translations)):
        raise ValueError('来源 RP 拉伸要求最终非退化 solver 链')
    stem='AdvPy_'+label+'_RP_'+side
    nodes=[]
    def node(suffix,kind,values=(),edges=()):
        name=stem+'_'+suffix
        nodes.append(SourceRpNode(name,kind,tuple(values),tuple(edges)))
        return name
    def edge(source,target): return (source,target)
    rest=sum(sqrt(sum(v*v for v in vector)) for vector in translations)
    stretch=node('StretchUnit','unitConversion',(('conversionFactor',.1),),
                 (edge(control+'.stretchy','input'),))
    anti=node('AntiPopUnit','unitConversion',(('conversionFactor',.1),),
              (edge(control+'.antiPop','input'),))
    lock=node('PoleLockUnit','unitConversion',(('conversionFactor',.1),),
              (edge(pole+'.lock','input'),))
    start=node('StartMatrix','multMatrix',edges=(
        edge(start_anchor+'.worldMatrix[0]','matrixIn[0]'),edge(global_inverse,'matrixIn[1]')))
    target=node('TargetMatrix','multMatrix',edges=(
        edge(target_anchor+'.worldMatrix[0]','matrixIn[0]'),edge(global_inverse,'matrixIn[1]')))
    distance=node('Distance','distanceBetween',edges=(
        edge(start+'.matrixSum','inMatrix1'),edge(target+'.matrixSum','inMatrix2')))
    normal=stem+'_Normal'
    anti_curve=stem+'_AntiPop'
    nodes.extend((SourceRpNode(normal,'animCurveUU',connections=((distance+'.distance','input'),)),
                  SourceRpNode(anti_curve,'animCurveUU',connections=((distance+'.distance','input'),))))
    anti_blend=node('AntiPopBlend','blendTwoAttr',edges=(
        edge(normal+'.output','input[0]'),edge(anti_curve+'.output','input[1]'),
        edge(anti+'.output','attributesBlender')))
    clamp=node('DistanceClamp','clamp',(('minR',0.),('maxR',rest)),
               (edge(anti_blend+'.output','inputR'),))
    stretch_blend=node('StretchBlend','blendTwoAttr',edges=(
        edge(clamp+'.outputR','input[0]'),edge(anti_blend+'.output','input[1]'),
        edge(stretch+'.output','attributesBlender')))
    ratio=node('Ratio','multiplyDivide',(('operation',2),('input2X',rest)),
               (edge(stretch_blend+'.output','input1X'),))
    volume_unit=node('VolumeUnit','unitConversion',(('conversionFactor',.1),),
                     (edge(control+'.volume','input'),))
    reciprocal=node('VolumeReciprocal','multiplyDivide',(('operation',2),('input1X',1.)),
                    (edge(ratio+'.outputX','input2X'),))
    power=node('VolumePower','multiplyDivide',(('operation',3),('input2X',.5)),
               (edge(reciprocal+'.outputX','input1X'),))
    volume=node('VolumeBlend','blendTwoAttr',(('input[0]',1.),),
                (edge(power+'.outputX','input[1]'),edge(volume_unit+'.output','attributesBlender')))
    segments=[]
    for index,(joint,previous,vector) in enumerate(zip(chain[1:],chain,translations),1):
        length_attribute='Lenght'+str(index)
        fatness_attribute='Fatness'+str(index)
        segments.append(SourceRpSegment(joint,previous,tuple(vector),length_attribute,fatness_attribute))
        length=node('Length'+str(index),'multDoubleLinear',edges=(
            edge(control+'.'+length_attribute,'input1'),edge(ratio+'.outputX','input2')))
        # MEL measures start→Pole for the first bone, Pole→IK for the others.
        lock_target=start_anchor if index==1 else target_anchor
        pole_distance=node('PoleDistance'+str(index),'distanceBetween',edges=(
            edge(pole+'.worldMatrix[0]','inMatrix1'),edge(lock_target+'.worldMatrix[0]','inMatrix2')))
        lock_scale=node('PoleDistanceScale'+str(index),'multiplyDivide',(('operation',2),),
                        (edge(pole_distance+'.distance','input1X'),edge(global_scale,'input2X')))
        magnitude=sqrt(sum(v*v for v in vector))
        lock_ratio=node('PoleDistanceRatio'+str(index),'multiplyDivide',
                        (('operation',2),('input2X',magnitude)),
                        (edge(lock_scale+'.outputX','input1X'),))
        blend=node('PoleLockBlend'+str(index),'blendTwoAttr',edges=(
            edge(length+'.output','input[0]'),edge(lock_ratio+'.outputX','input[1]'),
            edge(lock+'.output','attributesBlender')))
        node('Segment'+str(index),'multiplyDivide',tuple(
            ('input2'+axis,v) for axis,v in zip('XYZ',vector)),tuple(
            edge(blend+'.output','input1'+axis) for axis in 'XYZ'))
        node('Fatness'+str(index),'plusMinusAverage',edges=(
            edge(control+'.'+fatness_attribute,'input1D[0]'),edge(volume+'.output','input1D[1]')))
    return SourceRpDynamicsPlan(label,side,control,pole,start_anchor,target_anchor,rest,
        tuple(segments),tuple(nodes),ratio+'.outputX',volume+'.output',normal,anti_curve,
        tuple((stem+'_Segment'+str(index)+'.output',segment.joint+'.translate')
              for index,segment in enumerate(segments,1)))


def decode_source_rp_dynamics(text):
    from dataclasses import fields
    import re
    from .character_registry import safe_json,exact,path,identifier,finite,vector,CharacterRegistryError
    raw=exact(safe_json(text),(field.name for field in fields(SourceRpDynamicsPlan)))
    nodes=[]
    kinds={'unitConversion','multMatrix','distanceBetween','animCurveUU',
           'blendTwoAttr','clamp','multiplyDivide','multDoubleLinear','plusMinusAverage'}
    def attribute(value):
        if not isinstance(value,str) or re.fullmatch(r'[A-Za-z][A-Za-z0-9]*(?:\[\d+\])?(?:\.[A-Za-z][A-Za-z0-9]*(?:\[\d+\])?)*',value) is None:
            raise CharacterRegistryError('来源 RP 图属性地址无效')
        return value
    def plug(value):
        if not isinstance(value,str) or '.' not in value:
            raise CharacterRegistryError('来源 RP 图连接地址无效')
        node,attr=value.split('.',1)
        path(node) if node.startswith('|') else identifier(node)
        attribute(attr)
        return value
    for row in raw['nodes']:
        exact(row,(field.name for field in fields(SourceRpNode)))
        if row['kind'] not in kinds:
            raise CharacterRegistryError('来源 RP 图节点类型不受支持')
        values=tuple((attribute(attr),finite(value)) for attr,value in row['values'])
        connections=tuple((plug(source),attribute(target)) for source,target in row['connections'])
        if (len({attr for attr,_ in values})!=len(values) or
                len({target for _,target in connections})!=len(connections)):
            raise CharacterRegistryError('来源 RP 图输入字段重复')
        nodes.append(SourceRpNode(identifier(row['name']),row['kind'],values,connections))
    segments=[]
    for row in raw['segments']:
        exact(row,(field.name for field in fields(SourceRpSegment)))
        segments.append(SourceRpSegment(path(row['joint']),path(row['previous']),
            vector(row['translation'],3),identifier(row['length_attribute']),
            identifier(row['fatness_attribute'])))
    if (not 2<=len(segments)<=255 or not nodes or len(nodes)>4096
            or len({node.name for node in nodes})!=len(nodes)
            or raw['side'] not in ('R','L','M')):
        raise CharacterRegistryError('来源 RP 图骨段、节点或侧别无效')
    plan=SourceRpDynamicsPlan(identifier(raw['label']),raw['side'],path(raw['control']),
        path(raw['pole']),path(raw['start_anchor']),path(raw['target_anchor']),
        finite(raw['rest_length']),tuple(segments),tuple(nodes),plug(raw['ratio']),
        plug(raw['volume']),identifier(raw['normal_curve']),identifier(raw['anti_pop_curve']),
        tuple((plug(source),plug(destination)) for source,destination in raw['outputs']))
    total=sum(sqrt(sum(v*v for v in row.translation)) for row in segments)
    if (plan.rest_length<=0 or abs(total-plan.rest_length)>1e-6
            or len({target for _,target in plan.outputs})!=len(plan.outputs)):
        raise CharacterRegistryError('来源 RP 图绑定长度不一致')
    return plan
