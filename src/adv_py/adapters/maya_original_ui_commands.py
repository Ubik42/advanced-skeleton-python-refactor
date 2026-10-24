"""Keep native source command text available when UI callbacks become Python."""
_COMMANDS = {}


def command(raw, kind, name):
    current = getattr(raw, kind)(name, query=True, command=True)
    key = (id(raw), kind, name.rsplit('|', 1)[-1])
    if callable(current):
        return getattr(current, '_adv_source_command', _COMMANDS.get(key, ''))
    if isinstance(current, str) and current.lstrip().startswith(('as', 'evalDeferred as')):
        _COMMANDS[key] = current
        return current
    # Maya may expose a Python callback as generated Python dispatch text.
    # The saved MEL text remains the publish/copy/drag data, not executable code.
    return _COMMANDS.get(key, current)


def bind(raw, kind, name, source, callback):
    key = (id(raw), kind, name.rsplit('|', 1)[-1])
    _COMMANDS[key] = source
    callback._adv_source_command = source
    getattr(raw, kind)(name, edit=True, command=callback)


def forget(raw, names):
    names = {name.rsplit('|', 1)[-1] for name in names}
    for key in tuple(_COMMANDS):
        if key[0] == id(raw) and key[2] in names:
            del _COMMANDS[key]
