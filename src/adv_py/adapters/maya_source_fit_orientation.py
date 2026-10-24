"""Native per-child Fit orientation dispatch and live-frame sampling."""
from adv_py.application.fit_orientation_auto import OrientFitJoints
from adv_py.core.fit_ik import fit_joint_ik_info
from adv_py.core.fit_orientation import FitOrientationRequest, select_fit_orientation_child
from adv_py.core.source_fit_mode import source_fit_mode_aim_parent
from contextlib import nullcontext


def update_orientations(host, children, *, container='FitSkeleton', recursive=False):
    context=getattr(host,'source_fit_orientation_context',None)
    with context() if callable(context) else nullcontext():
        return _update_orientations(host,children,container=container,recursive=recursive)


def _update_orientations(host, children, *, container='FitSkeleton', recursive=False):
    host._require_transaction()
    children = tuple(children)
    if not children:
        return ()
    c = host._cmds
    snapshot = host.capture_fit_orientation(container)
    # asFitModeUpdateJoints switches world-match interactive edits to a
    # recursive update of the first supplied child, rather than merging roots.
    if snapshot.axis_configuration.world_match and not recursive:
        children = children[:1]
        recursive = True
    native_aim=getattr(host,'aim_source_fit_joint',None)
    editor = None if callable(native_aim) else OrientFitJoints(host)
    def axis(direction):return direction.value.replace('+','').upper()
    state=dict(primary=axis(snapshot.axis_configuration.primary),
               secondary=axis(snapshot.axis_configuration.secondary))
    applied=[]

    def aim(child, *, recursive_pass):
        paths = tuple(c.ls(child, long=True, allPaths=True) or ())
        if len(paths) != 1:
            return
        child = paths[0]
        current = host.capture_fit_orientation(container)
        parent = source_fit_mode_aim_parent(current, child)
        if parent is None:
            return
        info = fit_joint_ik_info(current.hierarchy, dict(current.labels), parent)
        if not recursive_pass:
            if info is not None and info.end == child:
                first = select_fit_orientation_child(current, info.start)
                if first is not None and first != child:
                    # Native end edits orient the RP/Spline start first so
                    # the middle reads its freshly evaluated world-up frame.
                    # This is a new MEL procedure call, not another iteration
                    # in the outer call. Its noFlip, world-forward and axis
                    # locals must not leak back into the edited end's pass.
                    applied.extend(update_orientations(host,(first,),
                        container=container,recursive=False))
        if callable(native_aim):
            # Read the evaluated frame after the recursive start operation.
            # The native implementation detaches before its center snap and
            # runs Maya's own aim before the original straight-plane nudge.
            current=host.capture_fit_orientation(container)
            native_aim(parent,child,current,info,state)
            applied.append(parent)
            return
        if info is not None:
            start_position = c.xform(info.start, query=True, worldSpace=True, translation=True)
            parent_position = c.xform(parent, query=True, worldSpace=True, translation=True)
            tolerance = .01*current.fit_scale
            if (-tolerance < start_position[0] < tolerance
                    and not -tolerance < parent_position[0] < tolerance):
                # Source detached the selected child and sibling branches
                # before snapping its parent. Maya pcp preserves those exact
                # child world positions without changing their DAG identity.
                host._transaction_changed = True
                c.move(0., parent_position[1], parent_position[2], parent,
                       absolute=True, worldSpace=True, preserveChildPosition=True)
        plan = editor.plan(FitOrientationRequest((parent,)), container)
        if plan.changes or plan.terminal_resets:
            editor.apply_plan_in_transaction(plan)
            applied.append(parent)

    for child in children:
        if recursive:
            descendants = tuple(c.listRelatives(child, allDescendents=True,
                                                type='joint', fullPath=True) or ())
            for item in (child, *reversed(descendants)):
                aim(item, recursive_pass=True)
        else:
            aim(child, recursive_pass=False)
    return tuple(applied)
