"""Source Anim/Bake commands; no detached pose-sampling replacement."""


class BakeOriginalControlAnimation:
    def __init__(self, host):
        self.host = host

    def systems(self):
        return self.host.original_animation_bake_systems()

    def execute(self, limbs, mode, *, ui_name='', **options):
        with self.host.transaction('原版动画烘焙：' + mode.upper()):
            return self.host.bake_original_fkik_animation(limbs, mode, ui_name=ui_name, **options)

    def move_to_extra(self, *, ui_name='', **state):
        with self.host.transaction('原版动画：Controls to ExtraControls'):
            return self.host.move_original_animation_to_extra(ui_name=ui_name, **state)

    def bake_extra(self, *, ui_name='', **state):
        with self.host.transaction('原版动画：ExtraControls to Controls'):
            return self.host.bake_original_extra_animation(ui_name=ui_name, **state)

    def bake_quick_ik(self, *, ui_name='', **state):
        with self.host.transaction('原版动画：QuickIK to FKControls'):
            return self.host.bake_original_quick_ik_animation(ui_name=ui_name, **state)
