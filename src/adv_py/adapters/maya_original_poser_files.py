"""Original Poser Open/Save/SaveAs/shelf through Python, MEL 9459–10155."""
from pathlib import Path
import re
import shutil

from adv_py.core.original_poser_file import OriginalPoserButton,OriginalPoserFile,decode,encode
from .maya_original_poser_store import icon_directory
from .maya_original_ui_commands import command as source_command


def raw(host):
    return getattr(host._cmds,'raw',host._cmds)


def browse(host,action):
    c=raw(host)
    file=c.fileDialog(directoryMask='*.mel',mode=0 if action=='Open' else 1)
    if not file:return 0
    if action=='Open':return open_file(host,file)
    if action=='SaveAs':return save_as(host,file)
    raise ValueError('未知原版 Poser 文件操作：'+action)


def capture(host,name):
    c=raw(host)
    ui='asPoserDefault'
    grid=ui+'GridLayout'
    sets=''
    for item in c.menu('asPoserControlSetsMenu',query=True,itemArray=True) or ():
        if c.menuItem(item,query=True,checkBox=True):
            sets+=c.menuItem(item,query=True,label=True)+' '
    buttons=[]
    for child,widget in enumerate(c.gridLayout(grid,query=True,gridOrder=True) or (),1):
        if not widget.rsplit('|',1)[-1].startswith('asPoser'):
            continue
        number=str(child)
        button=ui+'IconTextButton'+number
        slider=ui+'FloatSlider'+number
        text=ui+'Text'+number
        command=source_command(c,'iconTextButton',button)
        if not isinstance(command,str):
            raise ValueError('原版 Poser 按钮没有可保存的原始指令')
        command=command.replace(ui,'asPoser'+name,1).replace('untitled_',name+'_',1)
        image=Path(c.iconTextButton(button,query=True,image=True))
        match=re.search(r'([0-9]+)$',image.stem)
        if match is None:raise ValueError('原版 Poser 缩略图文件没有编号')
        animation=bool(int(c.rowColumnLayout(ui+'RowColumnLayout'+number,query=True,annotation=True)))
        color=c.text(text,query=True,backgroundColor=True)
        buttons.append(OriginalPoserButton(child,int(match.group(1)),command,
            c.text(text,query=True,label=True),animation,
            bool(c.floatSlider(slider,query=True,manage=True)),
            c.floatSlider(slider,query=True,annotation=True),
            float(c.floatSlider(slider,query=True,minValue=True)),
            float(c.floatSlider(slider,query=True,maxValue=True)),bool(color and color[0]==1)))
    return OriginalPoserFile(name,int(c.intField('asPoserNc',query=True,value=True)),
        int(c.intField('asPoserNr',query=True,value=True)),
        int(c.gridLayout(grid,query=True,cellWidth=True)),int(c.gridLayout(grid,query=True,cellHeight=True)),
        sets,tuple(buttons))


def _original_source(source=None):
    if source is not None:return Path(source)
    return Path(__file__).resolve().parents[3]/'local'/'adv_6_925'/'AdvancedSkeleton.mel'


def _helpers(source):
    """Keep the original generated asset's standalone MEL compatibility."""
    text=source.read_text(encoding='utf-8-sig')
    begin='//-- ASTools Procedures Starts Here --//'
    end='//-- ASTools Procedures Ends Here --//'
    lines=text.splitlines()
    # Earlier source procedures contain these markers inside quoted strings.
    # asSave compares whole input lines; a substring split would copy those
    # procedures' parsing code instead of the real ASTools section.
    starts=[index for index,line in enumerate(lines) if line==begin]
    stops=[index for index,line in enumerate(lines) if line==end]
    if len(starts)!=1 or len(stops)!=1 or stops[0]<=starts[0]:
        raise ValueError('原版源码缺少 Poser 发布所需的 ASTools 段')
    section=lines[starts[0]+1:stops[0]]
    return '\n'+begin+'\n'+'\n'.join(line for line in section if '******' not in line)+'\n'+end+'\n'


def _install_template(source,name):
    template=source.parent/'install.mel'
    if not template.is_file():return None
    result=[]
    paused=False
    for line in template.read_text(encoding='utf-8-sig').splitlines()[1:]:
        if line=='//--installTemplate pause--//':paused=True
        if line=='//--installTemplate resume--//':
            paused=False
            continue
        if paused:continue
        if line.startswith('string $scriptName='):
            line='string $scriptName="'+name+'";'
        elif line.startswith('string $sourceFile='):
            line='string $sourceFile=$asInstallScriptLocation+"../"+$scriptName+".mel";'
        elif line.startswith('string $icon='):
            line='string $icon=$asInstallScriptLocation+"'+name+'_background32.png";'
        elif line.startswith('string $command='):
            line=r'string $command="source \""+$sourceFile+"\"";'
        result.append(line)
    return '\n'.join(result)+'\n'


def save(host,*,source=None):
    c=raw(host)
    name=c.text('asPoserProjectName',query=True,label=True)
    if name=='untitled':return browse(host,'SaveAs')
    parent=Path(c.text('asPoserProjectPath',query=True,label=True)).resolve()
    folder=(parent/name).resolve()
    if folder.parent!=parent:
        raise ValueError('Poser 发布图片目录超出项目目录')
    value=capture(host,name)
    original=_original_source(source)
    # Read all source templates and serialize first, before replacing files.
    contents=encode(value)+_helpers(original)
    install=_install_template(original,name)
    folder.mkdir(parents=True,exist_ok=True)
    for file in folder.iterdir():
        if file.is_file():file.unlink()
    for file in icon_directory(c).iterdir():
        if file.is_file() and not file.name.endswith('.tif'):
            shutil.copyfile(file,folder/file.name.replace('untitled_',name+'_',1))
    destination=parent/(name+'.mel')
    destination.write_text(contents,encoding='utf-8')
    if install is not None:
        (folder/'install.mel').write_text(install,encoding='utf-8')
    c.window('asPoserDefault',edit=True,title='PoserDesigner :'+name)
    return str(destination)


def save_as(host,file,*,source=None):
    if not file:return 0
    c=raw(host)
    file=Path(file).expanduser().absolute()
    selected=tuple(c.ls(selection=True) or ())
    temporary=None
    try:
        with host.transaction('原版 Poser 另存为'):
            host._transaction_changed=True
            temporary=c.createNode('transform')
            node=c.createNode('transform',parent=temporary,name=file.name.split('.',1)[0])
            name=node.rsplit('|',1)[-1]
            c.delete(temporary)
            temporary=None
        c.text('asPoserProjectPath',edit=True,label=file.parent.as_posix()+'/')
        c.text('asPoserProjectName',edit=True,label=name)
        save(host,source=source)
    finally:
        if temporary and c.objExists(temporary):c.delete(temporary)
        c.select(selected,replace=True) if selected else c.select(clear=True)
    return 1


def open_file(host,file):
    from .maya_original_selection_feedback import file_loading,refresh
    with file_loading():
        result=_open_file(host,file)
    refresh(host)
    return result


def _open_file(host,file):
    c=raw(host)
    file=Path(file).expanduser().absolute()
    value=decode(file.read_text(encoding='utf-8-sig'))
    selected=tuple(c.ls(selection=True) or ())
    c.select(clear=True)
    from .maya_original_poser_ui import new_pose,update_grid
    try:
        c.intField('asPoserNc',edit=True,value=value.columns)
        c.intField('asPoserNr',edit=True,value=value.rows)
        update_grid(host)
        for button in value.buttons:
            image=file.parent/value.name/(value.name+'_'+str(button.image_number)+'.png')
            command=button.command.replace('asPoser'+value.name,'asPoserDefault',1)
            # asOpen imports occupied slots into the current default designer.
            child=str(button.child)
            animation='asSetAttrs ' not in command
            new_pose(host,('asPoserDefault',str(image),button.label,command,child,str(int(animation))),
                animation,file_loading=True)
        c.text('asPoserProjectPath',edit=True,label=file.parent.as_posix()+'/')
        c.text('asPoserProjectName',edit=True,label=file.stem)
        c.window('asPoserDefault',edit=True,title='PoserDesigner :'+file.stem)
    finally:
        c.select(selected,replace=True) if selected else c.select(clear=True)
    return 1


def to_shelf(host,*,shelf_top_level=None):
    c=raw(host)
    name=c.text('asPoserProjectName',query=True,label=True)
    if name=='untitled':raise ValueError('请先保存 Poser 项目，再放到工具架')
    parent=Path(c.text('asPoserProjectPath',query=True,label=True))
    icon=parent/name/(name+'_background32.png')
    if not icon.is_file():icon='absolute.png'
    if shelf_top_level is None:
        from maya import mel
        shelf_top_level=mel.eval('$advPyShelf=$gShelfTopLevel')
    previous=c.setParent(query=True)
    try:
        if not c.tabLayout(shelf_top_level,exists=True):return None
        shelf=c.tabLayout(shelf_top_level,query=True,selectTab=True)
        c.setParent(shelf)
        # Python shelf invokes the Python reader; the asset stays native MEL.
        destination=str(parent/(name+'.mel'))
        command=('from adv_py.adapters.maya_driving_systems import MayaDrivingSystemsHost\n'
            'from adv_py.adapters.maya_original_poser_files import show_published\n'
            'show_published(MayaDrivingSystemsHost(),'+repr(destination)+')')
        return c.shelfButton(command=command,sourceType='python',annotation='Poser:'+name,
            label='Poser:'+name,image1=str(icon),style=c.shelfLayout(shelf,query=True,style=True),
            width=c.shelfLayout(shelf,query=True,cellWidth=True),height=c.shelfLayout(shelf,query=True,cellHeight=True))
    finally:c.setParent(previous)


def show_published(host,file):
    """Construct the original compact published Poser rather than the designer."""
    c=raw(host)
    file=Path(file).expanduser().absolute()
    value=decode(file.read_text(encoding='utf-8-sig'))
    name='asPoser'+value.name
    from .maya_original_namespace_menu import populate,char_change
    if c.window(name,query=True,exists=True):
        populate(host,name)
        char_change(host,name)
        c.showWindow(name)
        return name
    from .maya_original_poser_ui import update_block
    c.window(name,resizeToFitChildren=True,menuBar=True,title=value.name)
    from .maya_original_reference_ui import published_menus
    from .maya_original_namespace_menu import update_title
    update_title(host,name)
    published_menus(host,name)
    form=c.formLayout(name+'FormLayout')
    c.text(name+'ControlSetsText',manage=False,label=value.control_sets)
    option=c.optionMenu(name+'OptionMenu',changeCommand=lambda *_:char_change(host,name))
    scroll=c.scrollLayout(name+'ScrollLayout')
    c.gridLayout(name+'GridLayout',cellWidth=value.cell_width,cellHeight=value.cell_height,
        numberOfColumns=value.columns,numberOfRows=value.rows)
    c.formLayout(form,edit=True,attachForm=((option,'top',0),(scroll,'bottom',0),
        (scroll,'left',0),(scroll,'right',0)),attachControl=(scroll,'top',0,option))
    for button in value.buttons:
        child=str(button.child)
        c.setParent(name+'GridLayout')
        column=c.columnLayout(name+'ColumnLayout'+child)
        c.rowColumnLayout(name+'RowColumnLayout'+child,annotation=str(int(button.animation)),
            numberOfColumns=2,columnWidth=((1,100),(2,15)))
        image=file.parent/value.name/(value.name+'_'+str(button.image_number)+'.png')
        c.iconTextButton(name+'IconTextButton'+child,width=100,height=75,image=image.as_posix(),command=button.command)
        c.floatSlider(name+'FloatSlider'+child,annotation=button.slider_annotation,
            manage=button.slider_managed,minValue=button.slider_minimum,maxValue=button.slider_maximum,
            width=10,height=75,horizontal=False)
        flags=dict(height=15,align='center',font='smallBoldLabelFont',label=button.label)
        if button.red_label:flags['backgroundColor']=(1.,0.,0.)
        c.text(name+'Text'+child,**flags)
        c.gridLayout(name+'GridLayout',edit=True,position=(column,button.child))
        update_block(host,name,button.child)
    populate(host,name)
    char_change(host,name)
    from .maya_original_selection_feedback import install,refresh
    install(host)
    refresh(host)
    c.showWindow(name)
    return name
