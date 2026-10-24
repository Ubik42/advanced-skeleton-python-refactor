"""Original generated Poser MEL data, read without evaluating its procedures.

The file remains the original publish format: command strings, native grid
widgets and neighboring image/animation files. Python reads the generated
window's data; embedded MEL helpers are never executed by this reader.
"""
from dataclasses import dataclass
import json
import re


@dataclass(frozen=True)
class OriginalPoserButton:
    child: int
    image_number: int
    command: str
    label: str
    animation: bool
    slider_managed: bool=False
    slider_annotation: str=''
    slider_minimum: float=0.
    slider_maximum: float=1.
    red_label: bool=False


@dataclass(frozen=True)
class OriginalPoserFile:
    name: str
    columns: int
    rows: int
    cell_width: int
    cell_height: int
    control_sets: str
    buttons: tuple[OriginalPoserButton,...]


def quote(value):
    return json.dumps(value,ensure_ascii=False)


def _statements(text):
    """Split MEL statements while preserving quoted semicolons and escapes."""
    result=[]
    quoted=False
    escaped=False
    comment=False
    index=0
    while index<len(text):
        character=text[index]
        if comment:
            if character=='\n':
                comment=False
                result.append(' ')
            index+=1
            continue
        if not quoted and text[index:index+2]=='//':
            comment=True
            index+=2
            continue
        result.append(character)
        if escaped:
            escaped=False
        elif quoted and character=='\\':
            escaped=True
        elif character=='"':
            quoted=not quoted
        elif character==';' and not quoted:
            yield ''.join(result[:-1]).strip()
            result=[]
        index+=1
    if quoted:
        raise ValueError('原版 Poser 文件字符串未闭合')


def _body(text):
    start=re.search(r'global\s+proc\s+asPoser([A-Za-z_][A-Za-z_0-9]*)\s*\(\s*\)\s*\{',text)
    if start is None:
        raise ValueError('文件没有原版 Poser 发布窗口过程')
    depth=1
    quoted=False
    escaped=False
    comment=False
    index=start.end()
    begin=index
    while index<len(text):
        ch=text[index]
        if comment:
            if ch=='\n':comment=False
        elif not quoted and text[index:index+2]=='//':
            comment=True
            index+=1
        elif escaped:escaped=False
        elif quoted and ch=='\\':escaped=True
        elif ch=='"':quoted=not quoted
        elif not quoted:
            if ch=='{':depth+=1
            elif ch=='}':
                depth-=1
                if depth==0:return start.group(1),text[begin:index]
        index+=1
    raise ValueError('原版 Poser 发布窗口过程未闭合')


def _string(statement,flag,default=''):
    match=re.search(r'(?:^|\s)'+re.escape(flag)+r'\s+("(?:\\.|[^"\\])*")',statement)
    return json.loads(match.group(1)) if match else default


def _number(statement,flag,default):
    match=re.search(r'(?:^|\s)'+re.escape(flag)+r'\s+([-+0-9.eE]+)(?=\s|$)',statement)
    return float(match.group(1)) if match else default


def decode(text):
    name,body=_body(text)
    ui='asPoser'+name
    columns=rows=None
    width,height=110,90
    sets=''
    command=None
    buttons={}
    animations={}
    for statement in _statements(body):
        assignment=re.search(r'(?:^|\n)\s*\$cmd\s*=\s*("(?:\\.|[^"\\])*")\s*$',statement)
        if assignment:
            command=json.loads(assignment.group(1))
        lines=statement.splitlines()
        line=next((line.strip() for line in reversed(lines) if line.strip()),'')
        if line.startswith('gridLayout ') and line.endswith(ui+'GridLayout') and ' -e ' not in line:
            columns=int(_number(line,'-nc',0))
            rows=int(_number(line,'-nr',0))
            width=int(_number(line,'-cw',110))
            height=int(_number(line,'-ch',90))
        elif line.startswith('text ') and line.endswith(ui+'ControlSetsText'):
            sets=_string(line,'-l')
        elif line.startswith('rowColumnLayout '):
            match=re.search(re.escape(ui)+r'RowColumnLayout([0-9]+)$',line)
            if match:animations[int(match.group(1))]=bool(_number(line,'-ann',0))
        elif line.startswith('iconTextButton '):
            match=re.search(re.escape(ui)+r'IconTextButton([0-9]+)$',line)
            if not match:continue
            child=int(match.group(1))
            image=re.search(r'\$asIconLocation\s*\+\s*("(?:\\.|[^"\\])*")',line)
            if image is None or command is None:
                raise ValueError('原版 Poser 按钮缺少原始命令或图片路径')
            image_name=json.loads(image.group(1))
            image_match=re.fullmatch(re.escape(name)+r'_([0-9]+)\.png',image_name)
            if image_match is None:
                raise ValueError('原版 Poser 图片编号格式无效')
            if child in buttons:raise ValueError('原版 Poser 网格按钮编号重复')
            buttons[child]=dict(child=child,image_number=int(image_match.group(1)),
                command=command,label='',animation=animations.get(child,False))
        elif line.startswith('floatSlider '):
            match=re.search(re.escape(ui)+r'FloatSlider([0-9]+)$',line)
            if match and int(match.group(1)) in buttons:
                buttons[int(match.group(1))].update(slider_managed=bool(_number(line,'-m',0)),
                    slider_annotation=_string(line,'-ann'),slider_minimum=_number(line,'-min',0),
                    slider_maximum=_number(line,'-max',1))
        elif line.startswith('text '):
            match=re.search(re.escape(ui)+r'Text([0-9]+)$',line)
            if match and int(match.group(1)) in buttons:
                buttons[int(match.group(1))].update(label=_string(line,'-l'),
                    red_label=bool(re.search(r'(?:^|\s)-bgc\s+1\s+0\s+0(?:\s|$)',line)))
    if columns is None or rows is None or columns<1 or rows<1:
        raise ValueError('原版 Poser 发布网格尺寸缺失或无效')
    if any(child<1 or child>columns*rows for child in buttons):
        raise ValueError('原版 Poser 发布按钮超出网格')
    return OriginalPoserFile(name,columns,rows,width,height,sets,
        tuple(OriginalPoserButton(**buttons[index]) for index in sorted(buttons)))


def encode(value):
    """Emit the same native data layout as original asSave's Poser branch."""
    name=value.name
    if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',name) is None:
        raise ValueError('Poser 发布名称不是 Maya 节点名称')
    ui='asPoser'+name
    lines=['//This file has been generated by AdvancedSkeletonPoser//',
        '//Using AdvancedSkeleton Version: 6.925//','',
        'global proc '+ui+' ()','{',
        'if (`window -q -ex '+ui+'`) { asPopulateNameSpaceMenu '+ui+'; showWindow '+ui+'; return; }',
        'string $asSelectorScriptLocation=`asSelectorScriptLocation`;',
        'string $asIconLocation=$asSelectorScriptLocation+'+quote(name+'/')+';',
        'string $cmd;',
        'window -rtf 1 -mb 1 -t '+quote(name)+' '+ui+';',
        'asSetFilterUpdateWindowTitle '+ui+';',
        'menu -l File;',
        '\tmenuItem -l "Create Reference.." -c "asReferenceBrowser 0";',
        '\tmenuItem -l "Reference Editor" -c "asReferenceEditor";',
        '\tmenuItem -l "Replace" -sm 1 -postMenuCommand '+quote('asPopulateReplaceMenu '+ui)+' '+ui+'FileReplaceMenuItem;',
        '\tsetParent -menu ..;',
        '\tmenuItem -d 1;',
        '\tmenuItem -l "Export Fbx.." -c '+quote('asExportFbxBrowser '+ui)+';',
        '\tsetParent..;',
        'menu -l Edit;',
        '\tmenuItem -l Refresh -c '+quote('asPopulateNameSpaceMenu '+ui)+';',
        '\tmenuItem -l Filter -c '+quote('asFilterNameSpaceMenuUI '+ui)+';',
        '\tsetParent..;',
        'formLayout '+ui+'FormLayout;',
        'text -m 0 -l '+quote(value.control_sets)+' '+ui+'ControlSetsText;',
        'optionMenu -cc '+quote('asCharChange '+ui)+' '+ui+'OptionMenu;',
        'scrollLayout '+ui+'ScrollLayout;',
        f'gridLayout -cw {value.cell_width} -ch {value.cell_height} -nc {value.columns} -nr {value.rows} '+ui+'GridLayout;',
        'formLayout -e',
        '\t-af '+ui+'OptionMenu "top" 0',
        '\t-ac '+ui+'ScrollLayout "top" 0 '+ui+'OptionMenu',
        '\t-af '+ui+'ScrollLayout "bottom" 0',
        '\t-af '+ui+'ScrollLayout "left" 0',
        '\t-af '+ui+'ScrollLayout "right" 0 '+ui+'FormLayout;']
    for button in value.buttons:
        child=str(button.child)
        lines.extend(['$cmd='+quote(button.command)+';',
            'setParent '+ui+'GridLayout;',
            'columnLayout '+ui+'ColumnLayout'+child+';',
            'rowColumnLayout -ann '+str(int(button.animation))+' -nc 2 -cw 1 100 -cw 2 15 '+ui+'RowColumnLayout'+child+';',
            'iconTextButton -w 100 -h 75 -i ($asIconLocation+'+quote(name+'_'+str(button.image_number)+'.png')+') -c $cmd '+ui+'IconTextButton'+child+';',
            'floatSlider -ann '+quote(button.slider_annotation)+' -m '+str(int(button.slider_managed))+
            ' -min '+str(button.slider_minimum)+' -max '+str(button.slider_maximum)+
            ' -w 10 -h 75 -hr 0 '+ui+'FloatSlider'+child+';',
            'text -h 15 -al "center" -fn "smallBoldLabelFont" -l '+quote(button.label)+
            (' -bgc 1 0 0' if button.red_label else '')+' '+ui+'Text'+child+';',
            'gridLayout -e -pos '+ui+'ColumnLayout'+child+' '+child+' '+ui+'GridLayout;',
            'asPoserupdateGridBlock '+ui+' '+child+';',''])
    lines.extend(['asPopulateNameSpaceMenu '+ui+';','asCharChange '+ui+';',
        'evalDeferred "showWindow;";','}',ui+';',''])
    return '\n'.join(lines)
