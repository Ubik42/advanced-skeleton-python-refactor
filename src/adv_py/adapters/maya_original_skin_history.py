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
