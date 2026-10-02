"""Original AutoPlace guide editing and explicit finish action."""


class FinishFitAutoPlace:
    def __init__(self,host):self._host=host

    def apply(self,container='FitSkeleton',*,skin=(),all_objects=()):
        with self._host.transaction('Finish Fit AutoPlace guides'):
            return self._host.finish_fit_auto_place(container,tuple(skin),tuple(all_objects))


class AutoPlaceFit:
    def __init__(self,host):self._host=host

    def apply(self,container='FitSkeleton',*,skin=(),all_objects=(),right_eye=()):
        with self._host.transaction('Fit AutoPlace from source scan phases'):
            return self._host.auto_place_fit(container,tuple(skin),tuple(all_objects),tuple(right_eye))
