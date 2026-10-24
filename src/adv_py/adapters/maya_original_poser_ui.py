"""Original Poser grid creation and moves, MEL 27639–27788/27918–27999."""
from math import ceil
from pathlib import Path
import re
import shutil

from .maya_original_poser_store import child_index, icon_directory, replace_extension
from .maya_original_control_identity import source_control_from_role
from .maya_original_ui_commands import command as source_command, forget


def show(host):
    """asPoserDesigner: retain the original menu and eight-column toolbar."""
    c=raw(host)
    directory=icon_directory(c)
    directory.mkdir(parents=True,exist_ok=True)
    # Original New discards only files inside its untitled scratch directory.
    for file in directory.iterdir():
        if file.is_file():
            file.unlink()
    def option(name,default):
        value=c.optionVar(query=name) if c.optionVar(exists=name) else default
        return value
    columns=int(option('asPoserNc',4))
    rows=int(option('asPoserNr',2))
    columns=columns if columns>=1 else 4
    rows=rows if rows>=1 else 2
    label=option('asPoserText','Pose')
    if label in ('0',0):label='Pose'
    name='asPoserDefault'
    if c.window(name,query=True,exists=True):
        old=c.lsUI(long=True) or ()
        forget(c,(widget for widget in old if widget==name or widget.startswith(name+'|')))
        c.deleteUI(name)
    c.window(name,menuBar=True,title='PoserDesigner :untitled')
    menu=c.menu(label='文件')
    c.menuItem(parent=menu,label='新建',command=lambda *_:c.evalDeferred(lambda:show(host)))
    from .maya_original_poser_files import browse,save,to_shelf
    c.menuItem(parent=menu,label='打开',command=lambda *_:browse(host,'Open'))
    sets_menu=c.menuItem('asPoserControlSetsMenu',parent=menu,subMenu=True,label='控制集')
    c.menuItem('asPoserControlSetsMenuItemControlSet',parent=sets_menu,checkBox=True,label='ControlSet')
    for control_set in control_sets(host):
        if control_set!='ControlSet':
            c.menuItem('asPoserControlSetsMenuItem'+control_set,parent=sets_menu,checkBox=False,label=control_set)
    c.setParent(menu,menu=True)
    c.menuItem(parent=menu,divider=True)
    c.menuItem(parent=menu,label='保存',command=lambda *_:save(host))
    c.menuItem(parent=menu,label='另存为',command=lambda *_:browse(host,'SaveAs'))
    c.menuItem(parent=menu,label='放到工具架',command=lambda *_:to_shelf(host))
    c.menuItem(parent=menu,divider=True)
    c.menuItem(parent=menu,label='关闭',command=lambda *_:c.deleteUI(name))
    c.setParent(name)
    form=c.formLayout(name+'FormLayout')
    c.text('asPoserProjectPath',visible=False,label=directory.parent.as_posix()+'/')
    c.text('asPoserProjectName',visible=False,label='untitled')
    toolbar=c.rowLayout(name+'RowLayout',adjustableColumn=1,numberOfColumns=8,
        columnWidth=((2,90),(3,80),(4,90),(5,50),(6,20),(7,25)))
    c.optionMenu(name+'OptionMenu',changeCommand=lambda *_:char_change(host,name))
    c.button('asPoserNewPose',label='新建姿态',command=lambda *_:new_pose(host))
    change=lambda *_:update_grid(host)
    c.textField('asPoserTextField',width=70,text=label,changeCommand=change)
    c.checkBox('asPoserOnlySel',value=bool(option('asPoserOnlySel',0)),label='仅选择',changeCommand=change)
    c.checkBox('asPoserAnim',value=bool(option('asPoserAnim',0)),label='动画',changeCommand=change)
    c.intField('asPoserNc',width=20,value=columns,changeCommand=change)
    c.intField('asPoserNr',width=20,value=rows,changeCommand=change)
    c.checkBox('asPoserRenderView',value=bool(option('asPoserRenderView',0)),label='渲染视图',changeCommand=change)
    c.setParent(form)
    content=c.columnLayout(name+'Scrollayout',dragCallback=drag,dropCallback=lambda *args:drop(host,*args))
    c.gridLayout(name+'GridLayout',height=90*rows,numberOfColumns=columns,numberOfRows=rows,
        cellWidth=110,cellHeight=90)
    c.formLayout(form,edit=True,attachForm=((toolbar,'top',0),(content,'bottom',0),
        (content,'left',0),(content,'right',0)),attachControl=(content,'top',0,toolbar))
    from .maya_original_namespace_menu import populate
    populate(host,name)
    c.showWindow(name)
    return name


def control_sets(host):
    """asGetControlSets' native objectSet exclusions and name matching."""
    c=raw(host)
    return tuple(node for node in c.ls(type='objectSet') or ()
        if re.search(r'[cC]ontrol[sS]et',node)
        and not any(c.sets(node,query=True,**{flag:True})
                    for flag in ('renderable','vertices','edges','facets','editPoints')))


def char_change(host,name):
    from .maya_original_namespace_menu import char_change as reconnect
    return reconnect(host,name)


def raw(host):
    return getattr(host._cmds, 'raw', host._cmds)


def current_host(host, ui_name):
    c = raw(host)
    value = c.optionMenu(ui_name + 'OptionMenu', query=True, value=True)
    if value == 'None':
        raise ValueError('No Character In The Scene')
    from .maya_driving_systems import MayaDrivingSystemsHost
    return MayaDrivingSystemsHost(namespace=value.strip(':') or None)


def update_grid(host):
    c = raw(host)
    columns = int(c.intField('asPoserNc', query=True, value=True))
    rows = int(c.intField('asPoserNr', query=True, value=True))
    label = c.textField('asPoserTextField', query=True, text=True)
    c.optionVar(intValue=('asPoserNc', columns))
    c.optionVar(intValue=('asPoserNr', rows))
    c.optionVar(stringValue=('asPoserText', label))
    for name in ('asPoserOnlySel', 'asPoserAnim', 'asPoserRenderView'):
        c.optionVar(intValue=(name, int(c.checkBox(name, query=True, value=True))))
    if columns < 1:
        c.intField('asPoserNc', edit=True, value=1)
        return update_grid(host)
    if rows < 1:
        c.intField('asPoserNr', edit=True, value=1)
        return update_grid(host)
    c.gridLayout('asPoserDefaultGridLayout', edit=True, numberOfColumns=columns,
                 numberOfRows=rows, width=110*columns, height=90*rows)
    return columns, rows


def update_block(host, ui_name, child):
    c = raw(host)
    button = ui_name + 'IconTextButton' + str(child)
    for menu in c.control(button, query=True, popupMenuArray=True) or ():
        c.deleteUI(menu)
    animation = int(c.rowColumnLayout(ui_name + 'RowColumnLayout' + str(child), query=True, annotation=True))
    menu = c.popupMenu(parent=button)
    c.menuItem(parent=menu, label='查看', command='asPoseView ' + ui_name + ' ' + str(child))
    if not animation:
        c.menuItem(parent=menu, divider=True)
        c.menuItem(parent=menu, label='选择', command='asPoseObjects ' + ui_name + ' ' + button + '" select -add"')
        c.menuItem(parent=menu, label='打关键帧', command='asPoseObjects ' + ui_name + ' ' + button + ' setKeyframe')
        c.menuItem(parent=menu, label='线性关键帧', command='asPoseObjects ' + ui_name + ' ' + button + ' "setKeyframe -itt linear -ott linear"')
    if ui_name == 'asPoserDefault':
        c.menuItem(parent=menu, divider=True)
        c.menuItem(parent=menu, label='修改名称', command='asPoserRename ' + str(child))
        c.menuItem(parent=menu, label='移除按钮', command='asPoserDeletePose ' + ui_name + ' ' + str(child))
        prefix = 'asPoserSnapShoot ' + ui_name + ' ' + str(child) + ' ' + str(animation)
        c.menuItem(parent=menu, label='更新缩略图', command=prefix + ' 1 0')
        if animation:
            c.menuItem(parent=menu, label='更新视频', command=prefix + ' 0 1')
    from .maya_original_selector_binding import bind
    bind(host, ui_name, host_provider=lambda: current_host(host, ui_name))
    return menu


def new_pose(host, load_data=(), animation=False, *, file_loading=False):
    c = raw(host)
    directory = icon_directory(c)
    directory.mkdir(parents=True, exist_ok=True)
    parent = c.setParent(query=True)
    loading = bool(load_data and load_data[0])
    ui_name = 'asPoserDefault' if not loading or file_loading else load_data[0]
    child = child_index(c, ui_name)
    if not loading:
        columns = int(c.intField('asPoserNc', query=True, value=True))
        rows = int(c.intField('asPoserNr', query=True, value=True))
        if child > columns * rows:
            raise ValueError('Grid is full, extend rows or columns !')
        active = current_host(host, ui_name)
        animation = bool(c.checkBox('asPoserAnim', query=True, value=True))
        with active.transaction('保存原版 Poser 姿态／动画'):
            command = active.capture_original_poser_command(ui_name, animation)
            if not command:
                raise ValueError('No valid objects !')
            from .maya_original_poser_snapshot import capture
            image = capture(active, ui_name, child, animation, True, True)
        if animation:
            command += ' ' + str(child)
        if c.about(mac=True):
            c.showWindow('asPoserDefault')
        label = c.textField('asPoserTextField', query=True, text=True)
    else:
        child = int(load_data[4])
        image = str(directory / ('untitled_' + str(child) + '.png'))
        shutil.copyfile(load_data[1], image)
        for extension in ('ma', 'jpg', 'avi'):
            source = replace_extension(load_data[1], extension)
            if c.file(source.as_posix(), query=True, exists=True):
                shutil.copyfile(source, replace_extension(image, extension))
        label, command = load_data[2:4]
        if file_loading:
            command = command.replace(load_data[0], ui_name, 1)
        animation = bool(int(load_data[5]))
    try:
        c.setParent(ui_name + 'GridLayout')
        column = c.columnLayout(ui_name + 'ColumnLayout' + str(child))
        c.gridLayout(ui_name + 'GridLayout', edit=True, position=(column, child))
        c.rowColumnLayout(ui_name + 'RowColumnLayout' + str(child), annotation=str(int(animation)),
                          numberOfColumns=2, columnWidth=((1,100),(2,15)))
        button = c.iconTextButton(ui_name + 'IconTextButton' + str(child), width=100, height=75,
                                  image=image, command=command)
        slider = c.floatSlider(ui_name + 'FloatSlider' + str(child), manage=False, width=10, height=75, horizontal=False)
        text = c.text(ui_name + 'Text' + str(child), height=15, align='center', font='smallBoldLabelFont', label=label)
        if animation:
            c.text(text, edit=True, backgroundColor=(1.,0.,0.))
        if not loading or file_loading:
            update_block(host,ui_name,child)
            c.iconTextButton(button,edit=True,dragCallback=drag,dropCallback=lambda *args:drop(host,*args))
        from .maya_original_selector_binding import _tokens
        tokens = _tokens(command)
        if len(tokens)==3 and tokens[0]=='asSetAttrs':
            statements=[row for row in tokens[2].split(';') if row.strip()]
            if len(statements)==1:
                address=statements[0].split()[0]
                node,attribute=address.split('.',1)
                namespace=c.optionMenu(ui_name+'OptionMenu',query=True,value=True)
                # Loading a saved Poser is valid in an empty scene. Original
                # asNewPose simply leaves the slider hidden if no target exists.
                if namespace=='None':
                    return button
                active=current_host(host,ui_name)
                node=source_control_from_role(active,node)
                sc=active._cmds
                if sc.objExists(node):
                    for keyable in sc.listAttr(node,keyable=True,multi=True,shortNames=True) or ():
                        if attribute!=keyable or not sc.getAttr(node+'.'+attribute,settable=True):
                            continue
                        exists=sc.attributeQuery(attribute,node=node,exists=True)
                        if exists and not sc.attributeQuery(attribute,node=node,rangeExists=True):
                            break
                        limits=sc.attributeQuery(attribute,node=node,range=True) if exists else (0.,1.)
                        c.floatSlider(slider,edit=True,annotation=address,manage=True,minValue=limits[0],maxValue=limits[1])
                        c.connectControl(slider,active.scene_address(node+'.'+attribute))
                        c.text(text,edit=True,label=attribute)
        if loading and not file_loading:
            from .maya_original_selector_binding import bind
            bind(host,ui_name,host_provider=lambda:current_host(host,ui_name))
        return button
    finally:
        c.setParent(parent)


def drag(control, x, y, modifiers):
    return (str(x),str(y),str(modifiers))


def drop(host, drag_control, drop_control, messages, x, y, drop_type):
    """Original fixed 110×90 grid placement and file/UI renaming."""
    if 'IconTextButton' in drop_control:
        return None
    c=raw(host)
    columns=int(c.intField('asPoserNc',query=True,value=True))
    rows=int(c.intField('asPoserNr',query=True,value=True))
    match=re.search(r'[0-9]+$',drag_control)
    if match is None:
        raise ValueError('原版 Poser 拖动控件没有编号')
    old=int(match.group())
    new=ceil(x/110.)+(ceil(y/90.)-1)*columns
    if new==old:
        return old
    if new>columns*rows:
        raise ValueError('out of grid, extend rows or columns !')
    order=c.gridLayout('asPoserDefaultGridLayout',query=True,gridOrder=True)
    if order[new-1].startswith('asPoser'):
        raise ValueError('grid position is occupied !')
    layout='asPoserDefaultColumnLayout'+str(old)
    c.gridLayout('asPoserDefaultGridLayout',edit=True,position=(layout,new))
    children=[name.rsplit('|',1)[-1] for name in c.layout(layout,query=True,childArray=True) or ()]
    grandchildren=[name.rsplit('|',1)[-1] for name in c.layout(children[0],query=True,childArray=True) or ()]
    all_children=(*children,layout,*grandchildren)
    for child in all_children:
        renamed=child[:-len(match.group())]+str(new)
        original=source_command(c,'iconTextButton',child) if c.iconTextButton(child,query=True,exists=True) else None
        c.renameUI(child,renamed)
        if not c.iconTextButton(renamed,query=True,exists=True):
            continue
        image=Path(c.iconTextButton(renamed,query=True,image=True))
        target=Path(str(image)[:-4-len(match.group())]+str(new)+'.png')
        if c.file(image.as_posix(),query=True,exists=True) and image!=target:
            image.replace(target)
            c.iconTextButton(renamed,edit=True,image=target.as_posix())
            for extension in ('jpg','avi'):
                source=replace_extension(image,extension)
                if c.file(source.as_posix(),query=True,exists=True):
                    source.replace(replace_extension(target,extension))
        source=icon_directory(c)/('untitled_'+str(old)+'.ma')
        destination=icon_directory(c)/('untitled_'+str(new)+'.ma')
        if c.file(source.as_posix(),query=True,exists=True) and source!=destination:
            source.replace(destination)
        if original is not None:
            from .maya_original_selector_binding import _tokens
            tokens=_tokens(original)
            if tokens and tokens[0]=='asLoadAttrs':
                original=tokens[0]+' '+tokens[1]+' '+str(new)
            c.iconTextButton(renamed,edit=True,command=original)
    forget(c,all_children)
    update_block(host,'asPoserDefault',new)
    return new
