"""One Maya host for registered cross-spine animation and Skin migration."""
from .maya_body import MayaBodyBuildHost
from .maya_face import MayaFaceHost
from .maya_mocap_control import MayaMocapControlHost
from .maya_spine_skin_handoff import MayaSpineSkinHandoffHost


class MayaCharacterSpineMigrationHost(MayaMocapControlHost, MayaFaceHost):
    def read_source_character_registration(self, namespace):
        return MayaBodyBuildHost(namespace=namespace).read_character_registration()


class MayaOriginalSkinSpineMigrationHost(MayaMocapControlHost):
    """One transaction boundary for original Skin and target FK controls."""

    def original_skin_handoff_host(self):
        return MayaSpineSkinHandoffHost()

    def mark_original_skin_mutation(self):
        self._require_transaction()
        self._transaction_changed = True
