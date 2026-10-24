"""ADV asGetSkinCluster, source MEL 8211–8219 (no host policy added)."""


def original_skin_cluster(commands, geometry):
    """Return the final Skin in pruned interest-level-two history.

    Target DAG history must not participate in this query. Missing Skin
    returns an empty string exactly like the source helper; callers decide
    whether their operation permits that condition.
    """
    skin = ""
    for node in commands.listHistory(geometry, pruneDagObjects=True, interestLevel=2) or []:
        if commands.nodeType(node) == "skinCluster":
            skin = node
    return skin


def related_skin_cluster(geometry, *, mel=None):
    """Maya's findRelatedSkinCluster, used by source asWeightHammerVerts.

    This is a Maya host utility, not the ADV asGetSkinCluster procedure. Its
    downstream selection policy deliberately remains a separate operation.
    """
    if mel is None:
        from maya import mel
    escaped = geometry.replace("\\", "\\\\").replace('"', '\\"')
    return mel.eval('findRelatedSkinCluster "' + escaped + '";') or ""


def remove_unused_for_skin(commands, skin):
    """Native removeUnusedForSkin(skin, 0), including its query-first guard.

    A skin with no unused influences is left untouched by Maya's helper.
    This preserves its history and avoids an unsolicited edit/update.
    """
    count = int(commands.skinCluster(skin, query=True,
                                     removeUnusedInfluence=True))
    if count > 0:
        commands.skinCluster(skin, edit=True, removeUnusedInfluence=True)
    return count


def native_skin_cluster_chain(commands, geometry):
    """Maya skinClusterChain: reverse the deformation chain, then unique.

    deformableShape's chain excludes unrelated upstream geometry histories.
    This is distinct from ADV's asGetSkinCluster interest-level query above.
    """
    chain = commands.deformableShape(geometry, ch=True) or []
    skins = (commands.ls(chain, type='skinCluster') or []) if chain else []
    return tuple(dict.fromkeys(reversed(skins)))


def remove_unused_selected_skin_influences(commands):
    """Maya removeUnusedInfluences() with filterSelected=0.

    The empty filter still chooses only the first SkinCluster in each native
    chain. Keep selected-object order, including repeated visits to a Skin
    through a selected transform and its shape, as Autodesk's helper does.
    """
    operated = removed = 0
    for geometry in commands.ls(selection=True, objectsOnly=True) or []:
        chain = native_skin_cluster_chain(commands, geometry)
        if not chain:
            continue
        operated += 1
        removed += remove_unused_for_skin(commands, chain[0])
    if not operated:
        raise RuntimeError('没有选中可清理无用影响的蒙皮对象')
    if removed:
        commands.select(commands.ls(selection=True) or [], replace=True)
    return removed


def new_original_skin_clusters(*, commands=None, namespace=None, mel=None,
                               maximum_influences=3):
    """Maya newSkinCluster with the flags used by ADV's original bind actions.

    Maya's own utility expands selected hierarchies/shapes and handles component
    membership and multi-geometry binding. A direct skinCluster(selection) call
    does not reproduce that boundary. No ADV MEL procedure is loaded here.
    """
    if commands is None:
        from maya import cmds as commands
    if mel is None:
        from maya import mel
    previous = commands.namespaceInfo(currentNamespace=True, absoluteName=True)
    target = previous if namespace is None else ":" + namespace.strip(":")
    if target != previous:
        commands.namespace(set=target)
    try:
        arguments = ('-toSelectedBones -mi ' + str(int(maximum_influences))
                     + ' -dr 4 -rui false')
        return tuple(mel.eval('newSkinCluster "' + arguments + '";') or ())
    finally:
        if target != previous:
            commands.namespace(set=previous)


def bind_original_skin(commands, selection, name, *, namespace=None,
                       maximum_influences=3, mel=None):
    """Source select → newSkinCluster → rename first returned Skin.

    Keep every other Skin produced by Maya's hierarchy expansion, as ADV
    does. The command boundary maps logical names when a character is active.
    Selection deliberately remains Maya's bind result for the following
    source commands to replace or extend.
    """
    commands.select(selection, replace=True)
    skins = new_original_skin_clusters(
        commands=getattr(commands, "raw", commands), namespace=namespace,
        maximum_influences=maximum_influences, mel=mel)
    return commands.rename(skins[0], name)
