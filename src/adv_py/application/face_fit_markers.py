"""Original Face fitting marker entry point; one undo transaction."""
class CreateFaceFitMarker:
    def __init__(self,host): self.host=host
    def apply(self,section):
        with self.host.transaction("创建 Face "+section+" Fit"):
            if section=="UpMidLo": return self.host.create_face_up_mid_lo_fit()
            return self.host.create_face_fit_marker(section)
