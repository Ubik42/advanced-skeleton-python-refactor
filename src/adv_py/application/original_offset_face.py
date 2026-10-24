"""Operation boundaries for original multi-head Face transplant/update."""
class CreateOriginalOffsetFace:
    def __init__(self, host):
        self.host = host

    def apply(self):
        with self.host.transaction('建立原版 Offset Face 场景'):
            return self.host.create_original_offset_face()


class ImportOriginalOffsetFace:
    def __init__(self, host):
        self.host = host

    def apply(self, file, options):
        with self.host.transaction('导入原版 Offset Face'):
            return self.host.import_original_offset_face(file, options)


class UpdateOriginalOffsetFaces:
    def __init__(self, host):
        self.host = host

    def apply(self):
        rows = self.host.read_original_offset_face_updates()
        if not self.host.confirm_original_offset_face_update(rows):
            return None
        with self.host.transaction('更新原版 Offset Face'):
            return self.host.update_original_offset_faces(rows)
