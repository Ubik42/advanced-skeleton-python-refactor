"""Bind original existing Selector buttons / popups without reordering UI."""
import re
import json
from pathlib import Path
from .maya_original_ui_commands import command as source_command, bind as bind_command

COMMAND = re.compile(r'^\s*(asSelect|asKey|asLinearKey|asAlignIK2FK|asAlignFK2IK|asSwitchIK2FK|asSwitchFK2IK)\s+"([^"]*)"\s+\{([^}]*)\}\s*;?\s*$')


def _tokens(command):
    if not isinstance(command, str):
        return ()
    try:
        text=command.rstrip().rstrip(';')
        tokens=[]
        index=0
        decoder=json.JSONDecoder()
        while index<len(text):
            if text[index].isspace():
                index+=1
                continue
            if text[index]=='"':
                value,length=decoder.raw_decode(text[index:])
                tokens.append(value)
                index+=length
            else:
                end=index
                while end<len(text) and not text[end].isspace() and text[end]!='"':
                    end+=1
                tokens.append(text[index:end])
                index=end
        return tuple(tokens)
    except ValueError:
        # Other original buttons can contain compound MEL or quoted scripts.
        return ()


def _stored_pose(c, window, button, originals):
    """Resolve the popup's original button before any Python callback edits."""
    exact = originals.get(button)
    if exact is None:
        matches = [value for path, value in originals.items()
                   if path.rsplit('|', 1)[-1] == button]
        if len(matches) != 1:
            return None
        exact = matches[0]
    tokens = _tokens(exact)
    return tokens[2] if len(tokens) == 3 and tokens[0] == 'asSetAttrs' else None


def bind(host, window, *, host_provider=None):
    c = getattr(host._cmds, 'raw', host._cmds)
    from adv_py.application.original_selector import EditOriginalSelector
    changed = []
    def active():
        return host_provider() if host_provider else host
    # Popup commands parse their button's MEL string in the source. Preserve
    # that string before replacing button callbacks in the same bind pass.
    originals = {control: source_command(c,'iconTextButton',control)
                 for control in c.lsUI(type='iconTextButton', long=True) or ()
                 if control == window or control.startswith(window + '|')}
    for command_type, controls in (
            ('iconTextButton', c.lsUI(type='iconTextButton', long=True) or ()),
            ('menuItem', c.lsUI(menuItems=True, long=True) or ())):
        widget = getattr(c, command_type)
        for control in controls:
            if not (control == window or control.startswith(window + '|')):
                continue
            original = source_command(c,command_type,control)
            tokens = _tokens(original)
            if command_type == 'iconTextButton' and isinstance(original,str):
                if len(tokens)==3 and tokens[0] in ('asSetAttrs', 'asKeyAttrs'):
                    text=tokens[2]
                    action='pose' if tokens[0]=='asSetAttrs' else 'stored_keys'

                    def set_pose(*_, text=text, action=action):
                        from adv_py.application.original_poser import EditOriginalPoser
                        return EditOriginalPoser(host_provider() if host_provider else host).apply(text, action)

                    bind_command(c,command_type,control,original,set_pose)
                    changed.append(control)
                    continue
                if len(tokens) in (2,3) and tokens[0]=='asLoadAttrs':
                    image=widget(control,query=True,image=True)
                    source=Path(re.sub(r'[.][a-z][a-z][a-z]', '.ma',image,count=1))
                    ui_name=tokens[1]

                    def load_animation(*_, source=source, ui_name=ui_name):
                        from adv_py.application.original_clipboard import TransferOriginalControlClipboard
                        active=host_provider() if host_provider else host
                        return TransferOriginalControlClipboard(active).paste(True,source=source,project_name=source.parent.name,ui_name=ui_name)

                    bind_command(c,command_type,control,original,load_animation)
                    changed.append(control)
                    continue
            if command_type == 'menuItem' and len(tokens) == 4 and tokens[0] == 'asPoseObjects':
                actions = {' select -add': 'select', 'setKeyframe': 'key',
                           'setKeyframe -itt linear -ott linear': 'linear_key'}
                action = actions.get(tokens[3])
                text = _stored_pose(c, window, tokens[2], originals)
                if action and text is not None:
                    def pose_objects(*_, text=text, action=action):
                        from adv_py.application.original_poser import EditOriginalPoser
                        return EditOriginalPoser(host_provider() if host_provider else host).apply(text, action)
                    bind_command(c,command_type,control,original,pose_objects)
                    changed.append(control)
                    continue
            if command_type=='menuItem' and tokens:
                callback=None
                if len(tokens)==3 and tokens[0]=='asPoseView' and tokens[2].isdigit():
                    name,child=tokens[1],int(tokens[2])
                    callback=lambda *_,name=name,child=child:active().view_original_poser_media(name,child)
                elif len(tokens)==2 and tokens[0]=='asPoserRename' and tokens[1].isdigit():
                    child=int(tokens[1])
                    callback=lambda *_,child=child:active().rename_original_poser_button(child)
                elif len(tokens)==3 and tokens[0]=='asPoserDeletePose' and tokens[2].isdigit():
                    name,child=tokens[1],int(tokens[2])
                    callback=lambda *_,name=name,child=child:active().delete_original_poser_button(name,child)
                elif len(tokens)==6 and tokens[0]=='asPoserSnapShoot' and all(part.isdigit() for part in tokens[2:]):
                    name=tokens[1]
                    child,animation,icon,movie=map(int,tokens[2:])
                    def snapshot(*_,name=name,child=child,animation=animation,icon=icon,movie=movie):
                        from .maya_original_poser_snapshot import capture
                        host=active()
                        with host.transaction('更新原版 Poser 图像'):
                            return capture(host,name,child,bool(animation),bool(icon),bool(movie))
                    callback=snapshot
                if callback:
                    bind_command(c,command_type,control,original,callback)
                    changed.append(control)
                    continue
            match = COMMAND.fullmatch(original) if isinstance(original, str) else None
            if not match:
                continue
            command, name, values = match.groups()
            objects = tuple(re.findall(r'"([^"]*)"', values))
            if not objects:
                continue

            def execute(*_, command=command, name=name, objects=objects):
                active = host_provider() if host_provider is not None else host
                return EditOriginalSelector(active).execute(command, name, objects)

            bind_command(c,command_type,control,original,execute)
            changed.append(control)
    return tuple(changed)
