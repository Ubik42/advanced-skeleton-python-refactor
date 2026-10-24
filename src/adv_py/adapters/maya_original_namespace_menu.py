"""Original namespace menu/filter and Poser slider reconnection, MEL 11590."""
from fnmatch import fnmatchcase


def raw(host):
    return getattr(host._cmds,'raw',host._cmds)


def namespace_from_ui(host,name):
    value=raw(host).optionMenu(name+'OptionMenu',query=True,value=True)
    return '' if value==':' else value


def filter_check(host,name,namespace):
    c=raw(host)
    key='asSelectorFilter_'+name
    value=c.optionVar(query=key) if c.optionVar(exists=key) else ''
    if value in ('',0,'0'):
        return True
    return any(c.file(reference,query=True,namespace=True)==namespace
        and fnmatchcase(reference,value) for reference in c.file(query=True,reference=True) or ())


def char_change(host,name):
    """Reconnect authored single-attribute sliders after a character change."""
    c=raw(host)
    grid=name+'GridLayout'
    from .maya_original_selection_feedback import refresh
    if not c.gridLayout(grid,query=True,exists=True):
        refresh(host)
        return ()
    prefix=namespace_from_ui(host,name)
    changed=[]
    for index,_ in enumerate(c.gridLayout(grid,query=True,gridOrder=True) or (),1):
        slider=name+'FloatSlider'+str(index)
        if not c.floatSlider(slider,query=True,exists=True):
            continue
        address=prefix+c.floatSlider(slider,query=True,annotation=True)
        if c.objExists(address):
            c.connectControl(slider,address)
            changed.append(slider)
    refresh(host)
    return tuple(changed)


def populate(host,name):
    c=raw(host)
    menu=name+'OptionMenu'
    namespaces=[entry for entry in c.namespaceInfo(recurse=True,listOnlyNamespaces=True) or () if entry!='UI']
    namespaces.append('')
    for item in c.optionMenu(menu,query=True,itemListShort=True) or ():
        c.deleteUI(item)
    labels=[]
    for namespace in sorted(namespaces):
        prefix=namespace+':'
        if (c.objExists(prefix+'Main.version') or c.objExists(prefix+'FaceGroup.version')) and filter_check(host,name,namespace):
            c.menuItem(parent=menu,label=prefix)
            labels.append(prefix)
    if not labels:
        label='None' if name=='bodySetup' or name.startswith('asPoser') else ':'
        c.menuItem(parent=menu,label=label)
        labels.append(label)
    return tuple(labels)


def set_from_selection(host,name):
    c=raw(host)
    populate(host,name)
    selection=c.ls(selection=True) or ()
    if selection:
        # Original uses the first token, including its legacy nested behavior.
        namespace=selection[0].split(':',1)[0]+':'
        for index,item in enumerate(c.optionMenu(name+'OptionMenu',query=True,itemListShort=True) or (),1):
            if c.menuItem(item,query=True,label=True)==namespace:
                c.optionMenu(name+'OptionMenu',edit=True,select=index)
                char_change(host,name)
    return namespace_from_ui(host,name)


def update_title(host,name):
    c=raw(host)
    key='asSelectorFilter_'+name
    value=c.optionVar(query=key) if c.optionVar(exists=key) else ''
    for kind,widget,attribute in (('window',name,'title'),('workspaceControl',name+'WorkspaceControl','label')):
        function=getattr(c,kind)
        if function(widget,query=True,exists=True):
            words=function(widget,query=True,**{attribute:True}).split()
            title=words[0] if words else ''
            if value not in ('',0,'0'):
                title+=' filter:'+str(value)
            function(widget,edit=True,**{attribute:title})


def filter_window(host,name):
    c=raw(host)
    key='asSelectorFilter_'+name
    value=c.optionVar(query=key) if c.optionVar(exists=key) else ''
    window='SelectorFilter_'+name
    if c.window(window,query=True,exists=True):
        c.deleteUI(window)
    c.window(window)
    c.columnLayout()
    field='asSelectorFilterTextFieldGrp_'+name
    def changed(*_):
        c.optionVar(stringValue=(key,c.textFieldGrp(field,query=True,text=True)))
        populate(host,name)
        char_change(host,name)
        update_title(host,name)
    c.textFieldGrp(field,text='' if value in (0,'0') else value,changeCommand=changed,
        label='引用文件筛选（例如 *characters*）',columnWidth=(1,200))
    c.showWindow(window)
    return window
