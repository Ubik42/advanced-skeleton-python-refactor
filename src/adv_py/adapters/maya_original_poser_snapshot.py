"""Original native Poser playblast / RenderView capture (MEL 27811–27908)."""
from pathlib import Path
import random
import shutil

from .maya_original_poser_store import icon_directory


def padded_frame(frame, padding=4):
    """asDoPadd counts the minus sign before prefixing its remaining zeros."""
    frame = int(frame)
    text = str(frame)
    return ('-' if frame < 0 else '') + '0' * (padding-len(text)) + str(abs(frame)) if len(text) < padding else text


def resize_image(raw, width, height, source, destination):
    """Use the original Maya file-node / convertSolidTx cache bypass."""
    source, destination = Path(source), Path(destination)
    unique = source.parent / ('unique' + str(random.uniform(0., 42.)).replace('.', '') + source.suffix)
    shutil.copyfile(source, unique)
    selected = raw.ls(selection=True) or ()
    node = None
    texture = 'asTempSolidTx32'
    if raw.objExists(texture):
        unique.unlink(missing_ok=True)
        raise ValueError('原版 Poser 临时纹理节点已存在：' + texture)
    try:
        node = raw.createNode('file')
        raw.setAttr(node + '.fileTextureName', unique.as_posix(), type='string')
        raw.convertSolidTx(sp=True, al=True, rx=width, ry=height,
            n=texture, fil='png', fin=destination.as_posix())
    finally:
        if node and raw.objExists(node):
            raw.delete(node)
        if raw.objExists(texture):
            raw.delete(texture)
        unique.unlink(missing_ok=True)
        raw.select(selected, replace=True) if selected else raw.select(clear=True)


def capture(host, ui_name, child, animation=False, update_icon=True, update_movie=True):
    host._require_transaction()
    raw = getattr(host._cmds, 'raw', host._cmds)
    directory = icon_directory(raw)
    directory.mkdir(parents=True, exist_ok=True)
    render_view = bool(raw.checkBox('asPoserRenderView', query=True, value=True))
    current = int(raw.currentTime(query=True))
    format_before = raw.getAttr('defaultRenderGlobals.imageFormat')
    huds = tuple(raw.headsUpDisplay(listHeadsUpDisplays=True) or ())
    visible = tuple(raw.headsUpDisplay(hud, query=True, visible=True) for hud in huds)
    file = directory / ('untitled_' + str(child))
    icon = file.with_suffix('.png')
    blast = Path(str(file) + '.' + padded_frame(current))
    large = file.with_suffix('.jpg')
    background = directory / 'untitled_background32.png'
    existing = raw.file(icon.as_posix(), query=True, exists=True)
    host._transaction_changed = True
    try:
        for hud in huds:
            raw.headsUpDisplay(hud, edit=True, visible=False)
        raw.setAttr('defaultRenderGlobals.imageFormat', 32)
        if render_view and update_icon:
            if raw.renderWindowEditor('renderView', query=True, nim=True) < 0:
                raise ValueError('No Image In RenderView')
            raw.renderWindowEditor('renderView', edit=True, writeImage=icon.as_posix())
            resize_image(raw, 100, 75, icon, icon)
            raw.setAttr('defaultRenderGlobals.imageFormat', 8)
            raw.renderWindowEditor('renderView', edit=True, writeImage=large.as_posix())
        if not render_view and update_icon:
            raw.playblast(width=100, height=75, compression='png', percent=100,
                startTime=current, endTime=current, filename=file.as_posix(), format='image',
                forceOverwrite=True, clearCache=False, viewer=False, showOrnaments=False)
            Path(str(blast) + '.png').replace(icon)
        raw.setAttr('defaultRenderGlobals.imageFormat', 8)
        if animation and update_movie:
            raw.playblast(percent=100, startTime=raw.playbackOptions(query=True, minTime=True),
                endTime=raw.playbackOptions(query=True, maxTime=True), filename=file.as_posix(),
                format='movie', forceOverwrite=True, clearCache=False, viewer=False, showOrnaments=False)
        elif update_icon:
            raw.playblast(percent=100, compression='png', startTime=current, endTime=current,
                filename=file.as_posix(), format='image', forceOverwrite=True,
                clearCache=False, viewer=False, showOrnaments=False)
            Path(str(blast) + '.jpg').replace(large)
        if not raw.file(background.as_posix(), query=True, exists=True):
            resize_image(raw, 32, 32, icon, background)
        if existing:
            raw.iconTextButton(ui_name + 'IconTextButton' + str(child), edit=True, image=icon.as_posix())
        return str(icon)
    finally:
        raw.setAttr('defaultRenderGlobals.imageFormat', format_before)
        for hud, state in zip(huds, visible):
            raw.headsUpDisplay(hud, edit=True, visible=state)
