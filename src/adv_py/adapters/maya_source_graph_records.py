"""Keep closed source graph records aligned with final native converter names."""
from adv_py.core.character_registry import canonical, CharacterRegistryError
from adv_py.core.character_identity import CharacterIdentity

RECORDS=('advPySourceIkRootFrame','advPySourceRpDynamics','advPySourceFkMatrix',
         'advPySourceBendyMatrix','advPySourceLocalScale','advPySourcePartPoint',
         'advPySourceTwistPosition','advPySourceTwistReference',
         'advPySourceInbetweenMatrix','advPySourceBendyMicroMatrix',
         'advPySourceEndMatrix',
         'advPySourceRpFollow','advPySourceRpScaleLayout','advPySourceRpModePlan',
         'advPySourceLimbAim','advPySourceDrivingSDK','advPySourceControlOrient',
         'advPySourceUnrealTwist','advPySourceGameScaling',
         'advPySourceSplineAlignment')


def rename_addresses(host, renames):
    if not renames:return
    host._require_transaction()
    c=host._cmds
    identity=CharacterIdentity(host.namespace or '')
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
        if not identity.owns(host.scene_address(node)):
            continue
        for attribute in RECORDS:
            plug=node+'.'+attribute
            if not c.objExists(plug):continue
            if c.getAttr(plug,type=True)!='string':
                raise CharacterRegistryError('来源图记录属性类型变化：'+plug)
            from adv_py.core.character_registry import safe_json
            raw=safe_json(c.getAttr(plug))
            if attribute == 'advPySourceGameScaling':
                from adv_py.core.original_game_scaling_record import remap_record
                encoded = remap_record(c.getAttr(plug), lambda address: renames.get(address, address))
                updated=safe_json(encoded)
            else:
                updated=rewrite(raw)
            if updated==raw:continue
            locked=bool(c.getAttr(plug,lock=True))
            try:
                c.setAttr(plug,lock=False)
                c.setAttr(plug,canonical(updated),type='string')
            finally:c.setAttr(plug,lock=locked)
            host._transaction_changed=True
    # The final native unitConversion naming pass runs after registration.
    # Preserve its exact graph identities as well as the source records;
    # recapturing all inputs here would silently accept unrelated changes.
    from adv_py.core.character_registry import REGISTRY_NAME, decode_registration, encode_registration
    from adv_py.core.fit_part import FitPartFinalPaths, rebase_plan_paths_after_parts
    plug = REGISTRY_NAME + '.advPyRegistryDocument'
    if c.objExists(plug):
        before = decode_registration(c.getAttr(plug))
        after = rebase_plan_paths_after_parts(
            before, FitPartFinalPaths((), (), tuple(renames.items())))
        if after != before:
            locked = bool(c.getAttr(plug, lock=True))
            try:
                c.setAttr(plug, lock=False)
                c.setAttr(plug, encode_registration(after), type='string')
            finally:
                c.setAttr(plug, lock=locked)
            host._transaction_changed = True
