"""ADV 6.925 asFitFingerUp's fixed finger names and off-axis prompt."""
from dataclasses import dataclass

from .corrective_shapes import corrective_round


SOURCE_FINGERS = ('Thumb', 'Pinky', 'Ring', 'Middle', 'Index')
SOURCE_FINGER_CHECK_CHANNELS = (
    'rotateX', 'rotateY', 'rotateZ', 'jointOrientX', 'jointOrientZ')


@dataclass(frozen=True, slots=True)
class SourceFitFinger:
    name: str
    indices: tuple[int, ...]

    @property
    def first(self):
        return self.indices[0] if self.indices else -1

    @property
    def last(self):
        # Missing fingers are not silently excluded in the MEL loop: its
        # eventual position query fails. Preserve that unsupported input.
        return self.indices[-1] if self.indices else 0

    def joint(self, index):
        return self.name+'Finger'+str(index)


def source_fit_fingers(existing):
    names = set(existing)
    return tuple(SourceFitFinger(finger, tuple(index for index in range(5)
        if finger+'Finger'+str(index) in names)) for finger in SOURCE_FINGERS)


def source_fit_finger_off_axis(samples):
    """Only finger-parent children are sampled by the scene adapter."""
    return tuple((joint, channel, rounded) for joint, channel, value in samples
                 if (rounded := corrective_round(float(value), 3)) != 0.)


def source_fit_finger_confirmation(rows):
    if not rows:
        return ''
    return ('Turning On Finger-up, will snap finger rotations to bend only in Y axis\n'
            'These are currently "Off-Axis":\n\n'+''.join(
                f'{joint}.{channel} = {value:g}\n' for joint, channel, value in rows))
