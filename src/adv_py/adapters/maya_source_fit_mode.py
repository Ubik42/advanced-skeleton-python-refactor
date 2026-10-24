"""Python FitMode: scene-bound jobs, native selected-joint aim callbacks."""
from contextlib import contextmanager
from dataclasses import dataclass, field

from adv_py.core.source_fit_mode import source_fit_mode_selection


# Maya keeps Python callbacks alive in scriptJob. Retain one session per
# character and always inspect the real job ID before treating it as active.
_SESSIONS = {}


@dataclass
class _FitModeSession:
    host: object
    selection_job: int = 0
    scale_job: int = 0
    selected_jobs: list[int] = field(default_factory=list)
    temporary_axes: list[str] = field(default_factory=list)
    updating: bool = False
    hud_created: bool = False

    @property
    def c(self):
        return getattr(self.host._cmds, 'raw', self.host._cmds)

    @property
    def hud(self):
        namespace = getattr(self.host, 'namespace', None) or ''
        return 'HUDFitMode' + ('_'+namespace.replace(':', '_') if namespace else '')

    def alive(self):
        return bool(self.selection_job and self.c.scriptJob(exists=self.selection_job))

    def _kill(self, job):
        if job and self.c.scriptJob(exists=job):
            self.c.scriptJob(kill=job)

    def clear_selection_jobs(self, *, restore_axes=True):
        for job in self.selected_jobs:
            self._kill(job)
        self.selected_jobs.clear()
        if restore_axes:
            for node in self.temporary_axes:
                if self.host._cmds.objExists(node):
                    self.host._cmds.setAttr(node+'.displayLocalAxis', False)
        self.temporary_axes.clear()

    @contextmanager
    def edit(self, label):
        if self.updating:
            yield False
            return
        self.updating = True
        try:
            with self.host.transaction(label):
                yield True
        finally:
            self.updating = False

    def selection_changed(self):
        if self.updating:
            return
        self.clear_selection_jobs()
        if not self.alive() or not self.host._cmds.objExists('FitSkeleton'):
            return
        host = self.host
        c = host._cmds
        snapshot = host.capture_fit_orientation('FitSkeleton')
        selected = tuple(c.ls(selection=True, long=True, type='joint') or ())
        plan = source_fit_mode_selection(snapshot, selected)
        for parent in plan.parent_axes:
            if not c.getAttr(parent+'.displayLocalAxis'):
                self.temporary_axes.append(parent)
            c.setAttr(parent+'.displayLocalAxis', True)
        if plan.transform_watch:
            for attribute in ('translate', 'rotate'):
                self.selected_jobs.append(self.c.scriptJob(compressUndo=True,
                    killWithScene=True, attributeChange=[
                        host.scene_address(plan.transform_watch+'.'+attribute),
                        lambda children=plan.aiming_children: self.update_joints(children)]))
        if plan.twist_watch:
            self.selected_jobs.append(self.c.scriptJob(compressUndo=True,
                killWithScene=True, attributeChange=[
                    host.scene_address(plan.twist_watch+'.twistJoints'), self.update_geometry]))

    def update_joints(self, children):
        host = self.host
        from .maya_source_fit_orientation import update_orientations
        with self.edit('FitMode 更新关节朝向') as execute:
            if not execute:
                return
            with host.fit_manual_update_channels('FitSkeleton'):
                update_orientations(host, children)

    def scale_changed(self):
        with self.edit('FitMode 更新 Fit 缩放') as execute:
            if execute:
                self.host.bake_fit_container_scale('FitSkeleton')

    def update_geometry(self):
        if self.updating:
            return
        from .maya_fit_geometry import MayaFitGeometryHost
        from adv_py.application.fit_geometry import UpdateFitGeometry
        c = self.host._cmds
        if c.objExists('FitSkeleton.visGeo') and c.getAttr('FitSkeleton.visGeo'):
            index = int(c.getAttr('FitSkeleton.visGeoType')) if c.objExists('FitSkeleton.visGeoType') else 1
            self.updating = True
            try:
                # Geometry owns its import/undo transaction. The session
                # guard prevents orientation writes recursively firing jobs.
                geometry = MayaFitGeometryHost(namespace=self.host.namespace)
                UpdateFitGeometry(geometry).execute(visible=True,
                    geometry_type=('cylinders', 'boxes', 'spheres', 'bones')[index])
            finally:
                self.updating = False

    def stop(self, *, restore_axes=False):
        self._kill(self.selection_job)
        self._kill(self.scale_job)
        self.selection_job = self.scale_job = 0
        self.clear_selection_jobs(restore_axes=restore_axes)
        if self.hud_created and self.c.headsUpDisplay(self.hud, exists=True):
            self.c.headsUpDisplay(self.hud, remove=True)
        self.hud_created = False

    def start(self):
        host = self.host
        if self.c.headsUpDisplay(self.hud, exists=True):
            raise ValueError('已有 FitMode 显示，请先关闭当前 FitMode')
        selected = tuple(host._cmds.ls(selection=True, long=True) or ())
        self.updating = True
        try:
            host._cmds.select(clear=True)
            with host.transaction('开启 FitMode'):
                host.manual_update_fit()
            self.selection_job = self.c.scriptJob(compressUndo=True, killWithScene=True,
                event=['SelectionChanged', self.selection_changed])
            if host._cmds.objExists('FitSkeleton'):
                self.scale_job = self.c.scriptJob(compressUndo=True, killWithScene=True,
                    attributeChange=[host.scene_address('FitSkeleton.scale'), self.scale_changed])
            self.c.headsUpDisplay(self.hud, section=2, block=0, blockSize='medium',
                                label='FitMode', labelFontSize='large')
            self.hud_created = True
        except Exception:
            self.stop(restore_axes=True)
            raise
        finally:
            self.updating = False
            host._cmds.select(selected, replace=True) if selected else host._cmds.select(clear=True)


def toggle(host):
    key = getattr(host, 'namespace', None) or ''
    previous = _SESSIONS.get(key)
    if previous is not None and previous.alive():
        previous.stop(restore_axes=True)
        del _SESSIONS[key]
        return False
    if previous is not None:
        previous.stop(restore_axes=True)
    session = _FitModeSession(host)
    _SESSIONS[key] = session
    try:
        session.start()
    except Exception:
        _SESSIONS.pop(key, None)
        raise
    return True


def stop(host):
    key = getattr(host, 'namespace', None) or ''
    session = _SESSIONS.pop(key, None)
    if session is not None:
        # asOffFitMode removes jobs/HUD; it does not hide the currently
        # displayed parent axes. Toggle-off does restore those temporary axes.
        session.stop(restore_axes=False)


@contextmanager
def suspend_for_geometry(host, *, resume):
    """asFitGeometry stops FitMode before imports and resumes visible builds."""
    key = getattr(host, 'namespace', None) or ''
    session = _SESSIONS.get(key)
    active = session is not None and session.alive()
    if active:
        stop(session.host)
    yield
    # An exception deliberately leaves jobs stopped, just like the source
    # procedure that never reaches its final asFitMode invocation.
    if active and resume:
        toggle(session.host)
