"""asSelChange / asSelChangeToggle / asShowSelJob, MEL 10165–10614.

Refresh the original existing Selector and Picker UI. No replacement window,
controller, animation curve, or solver is created by this observer.
"""
from contextlib import contextmanager
from fnmatch import fnmatchcase
import re

from .maya_original_control_identity import command_registration, control_roles

_RUNNING = False
_SWITCHING = False
_LOADING = 0
_JOB = None
_ORIGINAL_JOB = re.compile(
    r'^\s*(\d+):\s*["\']?SelectionChanged["\']?\s+["\']?\s*asSelChange\s*;?\s*["\']?\s*$')


def raw(host):
    return getattr(host._cmds, 'raw', host._cmds)


@contextmanager
def file_loading():
    global _LOADING
    _LOADING += 1
    try:
        yield
    finally:
        _LOADING -= 1


def _option(c, name):
    return bool(c.optionVar(query=name)) if c.optionVar(exists=name) else False


def have_animation(c, node):
    """asHaveAnimation checks direct inputs, including driven animCurves."""
    return any(c.objectType(source).startswith('animCurve')
               for source in c.listConnections(node, source=True, destination=False) or ())


def _actual(c, prefix, role):
    address = prefix + role
    if c.objExists(address):
        return address
    saved = command_registration(c, prefix)
    choices = [node for node, source in control_roles(saved).items() if source == role]
    if len(choices) > 1:
        raise ValueError('原版控制器角色不唯一：' + address)
    return prefix + choices[0] if choices else address


def resolve(c, name, role):
    """Original UI namespace precedence, plus the registered Python names."""
    menu = 'asSelector' + name + 'OptionMenu'
    if c.optionMenu(menu, query=True, exists=True):
        prefix = c.optionMenu(menu, query=True, value=True)
    elif c.optionMenu('asPickerOptionMenu', query=True, exists=True):
        prefix = c.optionMenu('asPickerOptionMenu', query=True, value=True)
    else:
        prefix = name.rsplit(':', 1)[0] + ':' if ':' in name else ''
    if prefix == ':':
        prefix = ''
    checkbox = 'asSelector' + name + 'ExtraCheckBox'
    if (len(role) > 2 and c.checkBox(checkbox, query=True, exists=True)
            and c.checkBox(checkbox, query=True, value=True)):
        extra = role[:2] + 'Extra' + role[2:]
        if 'RootX' in role:
            extra = role[:4] + 'Extra' + role[4:]
        candidate = _actual(c, prefix, extra)
        if c.objExists(candidate):
            return candidate
    return _actual(c, prefix, role)


def _selectors(c, selected, show_selection, show_keyed):
    changed = []
    for window in c.lsUI(windows=True) or ():
        # The source derives the layout from the window suffix, then checks
        # that it exists; retaining that rule also accepts authored windows.
        layout = 'asSelector' + window[10:] + 'FormLayout' if len(window) > 11 else ''
        if not c.formLayout(layout, query=True, exists=True):
            continue
        name = layout[10:-10]
        for control in c.formLayout(layout, query=True, childArray=True) or ():
            if not c.iconTextButton(control, query=True, exists=True):
                continue
            annotation = c.iconTextButton(control, query=True, annotation=True)
            on = show_selection and not _SWITCHING
            keyed = False
            for role in (token for token in annotation.split(';') if token):
                node = resolve(c, name, role)
                if node not in selected:
                    on = False
                if show_keyed and c.objExists(node) and have_animation(c, node):
                    keyed = True
            if fnmatchcase(annotation, '*AllSet'):
                on = keyed = False
            image = c.iconTextButton(control, query=True, image1=True)
            if not image:
                color = ((1., .5, .5) if on else (1., 0., 0.)) if keyed else (
                    (.263, 1., .639) if on else c.iconTextButton(control, query=True, overlayLabelColor=True))
                c.iconTextButton(control, edit=True, backgroundColor=color)
                changed.append(control)
                continue
            pieces = image.split('_')
            if len(pieces) < 3:
                continue
            # The legacy three-token case intentionally repeats token zero.
            project = '_'.join(pieces[:-3]) if len(pieces) > 3 else pieces[0]
            target = project + '_' + '_'.join(pieces[-3:-1]) + ('_OnK' if on else '_OffK') + str(int(keyed)) + '.png'
            if target != image:
                c.iconTextButton(control, edit=True, image=target)
                changed.append(control)
    return changed


def _picker(c, selected, show_selection, show_keyed):
    if not c.optionMenu('asPickerOptionMenu', query=True, exists=True):
        return ()
    prefix = c.optionMenu('asPickerOptionMenu', query=True, value=True)
    if prefix == ':':
        prefix = ''
    picker = ''
    if c.tabLayout('asPickerTabLayout', query=True, exists=True):
        tabs = c.tabLayout('asPickerTabLayout', query=True, tabLabel=True)
        index = c.tabLayout('asPickerTabLayout', query=True, selectTabIndex=True)
        picker = 'picker_' + tabs[index - 1] + ':'
        text = 'asPickerEmbeddedPickerNameSpace' + str(index)
        if c.text(text, query=True, exists=True):
            embedded = c.text(text, query=True, label=True)
            if embedded:
                picker = embedded + ':'
    controls = c.ls(picker + '*', type='transform') or ()
    picked = c.ls(picker + '*', selection=True, type='transform') or ()
    character_selected = c.ls(prefix + '*', selection=True, type='transform') or ()
    extra = _option(c, 'asShowExtra')
    undo = c.undoInfo(query=True, state=True)
    if undo:
        c.undoInfo(stateWithoutFlush=False)
    changed = []
    try:
        for control in controls:
            role = control.replace(picker, prefix, 1)
            if extra:
                role = role.replace('FK', 'FKExtra', 1)
            # Resolve Python roles only at the host boundary.
            target = _actual(c, prefix, role[len(prefix):])
            color = 13 if c.objExists(target) and show_keyed and have_animation(c, target) else 0
            c.setAttr(control + '.overrideColor', color)
            changed.append(control)
        if not picked and not character_selected:
            return tuple(changed)
        color = 0
        for node in selected:
            if show_selection:
                color = 14
            if fnmatchcase(node, picker + '*'):
                role = node.replace(picker, prefix, 1)
                if extra:
                    role = role.replace('FK', 'FKExtra', 1)
                target = _actual(c, prefix, role[len(prefix):])
                if c.objExists(target) and show_selection:
                    c.select(node, deselect=True)
                    c.select(target, toggle=True)
                    if target in selected:
                        color = 13 if show_keyed and have_animation(c, target) else 0
                    c.setAttr(node + '.overrideColor', color)
                else:
                    print('// ' + target + ' not found.')
            if fnmatchcase(node, prefix + '*'):
                role = node[len(prefix):] if prefix else node
                role = control_roles(command_registration(c, prefix)).get(role, role)
                target = picker + role
                if extra:
                    if 'Extra' not in target:
                        continue
                    target = target.replace('FKExtra', 'FK', 1)
                if c.objExists(target):
                    c.setAttr(target + '.overrideColor', color)
    finally:
        if undo:
            c.undoInfo(stateWithoutFlush=True)
    return tuple(changed)


def refresh(host):
    global _RUNNING
    if _LOADING or _RUNNING:
        return ()
    c = raw(host)
    show_selection = _option(c, 'asShowSelection')
    show_keyed = _option(c, 'asShowKeyed')
    if not show_selection and not show_keyed and not _SWITCHING:
        return ()
    _RUNNING = True
    try:
        selected = tuple(c.ls(selection=True) or ())
        return tuple(_selectors(c, selected, show_selection, show_keyed)) + _picker(c, selected, show_selection, show_keyed)
    finally:
        _RUNNING = False


def toggle(host):
    global _SWITCHING
    c = raw(host)
    selected = c.ls(selection=True) or ()
    _SWITCHING = True
    try:
        c.select(clear=True)
        refresh(host)
    finally:
        _SWITCHING = False
        c.select(selected, replace=True) if selected else c.select(clear=True)
    refresh(host)


def install(host):
    """One SelectionChanged job per live Maya command session."""
    global _JOB
    c = raw(host)
    # Published native windows can install the original MEL observer before
    # Python binds them. Two observers would toggle a Picker selection twice.
    # Replace only that exact original event/procedure, never unrelated jobs.
    for description in c.scriptJob(listJobs=True) or ():
        match = _ORIGINAL_JOB.fullmatch(description)
        if match:
            identity = int(match.group(1))
            if c.scriptJob(exists=identity):
                c.scriptJob(kill=identity)
    if _JOB is not None and _JOB[0] is c and c.scriptJob(exists=_JOB[1]):
        return _JOB[1]
    job = c.scriptJob(event=('SelectionChanged', lambda: refresh(host)))
    _JOB = c, job
    return job


def bind(host, window):
    """Replace original feedback callbacks in an existing Selector / Picker."""
    c = raw(host)
    changed = []
    for control in c.lsUI(type='checkBox', long=True) or ():
        if not control.startswith(window + '|'):
            continue
        leaf = control.rsplit('|', 1)[-1]
        for suffix, option in (('SelectionCheckBox', 'asShowSelection'),
                               ('KeyedCheckBox', 'asShowKeyed'),
                               ('ExtraCheckBox', 'asShowExtra')):
            if leaf.endswith(suffix):
                def change(value, *_, option=option):
                    c.optionVar(intValue=(option, int(value)))
                    toggle(host)
                c.checkBox(control, edit=True, changeCommand=change)
                changed.append(control)
    install(host)
    refresh(host)
    return tuple(changed)
