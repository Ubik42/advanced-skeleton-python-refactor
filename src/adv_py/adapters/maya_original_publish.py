"""Native ADV Publish: binary files, scripts, backups, Undo and selection.

Built-in ADV template behavior calls the Python ports. User-authored scripts
remain explicit extension callbacks. No ADV MEL procedure is evaluated.
"""
from contextlib import contextmanager

from adv_py.core.original_publish import (
    PUBLISH_OPTION, BODY_ONLY_SCRIPT, LO_ONLY_SCRIPT, original_publish_entries,
    replace_original_publish_entry, plan_original_publish,
)
from .maya_fit import MayaFitJointHost


class MayaOriginalPublishHost(MayaFitJointHost):
    def __init__(self, *, namespace=None, script_runner=None):
        super().__init__(namespace=namespace)
        self.script_runner = script_runner

    @property
    def _publish_raw(self):
        return getattr(self._cmds, 'raw', self._cmds)

    def original_publish_options(self):
        c = self._publish_raw
        values = c.optionVar(query=PUBLISH_OPTION) if c.optionVar(exists=PUBLISH_OPTION) else ()
        return (values,) if isinstance(values, str) else tuple(values or ())

    def set_original_display_layers_to_reference(self):
        self._require_transaction()
        c = self._publish_raw
        self._transaction_changed = True
        layers = []
        for layer in c.listConnections('layerManager.displayLayerId') or []:
            if layer == 'defaultLayer':
                continue
            c.setAttr(layer + '.displayType', 2)
            layers.append(layer)
        return tuple(layers)

    def set_original_publish_option(self, name, script):
        c = self._publish_raw
        values = self.original_publish_options()
        if not name:
            raise ValueError('No Name given')
        exists = any(entry.name == name for entry in original_publish_entries(values))
        if exists and c.confirmDialog(title='Confirm', message='Replace "' + name + '" ?',
                button=['Ok', 'Cancel'], defaultButton='Ok') != 'Ok':
            return False
        updated = replace_original_publish_entry(values, name, script)
        if exists:
            c.optionVar(clearArray=PUBLISH_OPTION)
            for value in updated:
                c.optionVar(stringValueAppend=(PUBLISH_OPTION, value))
        else:
            c.optionVar(stringValueAppend=(PUBLISH_OPTION, updated[-1]))
        return True

    def remove_original_publish_option(self, index):
        values = self.original_publish_options()
        if type(index) is not int or not 0 <= index < len(values):
            raise ValueError('Publish 配置索引不存在')
        self._publish_raw.optionVar(removeFromArray=(PUBLISH_OPTION, index))

    def capture_original_publish(self):
        c = self._cmds
        raw = self._publish_raw
        plan = plan_original_publish(raw.file(query=True, sceneName=True),
                                     original_publish_entries(self.original_publish_options()))
        controls = list(c.sets('ControlSet', query=True) or []) if c.objExists('ControlSet') else []
        if c.objExists('FaceControlSet'):
            controls.extend(c.sets('FaceControlSet', query=True) or [])
        animated = []
        for control in controls:
            for attribute in c.listAttr(control, keyable=True) or []:
                if c.listConnections(control + '.' + attribute, source=True,
                                     destination=False, type='animCurve'):
                    # Source deliberately repeats a control once per channel.
                    animated.append(control)
        return dict(plan=plan, animated=tuple(animated),
                    selection=tuple(raw.ls(selection=True) or []),
                    undo=bool(raw.undoInfo(query=True, state=True)))

    def confirm_original_publish_animation(self, source):
        if not source['animated']:
            return True
        self._cmds.select(source['animated'], replace=True)
        c = self._publish_raw
        c.refresh()
        return c.confirmDialog(title='Confirm', message=(
            'Animation found:\n\nThe selected controllers have animation.\n'
            'Do you wish to proceed to publish rig with the animation'),
            button=['Yes', 'No'], defaultButton='No', cancelButton='No',
            dismissString='No') == 'Yes'

    def _publish_backup(self, destination, scene):
        c = self._publish_raw
        if c.file(destination, query=True, exists=True):
            from maya import mel
            c.file(rename=destination)
            try:
                mel.eval('incrementalSaveScene;')
            finally:
                c.file(rename=scene)

    @contextmanager
    def _publish_script_namespace(self):
        c = self._publish_raw
        previous = c.namespaceInfo(currentNamespace=True, absoluteName=True)
        try:
            c.namespace(setNamespace=':' + (self.namespace or ''))
            yield
        finally:
            c.namespace(setNamespace=previous)

    def _publish_builtin_script(self, script):
        if script == BODY_ONLY_SCRIPT:
            from .maya_face_original_build import MayaOriginalFaceBuildHost
            face = object.__new__(MayaOriginalFaceBuildHost)
            face.__dict__ = dict(self.__dict__)
            face._transaction_active = True
            face._transaction_changed = False
            plan = face.plan_delete_face_advanced()
            if plan is not None:
                face.delete_face_advanced(plan)
            self._cmds.delete('FaceGroup')
            return True
        if script == LO_ONLY_SCRIPT:
            from maya import mel
            # These are Maya display-layer/delete utilities, with no ADV code.
            layer = self.scene_address('Hi')
            mel.eval('layerEditorSelectObjects "' + layer + '"; doDelete;')
            self._cmds.delete('Hi')
            return True
        return False

    def _publish_run_script(self, script):
        if not script:
            return None
        try:
            with self._publish_script_namespace():
                if not self._publish_builtin_script(script):
                    if self.script_runner is None:
                        raise RuntimeError('自定义 Publish 脚本需要显式宿主回调')
                    self.script_runner(script)
        except Exception as error:
            # MEL catch(evalEcho(...)) continues to export its partially edited
            # scene. Keep that behavior; the chunk is still undone afterwards.
            self._publish_raw.warning('Publish script: ' + str(error))
            return str(error)
        return None

    def _publish_binary(self, destination):
        self._publish_raw.file(destination, force=True, options='v=0',
                               type='mayaBinary', exportAll=True)

    def _publish_variant(self, script, destination, name, *, custom):
        c = self._publish_raw
        scripted = custom or bool(script)
        error = None
        if scripted:
            c.undoInfo(openChunk=True, chunkName='PublishScript for: "' + name + '"')
            try:
                # Native scripts may mutate through external host callbacks;
                # their completed chunk is always reverted after export.
                error = self._publish_run_script(script)
            finally:
                c.undoInfo(closeChunk=True)
            # Native source disables recording for file export without flush.
            c.undoInfo(stateWithoutFlush=False)
        try:
            self._publish_binary(destination)
        finally:
            if scripted:
                c.undoInfo(stateWithoutFlush=True)
                c.undo()
        return dict(destination=destination, script_error=error, restored=scripted)

    def publish_original_scene(self, source):
        c = self._publish_raw
        plan = source['plan']
        self._publish_backup(plan.destination, plan.scene)
        if not source['undo']:
            c.undoInfo(stateWithoutFlush=True)
        results = []
        try:
            for entry, destination in plan.variants:
                self._publish_backup(destination, plan.scene)
                results.append(self._publish_variant(entry.script, destination, entry.name, custom=True))
            results.append(self._publish_variant(plan.default_script, plan.destination, 'Default', custom=False))
        finally:
            if not source['undo']:
                c.undoInfo(stateWithoutFlush=False)
            c.select(source['selection'], replace=True) if source['selection'] else c.select(clear=True)
        return tuple(results)
