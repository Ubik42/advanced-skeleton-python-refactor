"""Read installed ADV 6.925 icon curves locally without bundling its assets."""
from __future__ import annotations

from functools import lru_cache
from math import isfinite
import os
from pathlib import Path
import re

from adv_py.core.adv_icon_axis import icon_axis_offset, rotate_icon_point


_TRANSFORM = re.compile(r'createNode transform -n "([^"]+)";')
_SHAPE = re.compile(r'createNode nurbsCurve -n "([^"]+)" -p "([^"]+)";')
_OVERRIDE_ENABLED = re.compile(r'setAttr "\.ove" (yes|no);')
_OVERRIDE_COLOR = re.compile(r'setAttr "\.ovc" ([0-9]+);')
_LOCAL_SOURCE = Path.home() / ".adv_py" / "as_icons_path.txt"
_PROJECT_SOURCE = (Path(__file__).resolve().parents[3]
                   / "local" / "adv_6_925" / "asIcons.ma")


def _icon_source() -> Path | None:
    configured = os.environ.get("ADV_6925_ICONS_FILE", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise ValueError("原版控制器图标文件不存在：" + str(path))
        return path
    if _PROJECT_SOURCE.is_file():
        return _PROJECT_SOURCE
    if _LOCAL_SOURCE.is_file():
        configured = _LOCAL_SOURCE.read_text(encoding="utf-8").strip()
    if not configured:
        return None
    path = Path(configured).expanduser()
    if not path.is_file():
        raise ValueError("原版控制器图标文件不存在：" + str(path))
    return path


@lru_cache(maxsize=4)
def _templates(source: Path) -> dict[str, tuple[dict, ...]]:
    lines = source.read_text(encoding="latin-1").splitlines()
    templates: dict[str, list[dict]] = {}
    transform = ""
    shape = ""
    override_enabled = False
    override_color = 0
    for index, line in enumerate(lines):
        found = _TRANSFORM.search(line)
        if found:
            transform = found.group(1)
            templates.setdefault(transform, [])
        found = _SHAPE.search(line)
        if found:
            shape, transform = found.groups()
            override_enabled = False
            override_color = 0
        found = _OVERRIDE_ENABLED.search(line)
        if found:
            override_enabled = found.group(1) == "yes"
        found = _OVERRIDE_COLOR.search(line)
        if found:
            override_color = int(found.group(1))
        if 'setAttr ".cc" -type "nurbsCurve"' not in line:
            continue
        if not transform or not shape:
            raise ValueError(f"原版图标曲线缺少层级：第 {index + 1} 行")
        tokens = []
        for next_line in lines[index + 1:]:
            tokens.extend(next_line.replace(";", " ").split())
            if ";" in next_line:
                break
        degree, spans, form = map(int, tokens[:3])
        if tokens[3] != "no" or int(tokens[4]) != 3:
            raise ValueError("原版图标含未支持的有理曲线：" + shape)
        knot_count = int(tokens[5])
        knots = tuple(float(v) for v in tokens[6:6 + knot_count])
        point_offset = 6 + knot_count
        point_count = int(tokens[point_offset])
        numbers = tokens[point_offset + 1:]
        if (len(knots) != point_count + degree - 1
                or len(numbers) != 3 * point_count
                or spans != point_count - degree or form not in (0, 2)):
            raise ValueError("原版图标曲线数据无效：" + shape)
        templates[transform].append({
            "degree": degree,
            "periodic": form == 2,
            "override_enabled": override_enabled,
            "override_color": override_color,
            "knots": knots,
            "points": tuple(tuple(float(v) for v in numbers[i:i + 3])
                            for i in range(0, len(numbers), 3)),
        })
    return {name: tuple(shapes) for name, shapes in templates.items()
            if shapes}


def create_adv_icon(commands, *, name: str, parent: str,
                    template: str, radius: float,
                    fallback_normal: tuple[float, float, float],
                    fallback_sections: int = 8,
                    axis_offset: tuple[float, float, float] = (0, 0, 0)) -> str:
    """Make an original icon when installed, or preserve the prior circle."""
    if (not isinstance(name, str) or not name
            or not isinstance(parent, str) or not parent
            or not isinstance(radius, (int, float))
            or not isfinite(radius) or radius <= 0
            or len(axis_offset) != 3
            or any(not isinstance(value, (int, float))
                   or not isfinite(value) for value in axis_offset)):
        raise ValueError("控制器图标参数无效")
    source = _icon_source()
    if source is None:
        if axis_offset != (0, 0, 0):
            raise ValueError("按 Fit 轴旋转图标需要原版 asIcons.ma")
        curve = commands.circle(
            name=name, normal=fallback_normal, radius=radius,
            degree=3, sections=fallback_sections,
            constructionHistory=False)[0]
    else:
        shapes = _templates(source).get(template)
        if not shapes or len(shapes) != 1:
            raise ValueError("原版控制器图标模板缺失：" + template)
        spec = shapes[0]
        points = [tuple(float(value) * radius for value in
                        rotate_icon_point(point, axis_offset))
                  for point in spec["points"]]
        curve = commands.curve(
            name=name, degree=spec["degree"], point=points,
            knot=spec["knots"], periodic=spec["periodic"])
    control = commands.parent(curve, parent, relative=True)[0]
    control = (commands.ls(control, long=True) or [control])[0]
    actual = commands.listRelatives(control, shapes=True, fullPath=True,
                                    type="nurbsCurve") or []
    if len(actual) != 1:
        raise RuntimeError("控制器曲线形态读回不一致：" + name)
    if source is not None:
        if (int(commands.getAttr(actual[0] + ".degree"))
                != spec["degree"]
                or int(commands.getAttr(actual[0] + ".form"))
                != (2 if spec["periodic"] else 0)):
            raise RuntimeError("原版图标曲线参数读回不一致：" + name)
        for index in sorted({0, len(points) // 2, len(points) - 1}):
            position = commands.pointPosition(
                actual[0] + f".cv[{index}]", local=True)
            if any(abs(float(value) - expected) > 1e-4
                   for value, expected in zip(position, points[index])):
                raise RuntimeError("原版图标曲线轴向读回不一致：" + name)
        commands.setAttr(actual[0] + ".overrideEnabled",
                         spec["override_enabled"])
        commands.setAttr(actual[0] + ".overrideColor",
                         spec["override_color"])
        if (bool(commands.getAttr(actual[0] + ".overrideEnabled"))
                != spec["override_enabled"]
                or int(commands.getAttr(actual[0] + ".overrideColor"))
                != spec["override_color"]):
            raise RuntimeError("原版图标颜色读回不一致：" + name)
        commands.addAttr(control, longName="advPyIconTemplate",
                         dataType="string")
        commands.setAttr(control + ".advPyIconTemplate", template,
                         type="string", lock=True)
    return control


def original_fit_icon_axis_offset(commands, control_name: str
                                  ) -> tuple[float, float, float]:
    """Resolve asGetAxis(..., Main, 0) for a standard FK control."""
    fit = commands.ls("|Group|FitSkeleton", long=True,
                      type="transform") or ()
    if len(fit) != 1:
        raise ValueError("控制器图标找不到唯一 FitSkeleton")
    worldmatch = (commands.attributeQuery("worldmatch", node=fit[0],
                                         exists=True)
                  and bool(commands.getAttr(fit[0] + ".worldmatch")))
    primary, secondary = "X", "Y"
    if worldmatch:
        match = re.fullmatch(r"AdvPy_(.+)FK_[RL]",
                             control_name.rsplit(":", 1)[-1])
        if match is None:
            raise ValueError("FK 控制器名称不能解析 Fit 关节：" + control_name)
        source_name = re.sub(r"Part[0-9]+$", "", match.group(1))
        candidates = (source_name,)
        finger = re.fullmatch(r"(Thumb|Index|Middle|Ring|Pinky)([1-4])",
                              source_name)
        if finger:
            candidates += (finger.group(1) + "Finger" + finger.group(2),)
        joints = commands.listRelatives(fit[0], allDescendents=True,
                                        fullPath=True, type="joint") or ()
        source = []
        for candidate in candidates:
            source = [joint for joint in joints
                      if joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                      == candidate]
            if source:
                break
        if len(source) != 1:
            raise ValueError("控制器图标找不到唯一 Fit 关节：" + source_name)
        def axis(attribute: str, default: str) -> str:
            if not commands.attributeQuery(attribute, node=source[0],
                                           exists=True):
                return default
            names = commands.attributeQuery(attribute, node=source[0],
                                            listEnum=True) or ()
            if len(names) != 1:
                raise ValueError("Fit 关节轴枚举无效：" + source[0])
            options = names[0].split(":")
            index = int(commands.getAttr(source[0] + "." + attribute))
            if not 0 <= index < len(options):
                raise ValueError("Fit 关节轴枚举越界：" + source[0])
            return options[index]
        primary = axis("primaryAxis", "X")
        secondary = axis("secondaryAxis", "Y")
    return icon_axis_offset(primary, secondary)
