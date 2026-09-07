from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import json
import re


PROC_HEADER = re.compile(
    r"(?ms)^\s*(?P<global>global\s+)?proc\s+"
    r"(?:(?P<return_type>string|int|float|vector|matrix)(?P<return_array>\[\])?\s+)?"
    r"(?P<name>[A-Za-z_]\w*)\s*\((?P<parameters>.*?)\)\s*\{"
)
GLOBAL_VAR = re.compile(
    r"(?m)^\s*global\s+(?:string|int|float|vector|matrix)(?:\[\])?\s+\$(\w+)"
)
DYNAMIC_EVAL = re.compile(r"\b(eval|evalDeferred)\b")


@dataclass(frozen=True)
class Procedure:
    name: str
    line_start: int
    line_end: int
    return_type: str
    parameters: str
    is_global: bool
    line_count: int
    category: str
    calls: tuple[str, ...]
    dynamic_eval_count: int


@dataclass(frozen=True)
class Inventory:
    source: str
    sha256: str
    byte_count: int
    line_count: int
    procedures: tuple[Procedure, ...]
    global_variables: tuple[str, ...]
    top_level_dynamic_eval_count: int

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "procedures": [asdict(proc) for proc in self.procedures],
        }


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _matching_brace(text: str, opening: int) -> int:
    depth = 0
    index = opening
    state = "code"
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""

        if state == "line_comment":
            if char == "\n":
                state = "code"
        elif state == "block_comment":
            if char == "*" and nxt == "/":
                state = "code"
                index += 1
        elif state == "string":
            if char == "\\":
                index += 1
            elif char == '"':
                state = "code"
        else:
            if char == "/" and nxt == "/":
                state = "line_comment"
                index += 1
            elif char == "/" and nxt == "*":
                state = "block_comment"
                index += 1
            elif char == '"':
                state = "string"
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index
        index += 1
    raise ValueError(f"Unclosed procedure body beginning at character {opening}")


def _category(name: str) -> str:
    lowered = name.lower()
    rules = (
        ("face", ("face", "phoneme", "emotion", "eyelid", "eyebrow", "lip")),
        ("fit", ("fit", "placement", "jointlabel")),
        ("deform", ("skin", "deform", "blendshape", "deltamush", "wrap")),
        ("export", ("export", "unreal", "fbx", "metahuman")),
        ("mocap", ("mocap", "motioncapture", "retarget")),
        ("ui", ("window", "layout", "button", "menu", "help", "updatebutton")),
        ("body_build", ("build", "rebuild", "body", "ik", "fk", "control")),
    )
    for category, needles in rules:
        if any(needle in lowered for needle in needles):
            return category
    return "shared"


def inventory(path: Path) -> Inventory:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    matches = list(PROC_HEADER.finditer(text))
    names = {match.group("name") for match in matches}
    name_alternation = "|".join(
        re.escape(name) for name in sorted(names, key=len, reverse=True)
    )
    call_pattern = re.compile(
        r"(?<![A-Za-z0-9_])(" + name_alternation + r")\s*(?:\(|;|`)"
    )
    procedures: list[Procedure] = []
    body_ranges: list[tuple[int, int]] = []

    for match in matches:
        opening = match.end() - 1
        closing = _matching_brace(text, opening)
        body = text[opening + 1 : closing]
        calls = tuple(
            sorted(
                {
                    dependency.group(1)
                    for dependency in call_pattern.finditer(body)
                    if dependency.group(1) != match.group("name")
                }
            )
        )
        start_line = _line_number(text, match.start())
        end_line = _line_number(text, closing)
        return_type = match.group("return_type") or "void"
        if match.group("return_array"):
            return_type += "[]"
        procedures.append(
            Procedure(
                name=match.group("name"),
                line_start=start_line,
                line_end=end_line,
                return_type=return_type,
                parameters=" ".join(match.group("parameters").split()),
                is_global=bool(match.group("global")),
                line_count=end_line - start_line + 1,
                category=_category(match.group("name")),
                calls=calls,
                dynamic_eval_count=len(DYNAMIC_EVAL.findall(body)),
            )
        )
        body_ranges.append((match.start(), closing + 1))

    top_level = list(text)
    for start, end in body_ranges:
        top_level[start:end] = " " * (end - start)
    return Inventory(
        source=str(path.resolve()),
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
        line_count=text.count("\n") + 1,
        procedures=tuple(procedures),
        global_variables=tuple(sorted(set(GLOBAL_VAR.findall(text)))),
        top_level_dynamic_eval_count=len(DYNAMIC_EVAL.findall("".join(top_level))),
    )


def write_reports(result: Inventory, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "mel_inventory.json"
    md_path = output_dir / "mel_inventory.md"
    json_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    categories = Counter(proc.category for proc in result.procedures)
    longest = sorted(result.procedures, key=lambda proc: proc.line_count, reverse=True)[:20]
    eval_procs = sorted(
        (proc for proc in result.procedures if proc.dynamic_eval_count),
        key=lambda proc: proc.dynamic_eval_count,
        reverse=True,
    )[:20]
    edges = sum(len(proc.calls) for proc in result.procedures)
    lines = [
        "# MEL 源码体检",
        "",
        f"- 源文件：`{result.source}`",
        f"- SHA-256：`{result.sha256}`",
        f"- 规模：{result.line_count:,} 行 / {result.byte_count:,} 字节",
        f"- 顶层过程：{len(result.procedures):,} 个",
        f"- 过程间静态调用边：{edges:,} 条",
        f"- MEL 全局变量：{len(result.global_variables):,} 个",
        f"- 含动态 eval 的过程：{sum(bool(p.dynamic_eval_count) for p in result.procedures):,} 个",
        "",
        "## 建议模块分布",
        "",
        "| 模块 | 过程数 |",
        "| --- | ---: |",
        *[f"| {name} | {count} |" for name, count in sorted(categories.items())],
        "",
        "## 最大的过程",
        "",
        "| 过程 | 行数 | 起始行 | 分类 | 静态依赖数 |",
        "| --- | ---: | ---: | --- | ---: |",
        *[
            f"| `{proc.name}` | {proc.line_count} | {proc.line_start} | {proc.category} | {len(proc.calls)} |"
            for proc in longest
        ],
        "",
        "## 动态执行热点",
        "",
        "| 过程 | eval 次数 | 起始行 |",
        "| --- | ---: | ---: |",
        *[
            f"| `{proc.name}` | {proc.dynamic_eval_count} | {proc.line_start} |"
            for proc in eval_procs
        ],
        "",
        "> 分类来自命名启发式，仅用于规划第一轮拆分；每个过程迁移前仍需人工确认副作用。",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path
