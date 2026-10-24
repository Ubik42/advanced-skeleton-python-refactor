"""Read the original Poser command strings through Python host operations."""


class EditOriginalPoser:
    def __init__(self, host):
        self.host = host

    def apply(self, text, action='pose', **options):
        with self.host.transaction('原版 Poser：' + action):
            if action == 'pose':
                return self.host.set_original_poser_attributes(text, **options)
            if action == 'stored_keys':
                return self.host.key_original_poser_attributes(text, **options)
            return self.host.original_poser_objects(text, action)
