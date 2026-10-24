"""ADV 6.925 asMappingUI's MoCap branch, with Python callbacks.

Keep the native section order, original control names and shared mapping
window. This module creates UI only when explicitly opened in existing Maya.
"""
from pathlib import Path

from adv_py.core.fbx_rig_import import detect_fbx_source_application
from adv_py.core.name_matcher_fit import NameMatcherRow,NameMatcherRules
from adv_py.core.source_name_matcher import source_name_matcher_name


WINDOW='asMappingUI'
PREFIX='asMappingUI'
WEBSITES={
    'AutodeskCharacterGenerator':'charactergenerator.autodesk.com',
    'CharacterCreator':'www.reallusion.com/character-creator',
    'Daz3d':'www.daz3d.com','DeepMotion':'www.deepmotion.com',
    'iPiSoft':'www.ipisoft.com','Mixamo':'www.mixamo.com',
    'MotionBuilder':'www.autodesk.com','MotionMaker':'www.autodesk.com',
    'Plask':'app.plask.ai','Poser':'smithmicro.com/poser',
    'Unreal':'www.unrealengine.com','Rokoko':'www.rokoko.com',
    'ReadyPlayerMe':'readyplayer.me',
}


class SourceMocapMappingUI:
    def __init__(self,controller,namespace,commands):
        self.controller=controller
        self.namespace=namespace
        self.c=commands
        self.rows=[]

    def _field(self,suffix):return self.c.textField(PREFIX+suffix,query=True,text=True)

    def _value(self,suffix):return self.c.checkBox(PREFIX+suffix,query=True,value=True)

    def _run(self,action,*args):
        try:return action()
        except (ValueError,RuntimeError) as error:
            self.c.warning(str(error))
            self.c.confirmDialog(title='操作未完成',message=str(error),button=('确定',))
            return None

    def _section(self,suffix,label):
        c=self.c
        name=PREFIX+suffix+'FrameLayout'
        # The source stores these native frame names in optionVars.
        def folded(closed):c.optionVar(intValue=(name,int(closed)))
        collapsed=bool(c.optionVar(query=name)) if c.optionVar(exists=name) else True
        c.frameLayout(name,parent=PREFIX+'ColumnLayout1',width=320,
            collapsable=True,collapse=collapsed,label=label,
            collapseCommand=lambda *_:folded(True),expandCommand=lambda *_:folded(False))
        return c.columnLayout(adjustableColumn=True)

    def _two_columns(self):
        c=self.c
        c.rowLayout(numberOfColumns=3,columnWidth3=(150,10,150))
        c.text(label='AdvancedSkeleton');c.text(label='|');c.text(label='来源骨架')
        c.setParent('..');c.separator(width=300)

    def _button(self,label,action,*,parent=None):
        args={'label':label,'width':150,'command':lambda *_:self._run(action)}
        if parent:args['parent']=parent
        return self.c.button(**args)

    def clear(self,*args):
        c=self.c
        for layout,_,_ in self.rows:c.deleteUI(layout)
        self.rows.clear()
        for suffix,text in (('Right','Right'),('Left','Left'),('Middle','')):
            c.textFieldGrp(PREFIX+'Side'+suffix+'TextFieldGrp',edit=True,text=text)
        c.checkBox(PREFIX+'SideBeforeNameCheckBox',edit=True,value=True)
        c.checkBox(PREFIX+'SideUnderScoreCheckBox',edit=True,value=False)
        self.example()

    def add_joint(self,advanced='',external='',*args):
        c=self.c;index=len(self.rows)+1
        layout=c.rowLayout(PREFIX+'JointsRowLayout'+str(index),
            parent=PREFIX+'JointsColumnLayout',numberOfColumns=3,columnWidth3=(150,10,150))
        a=c.textField(PREFIX+'JointsTextFieldA'+str(index),width=130,text=advanced)
        c.text(label='|')
        b=c.textField(PREFIX+'JointsTextFieldB'+str(index),width=130,text=external)
        self.rows.append((layout,a,b))
        c.setParent('..')

    def mapping(self):
        c=self.c
        return tuple(NameMatcherRow(c.textField(a,query=True,text=True),
                                   c.textField(b,query=True,text=True))
                     for _,a,b in self.rows)

    def rules(self):
        c=self.c
        return NameMatcherRules(*(c.textFieldGrp(PREFIX+'Side'+suffix+'TextFieldGrp',
            query=True,text=True) for suffix in ('Right','Left','Middle')),
            self._value('SideBeforeNameCheckBox'),self._value('SideUnderScoreCheckBox'))

    def example(self,*args):
        rules=self.rules()
        self.c.text(PREFIX+'SideResultExampleText',edit=True,
            label=source_name_matcher_name('Arm',rules))

    def load_template(self,*args):
        c=self.c;name=c.optionMenu(PREFIX+'Files',query=True,value=True)
        c.text(PREFIX+'WWW',edit=True,label=WEBSITES.get(name,''))
        self.clear()
        if name!='*New':
            template=self.controller.preparation_source_name_matcher_template(name,mocap=True)
            for suffix,value in (('Right',template.rules.right),('Left',template.rules.left),
                                 ('Middle',template.rules.middle)):
                c.textFieldGrp(PREFIX+'Side'+suffix+'TextFieldGrp',edit=True,text=value)
            c.checkBox(PREFIX+'SideBeforeNameCheckBox',edit=True,value=template.rules.side_before_name)
            c.checkBox(PREFIX+'SideUnderScoreCheckBox',edit=True,value=template.rules.side_underscore)
            for row in template.rows:self.add_joint(row.fit_joint,row.source_base)
        self.example()

    def export_template(self):
        paths=self.c.fileDialog2(fileMode=0,caption='导出动捕映射',fileFilter='动捕映射 (*.txt)') or ()
        if not paths:return None
        rules=self.rules()
        return self.controller.preparation_source_name_matcher_export(Path(paths[0]),
            tuple((row.fit_joint,row.source_base) for row in self.mapping()),
            right=rules.right,left=rules.left,middle=rules.middle,
            side_before_name=rules.side_before_name,side_underscore=rules.side_underscore)

    def scan(self):
        # asMoCapMatcherScan only invokes namespace detection. It does not
        # guess joint mappings or replace the user's selected template.
        namespace=''
        for selected in self.c.ls(selection=True) or ():
            tokens=selected.split(':')
            if len(tokens)>1:namespace=tokens[0]
        self.c.textField(PREFIX+'NameSpacesTextFieldB1',edit=True,text=namespace)
        return namespace

    def _namespace(self):
        return self._field('NameSpacesTextFieldA1').strip(':') or ':'

    def _arguments(self):
        rules=self.rules()
        return dict(right=rules.right,left=rules.left,middle=rules.middle,
            side_before_name=rules.side_before_name,side_underscore=rules.side_underscore)

    def zero_out(self):
        template=self.c.optionMenu(PREFIX+'Files',query=True,value=True)
        return self.controller.tools_name_matcher_zero_out(self._namespace(),None,
            tuple((row.fit_joint,row.source_base) for row in self.mapping()),
            **self._arguments(),template_name=None if template=='*New' else template,
            source_namespace=self._field('NameSpacesTextFieldB1'))

    def connect(self):
        return self.controller.tools_name_matcher_mocap(self._namespace(),None,
            tuple((row.fit_joint,row.source_base) for row in self.mapping()),
            **self._arguments(),use_extra=self._value('ExtraCheckBox'),
            source_namespace=self._field('NameSpacesTextFieldB1'))

    def show(self):
        c=self.c
        if c.window(WINDOW,exists=True):c.deleteUI(WINDOW)
        c.window(WINDOW,title='MoCapMatcher',widthHeight=(340,700))
        c.formLayout(PREFIX+'FormLayout')
        scroll=c.scrollLayout(PREFIX+'ScrollLayout')
        c.columnLayout(PREFIX+'ColumnLayout1',adjustableColumn=True)
        self._section('Templates','模板')
        c.rowLayout(numberOfColumns=4,columnWidth4=(10,25,200,100))
        c.separator(style='none');c.text(label='文件：')
        c.optionMenu(PREFIX+'Files',changeCommand=lambda *_:self._run(self.load_template))
        c.setParent('..');c.text(PREFIX+'WWW',label='',enable=False)
        c.separator(height=15,style='none')
        self._button('导出当前配置',self.export_template)
        self._section('Side','侧别')
        for suffix,label,value in (('Right','右侧：','Right'),('Left','左侧：','Left'),('Middle','中间：','')):
            change={'changeCommand':self.example} if suffix=='Right' else {}
            c.textFieldGrp(PREFIX+'Side'+suffix+'TextFieldGrp',columnWidth2=(45,60),
                label=label,text=value,**change)
        c.checkBox(PREFIX+'SideBeforeNameCheckBox',label='侧别在名称前',value=True,changeCommand=self.example)
        c.checkBox(PREFIX+'SideUnderScoreCheckBox',label='用下划线分隔',changeCommand=self.example)
        c.text(label='名称示例：');c.text(PREFIX+'SideResultExampleText',label='RightArm',font='boldLabelFont')
        self._section('Joints','关节')
        self._two_columns()
        c.columnLayout(PREFIX+'JointsColumnLayout',adjustableColumn=True)
        c.setParent('..')
        self._button('添加关节',lambda:self.add_joint())
        self._button('清空',self.clear)
        self._section('NameSpaces','命名空间')
        self._two_columns()
        c.rowLayout(numberOfColumns=3,columnWidth3=(150,10,150))
        c.textField(PREFIX+'NameSpacesTextFieldA1',width=130,
            text='' if self.namespace==':' else self.namespace.rstrip(':')+':')
        c.text(label='|');c.textField(PREFIX+'NameSpacesTextFieldB1',width=130)
        c.setParent('..');self._button('从所选对象检测',self.scan)
        self._section('TopNode','顶层节点')
        self._two_columns()
        c.rowLayout(numberOfColumns=3,columnWidth3=(150,10,150))
        c.textField(PREFIX+'TopNodeTextFieldA1',width=130,text='Group',editable=False)
        c.text(label='|');c.textField(PREFIX+'TopNodeTextFieldB1',width=130)
        self._section('Functions','操作')
        c.text(label='1：导入动捕骨架。',align='left')
        c.separator(height=10,style='none')
        c.text(label='2：选中动捕骨架。',align='left');self._button('扫描动捕骨架',self.scan)
        c.separator(height=10,style='none')
        c.text(label='3：缩放动捕骨架，使其与角色匹配。',align='left')
        c.separator(height=10,style='none')
        c.text(label='4：移到动画起点，归零动捕关节。',align='left')
        self._button('归零动捕关节',self.zero_out)
        c.text(label='必要时对齐两套骨架。',align='left')
        c.separator(height=10,style='none')
        c.rowLayout(numberOfColumns=2,columnWidth2=(160,60))
        self._button('连接动捕骨架',self.connect)
        c.checkBox(PREFIX+'ExtraCheckBox',label='Extra');c.setParent('..')
        self._button('断开动捕骨架',lambda:self.controller.tools_name_matcher_disconnect(self._namespace()))
        self._button('烘焙',lambda:self.controller.tools_name_matcher_bake(self._namespace()))
        c.formLayout(PREFIX+'FormLayout',edit=True,
            attachForm=tuple((scroll,edge,0) for edge in ('top','bottom','left','right')))
        c.showWindow(WINDOW)
        catalog=self.controller.preparation_source_name_matcher_catalog(mocap=True)
        names=[path.stem for path in catalog if not path.name.startswith('.') and path.name!='incrementalSave']
        for name in (*names,'*New'):c.menuItem(label=name,parent=PREFIX+'Files')
        if 'MotionBuilder' in names:c.optionMenu(PREFIX+'Files',edit=True,value='MotionBuilder')
        detected=detect_fbx_source_application(tuple(c.ls(recursive=True,long=True) or ()))
        if c.ls('mixamorig:*',recursive=True):
            c.textField(PREFIX+'NameSpacesTextFieldB1',edit=True,text='mixamorig')
        if detected in names:c.optionMenu(PREFIX+'Files',edit=True,value=detected)
        if c.namespace(exists='NameMatcher'):
            c.textField(PREFIX+'NameSpacesTextFieldB1',edit=True,text='NameMatcher')
        self.load_template()
        return WINDOW


def show_mocap_matcher(controller,namespace):
    from maya import cmds
    return SourceMocapMappingUI(controller,namespace,cmds).show()
