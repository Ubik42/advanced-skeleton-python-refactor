"""Enable explicit spline FK position and cross-section animation channels."""


class EnableBodyCharacterSplineAnimation:
    def __init__(self, host):
        self._host = host

    def apply(self):
        host = self._host
        original = host.read_character_registration()
        with host.transaction('Enable spline FK animation matching'):
            if host.read_character_registration() != original:
                raise RuntimeError('曲线脊柱登记在扩展前发生变化')
            result = host.install_character_spline_animation(original)
            if host.read_character_registration() != result:
                raise RuntimeError('曲线脊柱扩展登记读回不一致')
        return result
