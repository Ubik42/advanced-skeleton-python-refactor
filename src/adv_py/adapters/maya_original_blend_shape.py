"""Native asBlendShapeFrontOfChain helper, ADV 6.925 MEL 42788–42794."""


def original_front_of_chain_blend_shape(commands, *geometry, name):
    """Try suppressDialog first, falling back for older Maya commands.

    Use Maya's current selection when geometry is omitted, as the original
    helper does. No alternate deformer ordering is introduced by the fallback.
    """
    try:
        result = commands.blendShape(*geometry, name=name,
                                     frontOfChain=True, suppressDialog=True)
    except (TypeError, RuntimeError):
        result = commands.blendShape(*geometry, name=name, frontOfChain=True)
    return result[0]
