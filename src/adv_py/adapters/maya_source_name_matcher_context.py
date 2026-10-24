"""Shared Auto Key and selection behavior of asMappingUIFunction."""
from functools import wraps


def mapping_action(operation):
    @wraps(operation)
    def call(host, *args, **kwargs):
        commands = getattr(host._cmds, 'raw', host._cmds)
        auto_key = bool(commands.autoKeyframe(query=True, state=True))
        if auto_key:
            commands.autoKeyframe(state=False)
        try:
            result = operation(host, *args, **kwargs)
        finally:
            if auto_key:
                commands.autoKeyframe(state=True)
        commands.select(clear=True)
        return result
    return call
