"""Guard migrated runtime layers against accidental legacy/DCC imports."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "adv_py"


def main(output: Path) -> int:
    problems = []
    imported = 0
    mel_sites = []
    checked = 0
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(PACKAGE).as_posix()
        checked += 1
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        isolated = relative.startswith(("core/", "application/", "product/"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                imported += 1
                if (name.startswith("adv_py.legacy")
                        or (isinstance(node, ast.ImportFrom) and node.level
                            and name.split(".", 1)[0] == "legacy")):
                    problems.append(f"{relative}:{node.lineno}: legacy bridge import")
                if isolated and name.split(".", 1)[0] in ("maya", "bpy"):
                    problems.append(f"{relative}:{node.lineno}: DCC import in portable layer")
            if isinstance(node, ast.Name) and node.id == "LegacyMelBridge":
                problems.append(f"{relative}:{node.lineno}: legacy bridge reference")
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "eval"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "mel"):
                mel_sites.append(f"{relative}:{node.lineno}")
                native_bind_dialog = (relative == "adapters/maya_deform_skinning.py"
                    and len(node.args) == 1
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "SmoothBindSkinOptions")
                if relative != "adapters/maya_body.py" and not native_bind_dialog:
                    problems.append(f"{relative}:{node.lineno}: unexpected MEL call")
    report = {"modules_checked": checked, "imports_checked": imported,
              "legacy_runtime_references": 0 if not problems else None,
              "fbx_plugin_mel_sites": sum(site.startswith("adapters/maya_body.py:")
                                          for site in mel_sites),
              "native_bind_dialog_mel_sites": sum(site.startswith(
                  "adapters/maya_deform_skinning.py:") for site in mel_sites),
              "problems": problems, "status": "passed" if not problems else "failed"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
