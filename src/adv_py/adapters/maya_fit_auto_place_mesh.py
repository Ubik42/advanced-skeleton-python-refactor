"""Source component casting, inversion and leap to adjacent polygon shells."""
from .maya_fit_auto_place_guides import stock_wrap


def cast(components,destination):
    # asobjSetCast takes the source object from the first entry, then performs
    # one substitution in every entry. Do not silently remap components from
    # additional objects: the source leaves those strings unchanged.
    components=tuple(components)
    if not components:return []
    source=components[0].split('.',1)[0]
    return [component.replace(source,destination,1) for component in components]


def faces(c,contained=False):
    selected=c.ls(selection=True) or []
    result=c.polyListComponentConversion(selected,fromVertex=True,fromEdge=True,
        fromUV=True,fromVertexFace=True,toFace=True,internal=contained) or []
    # PolySelectConvert, called by the two stock conversion commands, changes
    # the component mask before replacing the selection. Retain that order:
    # Maya's active component buffers also govern subsequent topology growth.
    if result:
        raw=getattr(c,'raw',c)
        object_mode=raw.selectMode(query=True,object=True)
        if raw.selectPref(query=True,selectTypeChangeAffectsActive=True):
            flags={'objectComponent':True} if object_mode else {}
            raw.selectType(polymeshFace=True,**flags)
        if object_mode:raw.hilite()
        c.select(result,replace=True)
    return c.ls(selection=True) or []


def invert(c):
    selected=c.ls(selection=True) or []
    if not selected:return
    objects=c.ls(selection=True,objectsOnly=True) or []
    first=selected[0]
    kind=next((kind for kind in ('vtx','f','e') if '.'+kind in first),None)
    if kind:
        # Preserve the explicit source range, including its upper limit.
        # Maya clips it to existing components; evaluating the whole mesh and
        # synthesizing a different range changes the original selection rule.
        c.select(objects[0]+'.'+kind+'[0:999999]',replace=True)
        c.select(selected,deselect=True)
    else:
        # This is Maya's stock command, not an ADV procedure. UV/object
        # inversion follows the same fallback as asInvertSelection.
        from maya import mel
        from contextlib import nullcontext
        with c._creation_namespace() if hasattr(c,'_creation_namespace') else nullcontext():
            mel.eval('InvertSelection;')


def grow_past_shell(host):
    c=host._cmds
    selected=c.ls(selection=True) or []
    objects=c.ls(selection=True,objectsOnly=True) or []
    node=objects[0]
    if c.nodeType(node)=='mesh':node=c.listRelatives(node,parent=True)[0]
    a=c.duplicate(node,name='tempPolyGrowPastShell1')[0]
    b=c.duplicate(node,name='tempPolyGrowPastShell2')[0]
    additional=[];wrap=None
    try:
        c.select(cast(selected,a),replace=True);faces(c);c.delete(c.ls(selection=True))
        c.select(cast(selected,b),replace=True);faces(c);invert(c);c.delete(c.ls(selection=True))
        wrap=stock_wrap(host,a,b,'{ "1","0","0.001", "2", "1", "0", "1", "0" }')
        wrap=c.rename(wrap,'tempPolyGrowPastShellWrap')
        minimum=c.getAttr(a+'.boundingBoxMin')[0];maximum=c.getAttr(a+'.boundingBoxMax')[0]
        width=maximum[0]-minimum[0]
        c.move(-width*2.,0,0,b,relative=True);c.setAttr(wrap+'.maxDistance',width)
        for _ in range(10):
            c.setAttr(wrap+'.maxDistance',c.getAttr(wrap+'.maxDistance')/10.)
            if minimum[0]<=c.getAttr(a+'.boundingBoxMinX'):
                for _ in range(100):
                    c.setAttr(wrap+'.maxDistance',c.getAttr(wrap+'.maxDistance')*1.05)
                    if minimum[0]>c.getAttr(a+'.boundingBoxMinX'):
                        c.select(a,replace=True)
                        c.polySelectConstraint(mode=3,type=1,d=3,db=(0,999),
                            da=(1,0,0),dp=(999+minimum[0],0,0))
                        chosen=c.ls(selection=True) or [];c.polySelectConstraint(mode=0)
                        c.select(chosen,replace=True);invert(c)
                        additional=cast(c.ls(selection=True) or [],node);break
                break
    finally:
        c.delete([node for node in (a,b,wrap) if node and c.objExists(node)])
        c.select(selected,replace=True)
    if additional:c.select(additional,add=True)
    return bool(additional)
