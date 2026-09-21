"""Read-only preservation checkpoint preceding staged character rebuild."""
class CaptureBodyCharacterPreservation:
    def __init__(self,host):self._host=host

    def execute(self,*,extensions=()):
        host=self._host
        registration=host.read_character_registration()
        host.preflight_character_keyframe(registration)
        keys=host.capture_character_key_state(registration)
        result=host.capture_character_preservation(registration,tuple(extensions))
        if host.read_character_registration()!=registration or host.capture_character_key_state(registration)!=keys:
            raise RuntimeError('重建数据采集期间角色或动画发生变化')
        return result
