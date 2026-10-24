"""Original clipboard transfer keeps native Maya curves and merge behavior."""


class TransferOriginalControlClipboard:
    def __init__(self, host):
        self.host = host

    def copy(self, animation=False, **options):
        with self.host.transaction('复制原版动画' if animation else '复制原版姿态'):
            return self.host.copy_original_control_clipboard(animation, **options)

    def paste(self, animation=False, **options):
        with self.host.transaction('粘贴原版动画' if animation else '粘贴原版姿态'):
            return self.host.paste_original_control_clipboard(animation, **options)
