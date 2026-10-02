"""Keep closed source graph records aligned with final native converter names."""
from adv_py.core.character_registry import canonical, CharacterRegistryError

RECORDS=('advPySourceIkRootFrame','advPySourceRpDynamics','advPySourceFkMatrix',
         'advPySourceBendyMatrix','advPySourceTwistReference','advPySourceInbetweenMatrix','advPySourceBendyMicroMatrix')


def rename_addresses(host, renames):
    if not renames:return
    host._require_transaction()
    c=host._cmds
    def rewrite(value):
        if isinstance(value,str):
            node,separator,attribute=value.partition('.')
            renamed=renames.get(node)
            if renamed is not None:return renamed+(separator+attribute if separator else '')
            return value
        if isinstance(value,list):return [rewrite(item) for item in value]
        if isinstance(value,dict):return {key:rewrite(item) for key,item in value.items()}
        return value
    for node in c.ls(long=True) or []:
        for attribute in RECORDS:
            plug=node+'.'+attribute
            if not c.objExists(plug):continue
            if c.getAttr(plug,type=True)!='string':
                raise CharacterRegistryError('来源图记录属性类型变化：'+plug)
            from adv_py.core.character_registry import safe_json
            raw=safe_json(c.getAttr(plug))
            updated=rewrite(raw)
            if updated==raw:continue
            locked=bool(c.getAttr(plug,lock=True))
            try:
                c.setAttr(plug,lock=False)
                c.setAttr(plug,canonical(updated),type='string')
            finally:c.setAttr(plug,lock=locked)
            host._transaction_changed=True
