"""Original Anim/Bake dialog order, ADV 6.925 MEL 13982–14064."""


def show(host, ui_name='', **state):
    """Open the existing host's native dialog; this never launches Maya."""
    from adv_py.application.original_animation_bake import BakeOriginalControlAnimation
    c = getattr(host._cmds, 'raw', host._cmds)
    if not host.original_control_sets(ui_name, **state):
        raise ValueError('No controlSets detected. select a controller')
    service = BakeOriginalControlAnimation(host)
    systems = service.systems()
    choices = [('Extra 控制器 → 主控制器', 'extra', None),
               ('主控制器 → Extra 控制器', 'to_extra', None),
               ('QuickIK → FK 控制器', 'quick_ik', None)]
    choices += [('FK → IK：' + name, 'fkik', (name, 'ik')) for name in systems]
    choices += [('IK → FK：' + name, 'fkik', (name, 'fk')) for name in systems]
    if c.window('asAnimBake', query=True, exists=True):
        c.deleteUI('asAnimBake')
    window = c.window('asAnimBake', title='动画烘焙', resizeToFitChildren=True)
    c.columnLayout()
    c.text(label='烘焙：')

    def change(*_):
        index = c.optionMenu('asAnimBakeOptionMenu', query=True, select=True) - 1
        _, action, values = choices[index]
        enabled = action == 'fkik' and values[1] == 'ik'
        c.checkBox('asAnimBakingMoCapCheckBox', edit=True, enable=enabled)
        c.text('asAnimBakingMoCapText', edit=True, enable=enabled)

    c.optionMenu('asAnimBakeOptionMenu', changeCommand=change)
    for label, _, _ in choices:
        c.menuItem(label=label)
    c.separator(height=10)
    c.checkBox('asAnimBakingMoCapCheckBox', enable=False, label='烘焙动捕',
               value=bool(c.optionVar(query='asBakingMoCap')),
               changeCommand=lambda value: c.optionVar(intValue=('asBakingMoCap', int(value))))
    c.text('asAnimBakingMoCapText', enable=False, label='匹配肘／膝旋转，而不是位置')
    c.separator(style='none', height=10, width=200)
    c.rowLayout(numberOfColumns=2)
    c.separator(width=50, style='none')

    def execute(*_):
        index = c.optionMenu('asAnimBakeOptionMenu', query=True, select=True) - 1
        _, action, values = choices[index]
        options = dict(ui_name=ui_name, **state)
        if action == 'extra':
            return service.bake_extra(**options)
        if action == 'to_extra':
            return service.move_to_extra(**options)
        if action == 'quick_ik':
            return service.bake_quick_ik(**options)
        # This is Maya's existing progress UI global, not an ADV business
        # procedure and not another DCC process.
        from maya import mel
        progress = mel.eval('$advPyProgress = $gMainProgressBar')
        options.update(baking_mocap=bool(c.checkBox('asAnimBakingMoCapCheckBox',query=True,value=True)), progress=progress or None)
        return service.execute(values[0], values[1], **options)

    c.button(width=100, label='确定，烘焙', command=execute)
    c.showWindow(window)
    return window
