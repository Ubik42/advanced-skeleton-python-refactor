"""Selection-dependent FitMode callbacks from MEL 6528–6586."""
from dataclasses import dataclass

from .fit_orientation import select_fit_orientation_child


@dataclass(frozen=True, slots=True)
class SourceFitModeSelection:
    selected: tuple[str, ...]
    parent_axes: tuple[str, ...]
    aiming_children: tuple[str, ...]
    transform_watch: str | None
    twist_watch: str | None


def source_fit_mode_selection(snapshot, selected):
    nodes = {node.path: node for node in snapshot.hierarchy.joints}
    selected = tuple(path for path in selected if path in nodes)
    axes = []
    children = []
    for joint in selected:
        parent = nodes[joint].dag_parent
        if parent in nodes:
            axes.append(parent)
            children.append(joint)
    for joint in selected:
        child = select_fit_orientation_child(snapshot, joint)
        if child is not None:
            children.append(child)
    metadata = {row.joint: row for row in snapshot.metadata}
    # Native installs one twist watch on selected[0] when ANY selected joint
    # has twistJoints, even if the first joint does not have that attribute.
    from .fit_metadata import FitJointField
    twist = bool(selected) and any(FitJointField.TWIST_JOINTS in metadata[joint].present_fields
                                 for joint in selected if joint in metadata)
    return SourceFitModeSelection(selected, tuple(axes), tuple(children),
                                  selected[0] if selected and children else None,
                                  selected[0] if twist else None)


def source_fit_mode_aim_parent(snapshot, child):
    """Ignore non-preferred children and duplicate Cup branches as MEL does."""
    nodes = {node.path: node for node in snapshot.hierarchy.joints}
    joint = nodes.get(child)
    if joint is None or joint.dag_parent not in nodes:
        return None
    parent = nodes[joint.dag_parent]
    name = parent.short_name.rsplit(':', 1)[-1]
    import re
    if re.match(r'^Cup[0-9]', name) or name == 'Cup_NonSymmetry':
        return None
    return parent.path if select_fit_orientation_child(snapshot, parent.path) == child else None
