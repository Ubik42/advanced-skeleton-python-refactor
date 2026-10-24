"""Original Mirror Options widget order and persisted choices, MEL 12287."""


def show(host, ui_name='', **state):
    c = getattr(host._cmds, 'raw', host._cmds)
    if c.window('asMirrorOptions', query=True, exists=True):
        c.deleteUI('asMirrorOptions')
    window = c.window('asMirrorOptions', title='镜像选项')
    c.columnLayout(adjustableColumn=True)
    c.separator(height=25, style='none')
    rows = (
        ('asMOSide', '方向：', (('Flip', '交换'), ('R2L', '右 → 左'), ('L2R', '左 → 右'))),
        ('asMOAxis', '轴：', (('X', 'X'), ('Y', 'Y'), ('Z', 'Z'))),
        ('asMOSpace', '空间：', (('World', '世界'), ('Main', 'Main'), ('Center', 'RootX_M'))),
        ('asMOSelOnly', '控制器：', (('All', '全部'), ('Sel', '选中'))),
    )
    for name, label, buttons in rows:
        c.rowLayout(numberOfColumns=4, columnWidth=(1, 40))
        c.text(label=label)
        c.radioCollection(name + 'RadioCollection')
        for token, button in buttons:
            c.radioButton(name + token, label=button)
        c.setParent('..')
    c.separator(height=25, style='none')

    def mirror(*_):
        with host.transaction('原版控制器镜像'):
            return host.mirror_original_control_pose(ui_name, **state)

    c.button(width=100, label='镜像', command=mirror)
    c.showWindow(window)
    # Source selects the FIRST button without a stored preference, including
    # Swap and World. This differs from asMirror's defaults without a window.
    for name, _, buttons in rows:
        collection = name + 'RadioCollection'
        children = c.radioCollection(collection, query=True, collectionItemArray=True)
        selected = children[0]
        if c.optionVar(exists=name):
            saved = c.optionVar(query=name)
            if any(child.endswith(saved) for child in children):
                selected = saved
        c.radioCollection(collection, edit=True, select=selected)
    return window
