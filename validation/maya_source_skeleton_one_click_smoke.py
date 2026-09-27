"""Exercise the panel's root-namespace source skeleton to skinned character path."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> None:
    import maya.standalone
    maya.standalone.initialize(name="python")
    from maya import cmds
    from adv_py.core.fit_template import synthetic_body_source_fit_template
    from adv_py.core.fit_template import ordered_fit_joints
    from adv_py.core.fit_container import FitUpAxis
    from adv_py.core.variable_body_fit import variable_body_fit_template
    from adv_py.product.maya_panel_controller import MayaPanelController

    cmds.file(new=True, force=True)
    created = {}
    for spec in synthetic_body_source_fit_template(FitUpAxis.Y).joints:
        if spec.name in ("HeadEnd", "Heel", "FootSideInner",
                         "FootSideOuter", "ToesEnd"):
            continue
        parent = created.get(spec.parent)
        joint = cmds.createNode("joint", name=spec.name,
                                **({"parent": parent} if parent else {}))
        cmds.setAttr(joint + ".translate", *spec.local_position)
        created[spec.name] = joint
    mesh = cmds.polyCube(name="SourceMesh", width=8, height=18,
                         depth=5)[0]
    root = (cmds.ls(created["Root"], long=True) or [])[0]
    mesh = (cmds.ls(mesh, long=True) or [])[0]
    try:
        MayaPanelController().body_build_from_source(
            ":", root, meshes=("|MissingMesh",))
    except ValueError:
        assert not cmds.namespace(exists="AdvPy")
        assert not cmds.objExists("AdvPy:Root")
    else:
        raise AssertionError("无效网格没有整体回滚")
    result = MayaPanelController().body_build_from_source(
        ":", root, meshes=(mesh,), segment_influences=True)
    assert result.namespace == "AdvPy", result
    assert cmds.objExists("Root") and cmds.objExists("SourceMesh")
    assert cmds.objExists("AdvPy:Root_M")
    assert cmds.objExists("AdvPy:SourceMesh")
    skins = cmds.ls("AdvPy:*", type="skinCluster") or []
    assert len(skins) == 1, skins
    assert not (cmds.listHistory("SourceMesh") or []) or not any(
        cmds.nodeType(node) == "skinCluster"
        for node in cmds.listHistory("SourceMesh") or [])
    with tempfile.TemporaryDirectory(prefix="advpy-source-one-click-") as tmp:
        cmds.setKeyframe("AdvPy:AdvPy_Global", attribute="translateX",
                         time=1, value=0)
        cmds.setKeyframe("AdvPy:AdvPy_Global", attribute="translateX",
                         time=5, value=2)
        published = MayaPanelController().publish_fbx(
            "AdvPy", Path(tmp) / "character.fbx", start=1, end=5,
            include_skins=True)
        assert published.bytes_written > 0
        scene = str(Path(tmp) / "character.mb")
        cmds.file(rename=scene)
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(scene, open=True, force=True, executeScriptNodes=False)
        assert cmds.objExists("AdvPy:Root_M")
        assert len(cmds.ls("AdvPy:*", type="skinCluster") or []) == 1
    cmds.select("Root", replace=True)
    fit_count, fit_namespace = MayaPanelController().fit_from_selected_skeleton(":")
    assert fit_namespace == "AdvPy2" and fit_count >= 18
    assert cmds.objExists("AdvPy2:FitSkeleton")
    assert cmds.objExists("Root")
    cmds.file(new=True, force=True)
    variable = {}
    template = variable_body_fit_template(
        FitUpAxis.Y, spine_segments=3, with_hand=False)
    for spec in ordered_fit_joints(template):
        if spec.name in ("HeadEnd", "Heel", "FootSideInner",
                         "FootSideOuter", "ToesEnd"):
            continue
        parent = variable.get(spec.parent)
        joint = cmds.createNode("joint", name=spec.name,
                                **({"parent": parent} if parent else {}))
        cmds.setAttr(joint + ".translate", *spec.local_position)
        variable[spec.name] = joint
    mesh = cmds.polyCube(name="VariableMesh", width=8, height=18,
                         depth=5)[0]
    variable_result = MayaPanelController().body_build_from_source(
        ":", cmds.ls(variable["Root"], long=True)[0],
        meshes=(cmds.ls(mesh, long=True)[0],), segment_influences=True)
    assert variable_result.joint_count == 31, variable_result
    assert cmds.objExists("AdvPy:Spine2_M")
    assert len(cmds.ls("AdvPy:*", type="skinCluster") or []) == 1
    print("PASS root source to namespaced skinned Body", result)


if __name__ == "__main__":
    main()
