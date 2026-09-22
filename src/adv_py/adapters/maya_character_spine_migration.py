"""One Maya host for registered cross-spine animation and Skin migration."""
from .maya_body import MayaBodyBuildHost
from .maya_face import MayaFaceHost
from .maya_mocap_control import MayaMocapControlHost


class MayaCharacterSpineMigrationHost(MayaMocapControlHost, MayaFaceHost):
    def read_source_character_registration(self, namespace):
        return MayaBodyBuildHost(namespace=namespace).read_character_registration()
