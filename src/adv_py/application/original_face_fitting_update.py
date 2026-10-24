"""One native confirmation and one encompassing Face Fitting update undo."""


class UpdateOriginalFaceFitting:
    def __init__(self, host):
        self.host = host

    def apply(self):
        if not self.host.confirm_original_face_fitting_update():
            return None
        with self.host.transaction('Face Fitting Update'):
            return self.host.update_original_face_fitting()
