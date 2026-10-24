"""The weight array arithmetic embedded in asLockedAwareCopyWeights."""


def original_locked_copy_weights(original, copied, influence_count, locked_indices):
    if type(influence_count) is not int or influence_count < 1:
        raise ValueError('Skin 影响数量无效')
    original, copied = tuple(original), tuple(copied)
    locked = tuple(locked_indices)
    if (len(original) != len(copied) or len(copied) % influence_count
            or any(type(index) is not int or not 0 <= index < influence_count for index in locked)
            or len(set(locked)) != len(locked)):
        raise ValueError('Skin 权重数组或锁定影响索引不完整')
    result = list(copied)
    for offset in range(0, len(copied), influence_count):
        total_locked = sum(original[offset+index] for index in locked)
        if total_locked >= 1.0:
            result[offset:offset+influence_count] = original[offset:offset+influence_count]
            continue
        total_unlocked_copied = sum(copied[offset+index]
            for index in range(influence_count) if index not in locked)
        for index in locked:
            result[offset+index] = original[offset+index]
        remaining = 1.0-total_locked
        if total_unlocked_copied > 0.0:
            scalar = remaining/total_unlocked_copied
            for index in range(influence_count):
                if index not in locked:
                    result[offset+index] *= scalar
        elif influence_count > len(locked):
            first_unlocked = next(index for index in range(influence_count) if index not in locked)
            result[offset+first_unlocked] = remaining
    return tuple(result)
