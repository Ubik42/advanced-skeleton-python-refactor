"""Public scripting equivalent of the original asDecomposeOPM procedure."""


class DecomposeOriginalOffsetParentMatrices:
    def __init__(self, host):
        self.host = host

    def apply(self):
        with self.host.transaction('asDecomposeOPM'):
            return self.host.decompose_original_offset_parent_matrices()
