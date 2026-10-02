"""Closed source Inbetween FK graph records, including matrix constants."""
from dataclasses import dataclass
import re
from .source_body_matrix import SourceBodyMatrixPlan,decode_source_body_matrix
from .character_registry import safe_json,exact,canonical,vector,CharacterRegistryError

@dataclass(frozen=True,slots=True)
class SourceInbetweenMatrixRecord:
    graph: SourceBodyMatrixPlan
    matrices: tuple[tuple[str,tuple[float,...]],...]
    inherits_transform: bool


def decode(text):
    raw=exact(safe_json(text),('graph','matrices','inherits_transform'))
    graph=decode_source_body_matrix(canonical(raw['graph']))
    names={node.name for node in graph.nodes}
    matrices=tuple((plug,vector(values,16)) for plug,values in raw['matrices'])
    if (type(raw['inherits_transform']) is not bool
            or len({plug for plug,_ in matrices})!=len(matrices)
            or any(not isinstance(plug,str) or '.' not in plug
                   or plug.split('.',1)[0] not in names
                   or not re.fullmatch(r'matrixIn\[\d+\]',plug.split('.',1)[1])
                   for plug,_ in matrices)):
        raise CharacterRegistryError('来源 Inbetween 矩阵常量记录无效')
    return SourceInbetweenMatrixRecord(graph,matrices,raw['inherits_transform'])
