"""Group registered Inbetween segments by their existing IK handle."""
from __future__ import annotations

from dataclasses import dataclass, replace

from adv_py.core.fit_inbetween_ik_parts import (
    InbetweenIkPartsPlan, plan_inbetween_ik_parts,
)
from adv_py.core.fit_inbetween_ik_solver import (
    InbetweenIkSolverPlan, plan_inbetween_ik_solver,
)
from adv_py.core.fit_inbetween_ik_rebase import (
    rebase_inbetween_ik_mechanisms,
    rebase_inbetween_ik_reference,
    rebase_inbetween_spine_mechanisms,
)

from .body_character_rig import BodyCharacterRigBuildPlan
from .fit_inbetween_limb_mapping import InbetweenLimbBinding


@dataclass(frozen=True, slots=True)
class InbetweenIkSolverRequest:
    plan: InbetweenIkSolverPlan
    segments: tuple[InbetweenIkPartsPlan, ...]


@dataclass(frozen=True, slots=True)
class InbetweenIkSolverMapping:
    requests: tuple[InbetweenIkSolverRequest, ...]


def plan_character_inbetween_ik_solvers(
    bindings: tuple[InbetweenLimbBinding, ...],
    rig: BodyCharacterRigBuildPlan,
) -> InbetweenIkSolverMapping:
    """Collect all RP edges, then the toe single-chain edge after leg rebase."""
    pending = {
        (binding.start_ik_driver, binding.end_ik_driver): binding
        for binding in bindings
    }
    if len(pending) != len(bindings):
        raise ValueError("Inbetween IK 骨段重复登记")
    requests = []

    def collect(
        chain: tuple[str, ...], *, handle_name: str,
        effector_name: str, solver_name: str,
        handle_parent_path: str, pole_control_path: str,
        pole_constraint_name: str,
    ) -> None:
        segments = []
        for edge in zip(chain, chain[1:]):
            binding = pending.pop(edge, None)
            if binding is not None:
                segments.append(plan_inbetween_ik_parts(
                    binding.parts, start_ik_driver=edge[0],
                    end_ik_driver=edge[1]))
        if segments:
            plan = plan_inbetween_ik_solver(
                chain, tuple(segments), handle_name=handle_name,
                effector_name=effector_name, solver_name=solver_name,
                handle_parent_path=handle_parent_path,
                pole_control_path=pole_control_path,
                pole_constraint_name=pole_constraint_name)
            requests.append(InbetweenIkSolverRequest(
                plan, tuple(segments)))

    for spec in rig.arm.ik.limbs:
        collect(spec.chain, handle_name=spec.handle_name,
                effector_name=spec.handle_name.replace("Handle", "Effector"),
                solver_name="ikRPsolver",
                handle_parent_path=spec.wrist_control_path,
                pole_control_path=spec.pole_control_path,
                pole_constraint_name=spec.pole_constraint_name)
    foot_by_side = {spec.side: spec for spec in rig.leg.foot.sides}
    for spec in rig.leg.ik.limbs:
        foot = foot_by_side.get(spec.side)
        if foot is None or foot.handle_name != spec.handle_name:
            raise ValueError("Inbetween IK 缺少对应的足部 handle 父层")
        collect(spec.chain, handle_name=spec.handle_name,
                effector_name=spec.handle_name.replace("Handle", "Effector"),
                solver_name="ikRPsolver",
                handle_parent_path=foot.final_handle_parent_path,
                pole_control_path=spec.pole_control_path,
                pole_constraint_name=spec.pole_constraint_name)
    spine = (rig.torso.torso.spine if rig.torso is not None else None)
    if spine is not None:
        collect(tuple(spec.path for spec in spine.joints[3:]),
                handle_name="AdvPy_SpineIKHandle",
                effector_name="AdvPy_SpineIKEffector",
                solver_name="ikRPsolver",
                handle_parent_path=spine.ik_control,
                pole_control_path=spine.pole_control,
                pole_constraint_name="AdvPy_SpinePoleConstraint")
    rp_solvers = tuple(request.plan for request in requests)
    for foot in rig.leg.foot.sides:
        original_edge = (foot.ankle_driver_path,
                         foot.toe_driver_path)
        binding = pending.pop(original_edge, None)
        if binding is None:
            continue
        active = rebase_inbetween_ik_reference(
            foot, rp_solvers)
        chain = (active.ankle_driver_path,
                 active.toe_driver_path)
        segment = plan_inbetween_ik_parts(
            binding.parts, start_ik_driver=chain[0],
            end_ik_driver=chain[1])
        toe_plan = plan_inbetween_ik_solver(
            chain, (segment,), handle_name=foot.toe_handle_name,
            effector_name=foot.toe_effector_name,
            solver_name="ikSCsolver",
            handle_parent_path=foot.toe_handle_parent_path,
            pole_control_path=None, pole_constraint_name=None)
        requests.append(InbetweenIkSolverRequest(
            toe_plan, (segment,)))
    for foot in rig.leg.foot.sides:
        original_edge = (foot.toe_driver_path,
                         foot.toe_end_driver_path)
        binding = pending.pop(original_edge, None)
        if binding is None:
            continue
        active = rebase_inbetween_ik_reference(
            foot, tuple(request.plan for request in requests))
        chain = (active.toe_driver_path,
                 active.toe_end_driver_path)
        segment = plan_inbetween_ik_parts(
            binding.parts, start_ik_driver=chain[0],
            end_ik_driver=chain[1])
        toe_end_plan = plan_inbetween_ik_solver(
            chain, (segment,), handle_name=foot.toe_end_handle_name,
            effector_name=foot.toe_end_effector_name,
            solver_name="ikSCsolver",
            handle_parent_path=foot.toe_control_path,
            pole_control_path=None, pole_constraint_name=None)
        requests.append(InbetweenIkSolverRequest(
            toe_end_plan, (segment,)))
    if pending:
        raise ValueError("Inbetween IK 骨段没有对应求解器："
                         + str(next(iter(pending))))
    return InbetweenIkSolverMapping(tuple(requests))


def rebase_character_rig_after_inbetween_ik(
    rig: BodyCharacterRigBuildPlan,
    mapping: InbetweenIkSolverMapping,
) -> BodyCharacterRigBuildPlan:
    """Return a rig plan whose paths and IK audits describe expanded chains.

    This is a plan rewrite only.  The caller must apply the matching solver
    operations in the scene before using the returned plan to capture nodes.
    """
    solvers = tuple(request.plan for request in mapping.requests)
    if not solvers:
        return rig
    by_handle = {solver.handle_name: solver for solver in solvers}
    if len(by_handle) != len(solvers):
        raise ValueError("Inbetween IK 求解器重复登记")
    rebased = rebase_inbetween_ik_reference(rig, solvers)
    arm_ik = replace(rebased.arm.ik, limbs=tuple(
        replace(spec, solver_joint_list=by_handle[spec.handle_name].solved_joint_list)
        if spec.handle_name in by_handle else spec
        for spec in rebased.arm.ik.limbs))
    leg_ik = replace(rebased.leg.ik, limbs=tuple(
        replace(spec, solver_joint_list=by_handle[spec.handle_name].solved_joint_list)
        if spec.handle_name in by_handle else spec
        for spec in rebased.leg.ik.limbs))
    arm = replace(rebased.arm, ik=arm_ik,
                  mechanisms=rebase_inbetween_ik_mechanisms(
                      rig.arm.mechanisms, solvers))
    foot_plan = replace(rebased.leg.foot, sides=tuple(
        replace(
            spec,
            toe_solver_joint_list=(
                by_handle[spec.toe_handle_name].solved_joint_list
                if spec.toe_handle_name in by_handle
                else spec.toe_solver_joint_list),
            toe_end_solver_joint_list=(
                by_handle[spec.toe_end_handle_name].solved_joint_list
                if spec.toe_end_handle_name in by_handle
                else spec.toe_end_solver_joint_list),
        ) for spec in rebased.leg.foot.sides))
    leg = replace(rebased.leg, ik=leg_ik, foot=foot_plan,
                  mechanisms=rebase_inbetween_ik_mechanisms(
                      rig.leg.mechanisms, solvers))
    torso = rebased.torso
    if torso is not None and torso.torso.spine is not None:
        spine = rebase_inbetween_spine_mechanisms(
            rig.torso.torso.spine, solvers)
        spine_solver = by_handle.get("AdvPy_SpineIKHandle")
        if spine_solver is not None:
            spine = replace(spine,
                            solver_joint_list=spine_solver.solved_joint_list)
        torso = replace(torso, torso=replace(torso.torso, spine=spine))
    return replace(rebased, arm=arm, leg=leg, torso=torso)
