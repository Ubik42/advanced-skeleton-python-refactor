"""ADV Optimize policies, MEL 75547–75580 and 75640–75702."""

# Spelling is source data, including curveUnafeccted's historical spelling.
UNUSED_ATTRIBUTE_EXCEPTIONS = frozenset((
    'ikLocal', 'clusterControl', 'skinControl', 'softModControl',
    'SquashControl', 'localOrient', 'parent', 'optimizedDS', 'primaryAxis',
    'secondaryAxis', 'worldorient', 'worldmatch', 'curveUnafeccted', 'mirror',
    'mirroredBehaviour', 'mirroredTranslate', 'customAxis', 'vtxNr',
))


def removable_original_control_attribute(attribute, *, locked, connected):
    return (not locked and not connected
            and attribute not in UNUSED_ATTRIBUTE_EXCEPTIONS)
