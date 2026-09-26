"""Maya selection and preference actions from the original Skinning panel."""
from __future__ import annotations


SMOOTH_BIND_OPTIONS = (
    ("multipleBindPosesOpt", 1),
    ("bindMethod", 1),
    ("bindTo", 2),
    ("skinMethod", 1),
    ("removeUnusedInfluences", 0),
    ("colorizeSkeleton", 0),
    ("maxInfl", 3.0),
    ("normalizeWeights", 2),
    ("obeyMaxInfl", 0),
)


def select_deform_joints(namespace: str, registered_joints: tuple[str, ...],
                         *, cmds=None) -> int:
    """Append deform joints to the current Maya selection, preserving meshes."""
    if cmds is None:
        from maya import cmds
    selected = tuple(cmds.ls(selection=True, long=True, flatten=True) or ())
    set_name = f"{namespace}:DeformSet" if namespace else "DeformSet"
    if cmds.objExists(set_name):
        joints = tuple(cmds.sets(set_name, query=True) or ())
    else:
        joints = registered_joints
    joints = tuple(path for path in joints if path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                   not in {"Eye_R", "Eye_L", "Jaw_M"})
    if not joints:
        raise ValueError("当前角色没有可选择的变形关节")
    # Preflight all paths before changing the selection.
    missing = tuple(path for path in joints if not cmds.objExists(path))
    if missing:
        raise ValueError(f"变形关节不存在：{missing[0]}")
    cmds.select(joints, replace=True)
    if selected:
        cmds.select(selected, add=True)
    return len(joints)


def set_smooth_bind_options(*, cmds=None, mel=None, show_dialog: bool = True) -> None:
    """Apply the 6.925 optionVars and open Maya's native bind dialog."""
    if cmds is None:
        from maya import cmds
    for name, value in SMOOTH_BIND_OPTIONS:
        if isinstance(value, float):
            cmds.optionVar(floatValue=(name, value))
        else:
            cmds.optionVar(intValue=(name, value))
    if show_dialog:
        if mel is None:
            from maya import mel
        mel.eval("SmoothBindSkinOptions")
