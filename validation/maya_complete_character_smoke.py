"""One integrated control-to-deformation acceptance run, generated assets only."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "examples")]
import maya.standalone


def main(output, with_hand=True):
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from maya.api import OpenMaya as om
        from maya_complete_character import build_character, CharacterExampleHost
        from adv_py.application import MatchBodySpine, SwitchBodyControlSpace

        cmds.file(new=True, force=True)
        cmds.upAxis(axis="z", rotateView=False)
        cmds.undoInfo(state=True)
        marker = cmds.createNode("transform", name="CompleteCharacterSelection")
        cmds.select(marker)
        checks = {}
        class FailedHost(CharacterExampleHost):
            def apply_skin_weight_changes(self, request, changes):
                super().apply_skin_weight_changes(request, changes)
                raise RuntimeError("Injected full workflow skin failure")
        try:
            build_character(with_hand=with_hand, host=FailedHost())
            checks["late_failure_rolls_back_complete_workflow"] = False
        except RuntimeError as exc:
            if "Injected" not in str(exc):
                raise
            checks["late_failure_rolls_back_complete_workflow"] = not (cmds.ls(type="joint") or cmds.ls(type="mesh") or cmds.ls("AdvPy_*", "FitSkeleton"))
        demo = build_character(with_hand=with_hand)
        host, rig = demo.host, demo.rig
        original_pose = host.capture_control_space_pose(rig.plan.control_spaces)
        original_vertices = tuple(cmds.xform(demo.mesh+".vtx[*]",query=True,worldSpace=True,translation=True))
        cmds.undo()
        checks["one_undo_removes_fit_body_rig_mesh_and_skin"] = not (cmds.ls(type="joint") or cmds.ls(type="mesh") or cmds.ls("AdvPy_*", "FitSkeleton"))
        cmds.redo()
        checks["redo_restores_complete_workflow"] = cmds.objExists(demo.skin) and len(host.capture_body_skeleton(rig.body.root).joints) == (70 if with_hand else 30)
        from adv_py.core.body_control_spaces import control_space_pose_error
        redo_pose_error = control_space_pose_error(original_pose,host.capture_control_space_pose(rig.plan.control_spaces))
        redo_mesh_error = max(abs(a-b) for a,b in zip(original_vertices,cmds.xform(demo.mesh+".vtx[*]",query=True,worldSpace=True,translation=True)))
        checks["redo_preserves_all_body_offsets_and_mesh_positions"] = max(redo_pose_error,redo_mesh_error)<1e-4
        before_nodes = set(cmds.ls(long=True))
        try:
            build_character(with_hand=with_hand)
            checks["occupied_scene_rejected_without_writes"] = False
        except ValueError:
            checks["occupied_scene_rejected_without_writes"] = before_nodes == set(cmds.ls(long=True))

        def points():
            selection = om.MSelectionList()
            selection.add(demo.mesh)
            return tuple(tuple(p)[:3] for p in om.MFnMesh(selection.getDagPath(0).extendToShape()).getPoints(om.MSpace.kWorld))
        def matrix(path):
            return om.MMatrix(cmds.xform(path, query=True, worldSpace=True, matrix=True))
        rest = points()
        inverse_bind = {j.path: matrix(j.path).inverse() for j in rig.body.joints}
        readback = host.capture_all_skin_weights(demo.skin, demo.mesh)
        wanted = {v.vertex_index: {w.influence_path:w.weight for w in v.weights} for v in demo.weights}
        weight_error = max(abs(w.weight-wanted[v.vertex_index].get(w.influence_path,0)) for v in readback.vertices for w in v.weights)
        checks["all_vertices_have_explicit_two_joint_normalized_weights"] = (
            len(readback.vertices) == len(rest) and weight_error < 1e-6
            and all(len(v.weights)==2 and abs(sum(w.weight for w in v.weights)-1)<1e-6 for v in readback.vertices)
            and set(w.influence_path for v in readback.vertices for w in v.weights) == set(inverse_bind))
        checks["linear_skinning_active"] = cmds.getAttr(demo.skin + ".skinningMethod") == 0
        errors, movements = {}, {}
        def audit(label, before=None):
            transforms = {p: inv*matrix(p) for p,inv in inverse_bind.items()}
            expected = []
            for vertex in demo.weights:
                p = om.MPoint(*rest[vertex.vertex_index])
                blend = [0.0,0.0,0.0]
                for weight in vertex.weights:
                    transformed = p*transforms[weight.influence_path]
                    for axis in range(3):
                        blend[axis] += transformed[axis]*weight.weight
                expected.append(blend)
            actual = points()
            errors[label] = max(abs(a-b) for e,r in zip(expected,actual) for a,b in zip(e,r))
            if before is not None:
                movements[label] = max(abs(a-b) for e,r in zip(before,actual) for a,b in zip(e,r))
            return actual
        def edit(path, attr, value):
            cmds.setAttr(path + "." + attr, value)
        def motion(label, fn):
            before = points()
            fn()
            audit(label, before)

        spine = rig.plan.torso.torso.spine
        motion("torso_fk", lambda: edit(spine.fk_controls[1], "rotateZ", -20))
        before = points()
        MatchBodySpine(host).execute(spine,"ik")
        after = audit("spine_fk_to_ik")
        pose_errors = [max(abs(a-b) for p,q in zip(before,after) for a,b in zip(p,q))]
        motion("torso_ik", lambda: edit(spine.ik_control,"translateY",cmds.getAttr(spine.ik_control+".translateY")+0.3))
        before = points()
        MatchBodySpine(host).execute(spine,"fk")
        after = audit("spine_ik_to_fk")
        pose_errors.append(max(abs(a-b) for p,q in zip(before,after) for a,b in zip(p,q)))
        for name,module in (("arm",rig.plan.arm),("leg",rig.plan.leg)):
            for control in module.fk_controls.controls:
                if "Elbow" in control.control_name or "Knee" in control.control_name:
                    motion(name+"_fk_"+control.side.value, lambda c=control: edit(c.control_path,"rotateZ",12))
            for side in module.blend.sides:
                edit(module.blend.settings_path,side.attribute,1)
            for limb in module.ik.limbs:
                target = limb.wrist_control_path if name=="arm" else limb.ankle_control_path
                motion(name+"_ik_"+limb.side.value,lambda p=target: edit(p,"translateY",0.3))
        for control in rig.plan.torso.torso.controls.controls:
            if control.driven_joint.endswith("|Head_M"):
                motion("head",lambda p=control.control_path: edit(p,"rotateY",15))
        if rig.plan.hand:
            for control in rig.plan.hand.controls.controls:
                if "Index" in control.control_name and "1" in control.control_name:
                    motion("finger_"+control.side.value,lambda p=control.control_path: edit(p,"rotateZ",20))
        switch = SwitchBodyControlSpace(host)
        for spec in rig.plan.control_spaces.spaces:
            for mode in ("body","global"):
                before = points()
                switch.execute(rig.plan.control_spaces,spec.key,mode)
                after = audit("space_"+spec.key+"_"+mode)
                pose_errors.append(max(abs(a-b) for p,q in zip(before,after) for a,b in zip(p,q)))
        global_control = rig.plan.global_control.control_path
        for attr,value in (("translateX",3),("rotateZ",25),("globalScale",1.5)):
            motion("global_"+attr,lambda a=attr,v=value: edit(global_control,a,v))
        checks["all_deformations_match_independent_linear_skin_equation"] = max(errors.values()) < 1e-4
        expected_actions = {"torso_fk","torso_ik","arm_fk_R","arm_fk_L","leg_fk_R","leg_fk_L","arm_ik_R","arm_ik_L","leg_ik_R","leg_ik_L","head","global_translateX","global_rotateZ","global_globalScale"}
        if with_hand:
            expected_actions.update(("finger_R","finger_L"))
        checks["every_representative_action_moves_vertices"] = set(movements)==expected_actions and min(movements.values()) > 1e-4
        checks["matches_and_spaces_preserve_deformed_mesh"] = max(pose_errors)<1e-4
        checks["selection_and_time_preserved"] = cmds.ls(selection=True)==[marker] and cmds.currentTime(query=True)==1
        report = {"host":"maya", "version":cmds.about(version=True),"body_joint_count":len(rig.body.joints),"vertex_count":len(rest),**checks,
                  "max_redo_pose_error":redo_pose_error,"max_redo_mesh_error":redo_mesh_error,"max_weight_error":weight_error,"max_skin_equation_error":max(errors.values()),"max_pose_switch_vertex_error":max(pose_errors),
                  "deformation_errors":errors,"action_vertex_displacements":movements,
                  "duration_seconds":round(time.perf_counter()-started,3),"status":"passed" if all(checks.values()) else "failed"}
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(report,indent=2))
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__=="__main__":
    raise SystemExit(main(Path(sys.argv[1]),with_hand="--basic" not in sys.argv[2:]))
