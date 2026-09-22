import unittest

from adv_py.application import RetargetMocapVariableScheduledToCharacter
from adv_py.core.character_registry import CharacterRegistryError


class VariableMocapScheduleTests(unittest.TestCase):
    def test_events_are_explicit_and_bound_to_sampled_frames(self):
        service = RetargetMocapVariableScheduledToCharacter(
            object(),
            spine_events=((1, "fk"), (5, "ik"), (8, "fk")),
            limb_events={
                ("arm", "R"): ((1, "fk"),),
                ("arm", "L"): ((1, "fk"),),
                ("leg", "R"): ((1, "fk"),),
                ("leg", "L"): ((1, "fk"),),
            },
        )
        self.assertEqual(
            service._ik_frames(service._spine_events, tuple(range(1, 11))),
            (5, 6, 7),
        )
        with self.assertRaises(CharacterRegistryError):
            service._ik_frames(service._spine_events, (1, 3, 5, 7, 9))
        with self.assertRaises(CharacterRegistryError):
            service._events(((1, "fk"), (1, "ik")))
        with self.assertRaises(CharacterRegistryError):
            service._events(((1, "fk"), (5, "fk")))
        with self.assertRaises(CharacterRegistryError):
            RetargetMocapVariableScheduledToCharacter(
                object(), spine_events=((1, "fk"),),
                limb_events={("arm", "R"): ((1, "ik"),)},
            )
        with self.assertRaises(CharacterRegistryError):
            RetargetMocapVariableScheduledToCharacter(
                object(), spine_events=((1, "fk"),),
                limb_events={pair: ((1, "fk"),) for pair in service.LIMBS},
                replace_existing_modes=1,
            )


if __name__ == "__main__":
    unittest.main()
