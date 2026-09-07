import unittest
from contextlib import contextmanager
from dataclasses import replace

from adv_py.application import EditSkinWeights
from adv_py.core import (
    SkinInfluenceWeight,
    SkinVertexWeights,
    SkinWeightInputState,
    SkinWeightValidationError,
    audit_skin_weight_input,
    skin_weight_request,
)


A = "|JointA"
B = "|JointB"


def vertex(index, *weights):
    return SkinVertexWeights(
        index,
        tuple(SkinInfluenceWeight(path, value) for path, value in weights),
    )


class FakeSkinWeightHost:
    def __init__(self, *, faulty_result=False):
        self.state = SkinWeightInputState(
            "AdvPy_BodySkin",
            "|BodyMesh",
            8,
            (A, B),
            (),
            2,
            True,
            (vertex(0, (A, 0.6), (B, 0.4)),),
        )
        self.faulty_result = faulty_result
        self.transaction_count = 0
        self.written = False

    def capture_skin_weight_input(self, request):
        del request
        if self.faulty_result and self.written:
            return replace(
                self.state,
                vertices=(vertex(0, (A, 0.9), (B, 0.1)),),
            )
        return self.state

    @contextmanager
    def transaction(self, label):
        del label
        before = self.state
        self.transaction_count += 1
        try:
            yield
        except Exception:
            self.state = before
            self.written = False
            raise

    def apply_skin_weight_changes(self, request, changes):
        del request
        current = {item.vertex_index: item for item in self.state.vertices}
        for change in changes:
            current[change.vertex_index] = SkinVertexWeights(
                change.vertex_index,
                change.after,
            )
        self.state = replace(
            self.state,
            vertices=tuple(current[index] for index in sorted(current)),
        )
        self.written = True


class SkinWeightTests(unittest.TestCase):
    def test_request_is_canonical_and_requires_normalized_weights(self):
        request = skin_weight_request(
            "AdvPy_BodySkin",
            "|BodyMesh",
            (vertex(3, (B, 0.25), (A, 0.75)),),
        )
        self.assertEqual(
            tuple(entry.influence_path for entry in request.vertices[0].weights),
            (A, B),
        )
        with self.assertRaises(SkinWeightValidationError):
            skin_weight_request(
                "AdvPy_BodySkin",
                "|BodyMesh",
                (vertex(0, (A, 0.4), (B, 0.4)),),
            )

    def test_preflight_reports_locked_and_out_of_range_targets(self):
        request = skin_weight_request(
            "AdvPy_BodySkin",
            "|BodyMesh",
            (vertex(9, (A, 1.0)),),
        )
        state = SkinWeightInputState(
            "AdvPy_BodySkin",
            "|BodyMesh",
            8,
            (A, B),
            (A,),
            2,
            True,
            (),
        )
        codes = {issue.code for issue in audit_skin_weight_input(request, state)}
        self.assertEqual(codes, {"vertex_out_of_range", "influence_locked"})

    def test_noop_does_not_open_transaction(self):
        host = FakeSkinWeightHost()
        result = EditSkinWeights(host).apply(
            "AdvPy_BodySkin",
            "|BodyMesh",
            (vertex(0, (B, 0.4), (A, 0.6)),),
        )
        self.assertEqual(result.changed_vertex_count, 0)
        self.assertEqual(host.transaction_count, 0)

    def test_applies_once_and_rolls_back_faulty_result(self):
        target = (vertex(0, (A, 1.0)),)
        host = FakeSkinWeightHost()
        result = EditSkinWeights(host).apply(
            "AdvPy_BodySkin",
            "|BodyMesh",
            target,
        )
        self.assertEqual(result.changed_vertex_count, 1)
        self.assertEqual(host.transaction_count, 1)
        self.assertEqual(host.state.vertices, target)

        faulty = FakeSkinWeightHost(faulty_result=True)
        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            EditSkinWeights(faulty).apply(
                "AdvPy_BodySkin",
                "|BodyMesh",
                target,
            )
        self.assertEqual(
            faulty.state.vertices,
            (vertex(0, (A, 0.6), (B, 0.4)),),
        )


if __name__ == "__main__":
    unittest.main()
