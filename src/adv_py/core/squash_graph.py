"""Declarative dependency graph from ADV's Squash deform setup."""
from __future__ import annotations

from dataclasses import dataclass

from .squash_controller import SquashPlan, VOLUME_EXPONENTS


@dataclass(frozen=True, slots=True)
class GraphNode:
    name: str
    type: str


@dataclass(frozen=True, slots=True)
class GraphValue:
    plug: str
    value: float | int


@dataclass(frozen=True, slots=True)
class GraphLink:
    source: str
    target: str


@dataclass(frozen=True, slots=True)
class SquashGraph:
    nodes: tuple[GraphNode, ...]
    values: tuple[GraphValue, ...]
    links: tuple[GraphLink, ...]


def plan_squash_graph(plan: SquashPlan) -> SquashGraph:
    """Return DG work after the lattice, controls, joints and IK curve exist.

    Plugs are role-relative names. The Maya adapter resolves the namespace,
    parents the DAG nodes and supplies measured rest arc length and joint step.
    """
    stem, side = plan.name, plan.side
    control = plan.control
    name = lambda token: stem + token + side
    nodes = [GraphNode(name(token), kind) for token, kind in (
        ("BendMPDT", "multiplyDivide"),
        ("BendMPDR", "multiplyDivide"),
        ("IKCurveInfo", "curveInfo"),
        ("IKCurveInfoNormalize", "multiplyDivide"),
        ("IKCurveInfoMainScale", "multiplyDivide"),
        ("IKCurveInfoBaseScale", "multiplyDivide"),
        ("IKScale", "multiplyDivide"),
        ("IKStretch", "multiplyDivide"),
        ("LimitsClamp", "clamp"),
        ("SquashCondition", "condition"),
        ("StretchCondition", "condition"),
        ("squashVolume1Over", "multiplyDivide"),
        ("TopVolumeUC", "unitConversion"),
    )]
    values = [GraphValue(name(token) + ".operation", 2)
              for token in ("IKCurveInfoNormalize", "IKCurveInfoMainScale",
                            "IKCurveInfoBaseScale", "IKScale",
                            "squashVolume1Over")]
    values.extend((
        GraphValue(name("StretchCondition") + ".colorIfTrueR", 1),
        GraphValue(name("StretchCondition") + ".colorIfFalseR", 999),
        GraphValue(name("SquashCondition") + ".colorIfTrueR", 1),
        GraphValue(name("SquashCondition") + ".colorIfFalseR", 0),
        GraphValue(name("squashVolume1Over") + ".input1X", 1),
        GraphValue(name("TopVolumeUC") + ".conversionFactor", .1),
    ))
    links = []

    def connect(source: str, target: str) -> None:
        links.append(GraphLink(source, target))

    for axis in "YZ":
        connect(control + ".translate" + axis,
                name("BendMPDT") + ".input1" + axis)
        connect(control + ".bend", name("BendMPDT") + ".input2" + axis)
        connect(name("BendMPDT") + ".output" + axis,
                name("IKClusterHandle4Offset") + ".translate" + axis)
    connect(control + ".translateX",
            name("IKClusterHandle4Offset") + ".translateX")
    for axis in "XYZ":
        connect(control + ".rotate" + axis,
                name("BendMPDR") + ".input1" + axis)
        connect(control + ".bend", name("BendMPDR") + ".input2" + axis)
        connect(name("BendMPDR") + ".output" + axis,
                name("IKClusterHandle4Offset") + ".rotate" + axis)
    if side == "_L":
        nodes.append(GraphNode(name("IKTwistReverse"), "multiplyDivide"))
        values.append(GraphValue(name("IKTwistReverse") + ".input2X", -1))
        connect(control + ".rotateX", name("IKTwistReverse") + ".input1X")
        connect(name("IKTwistReverse") + ".outputX",
                name("IKHandle") + ".twist")
    else:
        connect(name("BendMPDR") + ".outputX",
                name("IKHandle") + ".twist")

    connect(name("IKCurveShape") + ".worldSpace[0]",
            name("IKCurveInfo") + ".inputCurve")
    connect(name("IKCurveInfo") + ".arcLength",
            name("IKCurveInfoNormalize") + ".input1X")
    connect(name("IKCurveInfoNormalize") + ".outputX",
            name("IKCurveInfoMainScale") + ".input1X")
    connect("MainScaleMultiplyDivide.outputY",
            name("IKCurveInfoMainScale") + ".input2X")
    connect(name("IKCurveInfoMainScale") + ".outputX",
            name("IKCurveInfoBaseScale") + ".input1X")
    connect(name("Base") + ".scaleX",
            name("IKCurveInfoBaseScale") + ".input2X")
    connect(name("IKCurveInfoBaseScale") + ".outputX",
            name("IKScale") + ".input1X")
    connect(plan.parent_joint + ".scaleX", name("IKScale") + ".input2X")
    connect(name("IKScale") + ".outputX", name("LimitsClamp") + ".inputR")
    connect(control + ".stretch", name("StretchCondition") + ".firstTerm")
    connect(control + ".squash", name("SquashCondition") + ".firstTerm")
    connect(name("StretchCondition") + ".outColorR",
            name("LimitsClamp") + ".maxR")
    connect(name("SquashCondition") + ".outColorR",
            name("LimitsClamp") + ".minR")
    connect(name("LimitsClamp") + ".outputR",
            name("IKStretch") + ".input2X")
    connect(name("LimitsClamp") + ".outputR",
            name("squashVolume1Over") + ".input2X")
    for index in range(1, 11):
        connect(name("IKStretch") + ".outputX",
                stem + "IKX%d%s.translateX" % (index, side))
    connect(control + ".volume", name("TopVolumeUC") + ".input")
    for index, exponent in enumerate(VOLUME_EXPONENTS, 1):
        power = name("squashVolumePow%d" % index)
        blend = name("BlendTwo%d" % index)
        nodes.extend((GraphNode(power, "multiplyDivide"),
                      GraphNode(blend, "blendTwoAttr")))
        values.extend((GraphValue(power + ".operation", 3),
                       GraphValue(power + ".input2X", exponent),
                       GraphValue(blend + ".input[0]", 1)))
        connect(name("squashVolume1Over") + ".outputX",
                power + ".input1X")
        connect(power + ".outputX", blend + ".input[1]")
        connect(name("TopVolumeUC") + ".output",
                blend + ".attributesBlender")
        for axis in "YZ":
            connect(blend + ".output",
                    stem + "IKX%d%s.scale%s" % (index, side, axis))
    connect(control + ".latticeVis", name("FfdLattice") + ".visibility")
    connect(control + ".curveVis", name("IKCurve") + ".visibility")
    connect(control + ".outsideLattice",
            name("Ffd") + ".outsideLattice")
    return SquashGraph(tuple(nodes), tuple(values), tuple(links))
