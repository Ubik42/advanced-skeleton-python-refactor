"""Connect implemented Python commands to the original existing menu items.

The native Selector / Picker / Poser controls keep their original ordering,
separators and labels. This module creates no replacement main window.
"""


def bind(host, window, ui_name='', **state):
    c = getattr(host._cmds, 'raw', host._cmds)
    from adv_py.application.original_animation_tools import EditOriginalAnimationTools
    from adv_py.application.original_clipboard import TransferOriginalControlClipboard
    from adv_py.application.driving_systems import EditOriginalPoseFunctions

    def current_host():
        menu = ui_name + 'OptionMenu'
        if ui_name and c.optionMenu(menu, query=True, exists=True):
            namespace = c.optionMenu(menu, query=True, value=True).strip(':')
            from .maya_driving_systems import MayaDrivingSystemsHost
            return MayaDrivingSystemsHost(namespace=namespace or None)
        return host

    def pose(action):
        return lambda *_: EditOriginalPoseFunctions(current_host()).apply(action, ui_name=ui_name, ui_state=state)

    def clipboard(action, animation):
        def execute(*_):
            service = TransferOriginalControlClipboard(current_host())
            return getattr(service, action)(animation, ui_name=ui_name, **state)
        return execute

    def tool(action):
        return lambda *_: EditOriginalAnimationTools(current_host()).execute(action)

    def mirror_options(*_):
        from .maya_original_mirror_options_ui import show
        return show(current_host(), ui_name, **state)

    def bake(*_):
        from .maya_original_animation_bake_ui import show
        return show(current_host(), ui_name, **state)

    callbacks = {
        'Pose': {'Copy': clipboard('copy', False), 'Paste': clipboard('paste', False),
                 'Reset': pose('neutral'), 'Tpose': pose('t_pose'), 'Mirror': pose('mirror')},
        'Anim': {'Copy': clipboard('copy', True), 'Paste': clipboard('paste', True),
                 'Clean': pose('clean_animation'), 'Bake': bake, 'SwitchFKIK': tool('switch_fkik'),
                 'SwitchPivot': tool('switch_pivot'), 'PivotControl': tool('pivot_control'), 'QuickIK': tool('quick_ik')},
    }
    changed = []
    for menu in c.window(window, query=True, menuArray=True) or ():
        label = c.menu(menu, query=True, label=True)
        if label not in callbacks:
            continue
        for item in c.menu(menu, query=True, itemArray=True) or ():
            original = c.menuItem(item, query=True, command=True)
            item_label = c.menuItem(item, query=True, label=True)
            if label == 'Pose' and isinstance(original, str) and 'asMirrorOptions' in original:
                callback = mirror_options
            else:
                callback = callbacks[label].get(item_label)
            if callback is not None:
                c.menuItem(item, edit=True, command=callback)
                changed.append(item)
    from .maya_original_selector_binding import bind as bind_selector
    changed.extend(bind_selector(host,window,host_provider=current_host))
    from .maya_original_selection_feedback import bind as bind_feedback
    changed.extend(bind_feedback(host,window))
    return tuple(changed)
