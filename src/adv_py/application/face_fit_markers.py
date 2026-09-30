"""Original Face fitting marker entry point; one undo transaction."""
class CreateFaceFitMarker:
    def __init__(self,host): self.host=host
    def apply(self,section):
        with self.host.transaction("创建 Face "+section+" Fit"):
            if section=="UpMidLo": return self.host.create_face_up_mid_lo_fit()
            if section=="ForeHead": return self.host.create_original_face_forehead_fit()
            if section in ("Pupil","Iris"): return self.host.create_original_eye_loop_fit(section)
            return self.host.create_face_fit_marker(section)
