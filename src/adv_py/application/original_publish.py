"""Publish the current source rig, then restore its working scene."""


class PublishOriginalScene:
    def __init__(self, host):
        self.host = host

    def apply(self):
        source = self.host.capture_original_publish()
        if not self.host.confirm_original_publish_animation(source):
            return None
        return self.host.publish_original_scene(source)
