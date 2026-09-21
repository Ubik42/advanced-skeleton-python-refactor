"""Explicit Maya namespace identity and reversible node-address mapping."""
from dataclasses import dataclass
import re

from .character_registry import CharacterRegistryError, REGISTRY_NAME

SHARED_NODES = frozenset(('time1','ikRPsolver','ikSCsolver','ikSplineSolver'))


@dataclass(frozen=True)
class CharacterIdentity:
    namespace: str

    def __post_init__(self):
        if not isinstance(self.namespace,str) or (self.namespace and not re.fullmatch(
                r'[A-Za-z_][A-Za-z_0-9]*(?::[A-Za-z_][A-Za-z_0-9]*)*',self.namespace)):
            raise CharacterRegistryError('角色命名空间必须是明确名称，可用冒号分隔层级')

    @property
    def registry_path(self):
        return self.to_scene(REGISTRY_NAME)

    def owns(self, address):
        prefix=self.namespace+':' if self.namespace else ''
        parts=[part.lstrip(':') for part in address.split('.',1)[0].split('|') if part]
        return bool(parts) and all(part.startswith(prefix) and ':' not in part[len(prefix):] for part in parts)

    def to_scene(self, address):
        if not isinstance(address,str) or not address:
            return address
        node,separator,attribute=address.partition('.')
        # Explicit physical addresses, including foreign connections reported by
        # Maya, retain their identity. Mutation policy belongs to the adapter.
        if ':' in node or node in SHARED_NODES:
            return address
        prefix=self.namespace+':' if self.namespace else ''
        return '|'.join(prefix+part if part else '' for part in node.split('|'))+separator+attribute

    def to_local(self, address):
        if not isinstance(address,str) or not address:
            return address
        node,separator,attribute=address.partition('.')
        prefix=self.namespace+':' if self.namespace else ''
        if self.owns(node):
            return '|'.join(part.lstrip(':')[len(prefix):] if part else '' for part in node.split('|'))+separator+attribute
        if node in SHARED_NODES:
            return address
        # A root-namespace outsider must not be confused with a local name.
        if ':' not in node:
            node='|'.join(':'+part if part else '' for part in node.split('|'))
        return node+separator+attribute


@dataclass(frozen=True)
class SceneCharacter:
    identity: CharacterIdentity
    registry_path: str
    registry_uuid: str
    referenced: bool
