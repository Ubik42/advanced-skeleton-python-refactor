import unittest

from adv_py.application import body_with_hand_orientation_request
from adv_py.core import (
    BODY_HAND_DIGITS,
    BODY_HAND_SEGMENTS,
    BodyHandDigit,
    FitSkeletonValidationError,
    FitUpAxis,
    body_hand_source_joint_names,
    predict_fit_template_hierarchy,
    synthetic_body_with_hand_source_fit_template,
)


class BodyHandFitTests(unittest.TestCase):
    def test_builds_five_complete_digit_chains_from_wrist(self):
        template = synthetic_body_with_hand_source_fit_template(FitUpAxis.Z)
        by_name = {joint.name: joint for joint in template.joints}

        self.assertEqual(len(template.joints), 38)
        self.assertEqual(BODY_HAND_DIGITS, tuple(BodyHandDigit))
        self.assertEqual(BODY_HAND_SEGMENTS, ("1", "2", "3", "End"))
        self.assertEqual(len(body_hand_source_joint_names()), 20)
        for digit in BODY_HAND_DIGITS:
            names = tuple(f"{digit.value}{part}" for part in BODY_HAND_SEGMENTS)
            self.assertEqual(by_name[names[0]].parent, "Wrist")
            self.assertEqual(by_name[names[1]].parent, names[0])
            self.assertEqual(by_name[names[2]].parent, names[1])
            self.assertEqual(by_name[names[3]].parent, names[2])
            self.assertEqual(
                tuple(by_name[name].label.text for name in names),
                ("Finger",) * 4,
            )

    def test_maps_palm_spread_to_the_scene_up_plane(self):
        y_template = synthetic_body_with_hand_source_fit_template(FitUpAxis.Y)
        z_template = synthetic_body_with_hand_source_fit_template(FitUpAxis.Z)
        y = {joint.name: joint for joint in y_template.joints}
        z = {joint.name: joint for joint in z_template.joints}

        self.assertEqual(y["Pinky1"].local_position, (-0.35, 0.0, 1.05))
        self.assertEqual(z["Pinky1"].local_position, (-0.35, 1.05, 0.0))
        self.assertEqual(y["Middle2"].local_position, (-1.08, 0.0, 0.0))
        self.assertEqual(z["Middle2"].local_position, (-1.08, 0.0, 0.0))
        with self.assertRaises(FitSkeletonValidationError):
            synthetic_body_with_hand_source_fit_template(FitUpAxis.Z, scale=0)

    def test_orientation_request_selects_middle_finger_for_wrist(self):
        request = body_with_hand_orientation_request()
        selected = {item.joint: item.child for item in request.child_selections}
        template = synthetic_body_with_hand_source_fit_template(FitUpAxis.Z)
        predicted = predict_fit_template_hierarchy(template, "|FitSkeleton")

        self.assertEqual(len(request.joints), 28)
        self.assertEqual(selected["Wrist"], "Middle1")
        wrist = next(node for node in predicted.joints if node.short_name == "Wrist")
        branches = {
            node.short_name
            for node in predicted.joints
            if node.dag_parent == wrist.path
        }
        self.assertEqual(
            branches,
            {f"{digit.value}1" for digit in BODY_HAND_DIGITS},
        )


if __name__ == "__main__":
    unittest.main()
