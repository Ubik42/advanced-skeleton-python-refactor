"""Native BodyRig JSON scalar rules; ADV MEL 23592–23858."""


def dominant_axis(values):
    """Native strict comparisons keep X, then Y, then Z on equal lengths."""
    axis = 0
    maximum = abs(values[0])
    for candidate in (1, 2):
        if abs(values[candidate]) > maximum:
            axis, maximum = candidate, abs(values[candidate])
    result = [0., 0., 0.]
    result[axis] = -1. if values[axis] < 0 else 1.
    return result, axis


def ik_axes(middle_offset, pole_local=None):
    primary, axis = dominant_axis(middle_offset)
    secondary = [0., 1., 0.]
    if pole_local is not None:
        projected = list(pole_local)
        projected[axis] = 0.
        secondary, _ = dominant_axis(projected)
    secondary[1] *= -1.
    return primary, secondary


def sdk_relationship(target, attribute, xs, ys):
    """Native linear descriptor uses first positive key, else first nonzero.

    This deliberately describes the selected authored key instead of fitting,
    simplifying or normalizing the entire driven-key curve.
    """
    if not xs or len(xs) != len(ys):
        return None
    base = 0.
    chosen = None
    for index, value in enumerate(xs):
        if abs(value) < .0001:
            base = ys[index]
        if chosen is None and value > .0001:
            chosen = index
    if chosen is None:
        chosen = next((index for index, value in enumerate(xs) if abs(value) > .0001), None)
    if chosen is None:
        return None
    driver = xs[chosen]
    driven = ys[chosen] - base
    return dict(target=target, attribute=attribute, multiplier=driven / driver,
                driverValue=driver, drivenValue=driven)


def attribute_text(value):
    """The native schema stores user-attribute values as MEL scalar strings."""
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, float):
        return format(value, '.6g')
    if isinstance(value, (str, int)):
        return str(value)
    raise ValueError('BodyRig 原版属性导出需要标量值')
