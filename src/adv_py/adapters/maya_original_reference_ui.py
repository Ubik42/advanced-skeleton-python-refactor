"""Original reference browser/editor and published-variant menu, MEL 22880.

Only Maya's own reference browser procedures cross the MEL boundary. Variant
discovery and reference replacement use the original namespace/file rules.
"""
from pathlib import Path
import json

from .maya_original_namespace_menu import namespace_from_ui,populate


def raw(host):
    return getattr(host._cmds,'raw',host._cmds)


def editor(host):
    from maya import mel
    return mel.eval('ReferenceEditor;')


def browser(host,model=False):
    c=raw(host)
    from maya import mel
    if c.about(isLT=True):
        raise ValueError('Maya LT does not have Reference, Import the model instead')
    fields=(('referenceOptionsRenamePrefix','stringValue','model' if model else 'anim'),
        ('referenceUseNamespacesDuringFileIO','intValue',1),
        ('referenceOptionsUseRenamePrefix','intValue',1),
        ('ReferenceMergeOptionValue','stringValue','radioNamespaceOnString' if model else 'radioNamespaceOnFileName'),
        ('defaultFileReferenceType','stringValue','mayaBinary'))
    before=set(c.ls(assemblies=True) or ()) if model else set()
    previous=[]
    radio=None
    def configure():
        nonlocal previous,radio
        previous=[(name,kind,c.optionVar(query=name)) for name,kind,_ in fields]
        radio=mel.eval('global string $selectedNamespaceRadioButton; $selectedNamespaceRadioButton;')
        for name,kind,value in fields:
            c.optionVar(**{kind:(name,value)})
        if radio:
            mel.eval('$selectedNamespaceRadioButton='+json.dumps(fields[3][2])+';')
    # The source deliberately repeats this after CreateReferenceOptions, since
    # Maya's options UI can rewrite those reference preferences on first open.
    configure()
    try:
        mel.eval('CreateReferenceOptions;')
        configure()
        mel.eval('CreateReference;')
    finally:
        for name,kind,value in previous:
            c.optionVar(**{kind:(name,value)})
        if radio:
            mel.eval('$selectedNamespaceRadioButton='+json.dumps(radio)+';')
    c.select(clear=True)
    if model:
        roots=tuple(node for node in c.ls(assemblies=True) or () if node not in before)
        if roots:c.select(roots,add=True)
        if c.objExists('Hi'):
            if c.nodeType('Hi')=='displayLayer':
                c.editDisplayLayerMembers('Hi',*(c.ls(selection=True) or ()),noRecurse=True)
        else:
            c.createDisplayLayer(name='Hi',number=1,noRecurse=True)
            c.setAttr('Hi.displayType',1)
    else:
        for menu in c.lsUI(type='optionMenu') or ():
            name=menu.rsplit('|',1)[-1]
            if name.startswith(('asSelector','asPicker')) and name.endswith('OptionMenu'):
                populate(host,name.removesuffix('OptionMenu'))
    c.select(clear=True)


def variants(host,ui_name):
    """Return original published MB choices, including the disabled current file."""
    c=raw(host)
    namespace=namespace_from_ui(host,ui_name).replace(':','',1)
    rows=[]
    for reference in c.ls(type='reference') or ():
        if reference=='sharedReferenceNode':continue
        prefix=c.referenceQuery(reference,namespace=True).replace(':','',1)
        if prefix!=namespace:continue
        source=c.referenceQuery(reference,filename=True).split('{',1)[0]
        parent=Path(source).parent
        names=c.getFileList(folder=parent.as_posix()+'/',filespec=prefix+'*.mb') or ()
        for name in names:
            destination=parent/name
            rows.append((reference,name,destination.as_posix(),destination.as_posix()!=source))
    return tuple(rows)


def populate_replace(host,ui_name):
    c=raw(host)
    parent=ui_name+'FileReplaceMenuItem'
    # This submenu owns its entries; clearing its actual children also handles
    # Poser windows instead of the source's hard-coded biped child-name pattern.
    for item in c.menu(parent,query=True,itemArray=True) or ():
        c.deleteUI(item)
    rows=variants(host,ui_name)
    for reference,label,path,enabled in rows:
        c.menuItem(parent=parent,label=label,enable=enabled,
            command=lambda *_,reference=reference,path=path:c.file(path,loadReference=reference))
    return rows


def published_menus(host,ui_name):
    c=raw(host)
    from .maya_original_namespace_menu import char_change,filter_window
    menu=c.menu(label='文件')
    c.menuItem(parent=menu,label='创建引用…',command=lambda *_:browser(host))
    c.menuItem(parent=menu,label='引用编辑器',command=lambda *_:editor(host))
    c.menuItem(ui_name+'FileReplaceMenuItem',parent=menu,label='替换',subMenu=True,
        postMenuCommand=lambda *_:populate_replace(host,ui_name))
    c.setParent(menu,menu=True)
    c.menuItem(parent=menu,divider=True)
    def export(*_):
        from .maya_original_fbx_export import MayaOriginalFbxExportHost
        from adv_py.application.original_fbx_export import ExportOriginalFbx
        namespace=namespace_from_ui(host,ui_name).strip(':') or None
        active=MayaOriginalFbxExportHost(namespace=namespace)
        active._original_export_ui_name=ui_name
        return ExportOriginalFbx(active).apply()
    c.menuItem(parent=menu,label='导出 FBX…',command=export)
    c.setParent(ui_name)
    edit=c.menu(label='编辑')
    def refresh(*_):
        populate(host,ui_name)
        char_change(host,ui_name)
    c.menuItem(parent=edit,label='刷新',command=refresh)
    c.menuItem(parent=edit,label='筛选',command=lambda *_:filter_window(host,ui_name))
    c.setParent(ui_name)
