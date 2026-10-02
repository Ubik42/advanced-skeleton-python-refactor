"""ADV 6.925 asGetAxis / asAbsAxis, MEL 26208–26279."""
from adv_py.core.adv_icon_axis import tertiary_axis


def original_axes(commands, joint, reference, *, fit_skeleton='FitSkeleton'):
    """Keep reference defaults, then override the pair only in worldmatch.

    The source tests primaryAxis before reading BOTH enum strings. A missing
    secondaryAxis on an authored pair remains a scene error, not a fallback.
    """
    if not commands.objExists(reference):
        raise ValueError('Object "' + reference + '" does not exist')
    primary, secondary = 'X', 'Y'
    if commands.objExists(reference+'.primaryAxis'):
        primary=commands.getAttr(reference+'.primaryAxis',asString=True)
        secondary=commands.getAttr(reference+'.secondaryAxis',asString=True)
    if (commands.objExists(fit_skeleton+'.worldmatch')
            and commands.getAttr(fit_skeleton+'.worldmatch')
            and commands.objExists(joint+'.primaryAxis')):
        primary=commands.getAttr(joint+'.primaryAxis',asString=True)
        secondary=commands.getAttr(joint+'.secondaryAxis',asString=True)
    return primary,secondary


def original_axis(commands, which, joint, reference, *, absolute=False,
                  fit_skeleton='FitSkeleton'):
    primary,secondary=original_axes(commands,joint,reference,fit_skeleton=fit_skeleton)
    if which=='primary':axis=primary
    elif which=='secondary':axis=secondary
    elif which=='tertiary':axis=tertiary_axis(primary,secondary)
    else:axis=''
    return axis.removeprefix('-') if absolute else axis
