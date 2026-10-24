"""Plan ADV geoAttach on the existing FK Offset without changing its DAG path."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_metadata import FitJointMetadata
from .source_fit_identity import source_fit_build_name, source_fit_control_matches, source_fit_side_sign


@dataclass(frozen=True, slots=True)
class BodyFitGeoAttachSpec:
    source_body: str
    fk_control: str
    fk_offset: str
    offset_parent: str
    mesh: str
    mode: str
    side: str
    surface: str
    constraint: str
    static_matrix: str
    attached_matrix: str
    blend_matrix: str
    weight_node: str
    output_matrix: str
    source_native: bool = False
    fit_joint: str | None = None
    source_sign: int = 1

    @property
    def node_names(self) -> tuple[str, ...]:
        if self.source_native:
            return (self.surface, self.constraint, self.static_matrix,
                    self.attached_matrix, self.blend_matrix, self.weight_node,
                    self.output_matrix, self.attached_matrix + "_parentConstraint1")
        return (self.surface, self.constraint, self.static_matrix,
                self.attached_matrix, self.blend_matrix,
                self.weight_node, self.output_matrix)


@dataclass(frozen=True, slots=True)
class BodyFitGeoAttachState:
    mesh_shape: str
    source_position: tuple[float, float, float]
    offset_world: tuple[float, ...]
    parent_world: tuple[float, ...]
    opm_source: str | None
    opm_value: tuple[float, ...]
    inherits_transform: bool = True


def plan_body_fit_geo_attach(
    metadata: tuple[FitJointMetadata, ...], controls: tuple,
    body_joints: tuple, *, instances: tuple = (), source_native: bool = False,
) -> tuple[BodyFitGeoAttachSpec, ...]:
    bodies = {joint.name.rsplit(":", 1)[-1]: joint.path
              for joint in body_joints}
    if len(bodies) != len(body_joints):
        raise ValueError("Geo Attach Body 关节短名重复")
    result: list[BodyFitGeoAttachSpec] = []
    used: set[str] = set()
    for item in metadata:
        if item.geo_attach is None:
            continue
        name = item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        if instances:
            name = source_fit_build_name(name)
        matches = tuple(control for control in controls
                        if source_fit_control_matches(item, control, instances))
        for control in matches:
            side = control.side.value
            source_body = bodies.get(name + "_" + side)
            if source_body is None:
                raise ValueError("Geo Attach 来源 Body 关节缺失："
                                 + name + "_" + side)
            if not any(path.startswith(source_body + "|")
                       for path in bodies.values()):
                continue  # Original ADV skips terminal Fit joints.
            if control.control_path in used:
                raise ValueError("Geo Attach 来源 FK 控制重复："
                                 + control.control_path)
            used.add(control.control_path)
            if not control.control_path.startswith(control.offset_path + "|"):
                raise ValueError("Geo Attach FK 控制层路径无效")
            parent = control.offset_path.rsplit("|", 1)[0]
            if not parent:
                raise ValueError("Geo Attach FK Offset 缺少父层")
            leaf = control.control_path.rsplit("|", 1)[-1]
            namespace = leaf.rsplit(":", 1)[0] + ":" if ":" in leaf else ""
            stem = namespace + "AdvPy_GeoAttach" + name + "_" + side
            result.append(BodyFitGeoAttachSpec(
                source_body, control.control_path, control.offset_path,
                parent, item.geo_attach, item.geo_attach_mode, side,
                stem + "Surface", stem + "POPC", stem + "StaticMM",
                stem + "AttachedMM", stem + "BM", stem + "Weight",
                stem + "OutputMM", source_native, name if source_native else None,
                source_fit_side_sign(name + "_" + side, instances)))
        if not source_native and not matches and any(name + "_" + side in bodies
                               for side in ("M", "R", "L")):
            raise ValueError("Geo Attach 来源缺少 FK 控制：" + name)
    names = tuple(name for spec in result for name in spec.node_names)
    if len(names) != len(set(names)):
        raise ValueError("Geo Attach 生成节点名称重复")
    return tuple(result)
