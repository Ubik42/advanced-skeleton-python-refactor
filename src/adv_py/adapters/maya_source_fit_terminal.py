"""Read native NonSymmetryFitJoints.previousParent without changing its DAG."""


def capture_non_terminal_fits(host,hierarchy):
    staged=getattr(host,'_source_fit_terminal_state',None)
    if staged is not None:
        return staged.resolve(hierarchy)
    c=host._cmds
    if not c.objExists('NonSymmetryFitJoints'):return ()
    known={node.path for node in hierarchy.joints}
    result=set()
    for joint in c.listRelatives('NonSymmetryFitJoints',children=True,type='joint',fullPath=True) or []:
        plug=joint+'.previousParent'
        if not c.objExists(plug):continue
        reference=c.getAttr(plug)
        if not isinstance(reference,str) or not reference:continue
        result.update(path for path in c.ls(reference,long=True,type='joint') or [] if path in known)
    return tuple(sorted(result))


def capture_state(host,container):
    from adv_py.core.source_fit_terminal import source_fit_terminal_state
    hierarchy=host.capture_fit_hierarchy(container)
    return source_fit_terminal_state(hierarchy,capture_non_terminal_fits(host,hierarchy))


def install_staged_state(host,state,container='FitSkeleton'):
    from adv_py.core.source_fit_terminal import SourceFitTerminalState
    from adv_py.core.fit_settings import FitSkeletonValidationError
    host._require_transaction()
    if not isinstance(state,SourceFitTerminalState):
        raise FitSkeletonValidationError('暂存非对称末端来源类型无效')
    state.resolve(host.capture_fit_hierarchy(container))
    host._source_fit_terminal_state=state
