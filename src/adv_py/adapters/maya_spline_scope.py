"""Map only Spline node arguments at the existing Maya command boundary."""
from contextlib import contextmanager

from adv_py.core.spline_names import remap_spline_value,scope_spline_plan
from .maya_namespace import _NODE_ARGS,_NODE_RESULTS


class SplineCommands:
    def __init__(self,commands,system,canonical_results=True):
        self.commands=commands
        self.system=system
        self.canonical_results=canonical_results

    @property
    def raw(self):
        # Extra/Sub CV edits use raw commands. Preserve our system mapping
        # while bypassing only the character namespace layer as requested.
        return SplineCommands(getattr(self.commands,'raw',self.commands),self.system,self.canonical_results)

    def __getattr__(self,name):
        command=getattr(self.commands,name)
        def call(*args,**kwargs):
            args=list(args)
            kwargs=dict(kwargs)
            def address(value):
                return remap_spline_value(value,self.system)
            if name=='setAttr':
                if args:
                    args[0]=address(args[0])
            elif name not in ('createNode','shadingNode','attributeQuery') and name in _NODE_ARGS|{'select','listAttr'}:
                args=[address(value) for value in args]
            for flag in ('name','n','parent','p','node','startJoint','sj','endEffector','ee','worldUpObject','curve'):
                if name=='addAttr' and flag in ('parent','p'):
                    continue
                if flag in kwargs and isinstance(kwargs[flag],str):
                    kwargs[flag]=address(kwargs[flag])
            result=command(*args,**kwargs)
            query=kwargs.get('query',kwargs.get('q',False))
            node_result=name in _NODE_RESULTS or name=='ls' or name=='connectionInfo' and any(
                kwargs.get(flag) for flag in ('sourceFromDestination','sfd','destinationFromSource','dfs'))
            if query and any(kwargs.get(flag) for flag in ('weightAliasList','wal')):
                node_result=False
            return remap_spline_value(result,self.system,canonical=True) if node_result and self.canonical_results else result
        return call


@contextmanager
def spline_scope(host,plan,*,localize=True):
    previous=host._cmds
    if not plan.system_name:
        yield plan
        return
    host._cmds=SplineCommands(previous,plan.system_name,localize)
    try:
        yield scope_spline_plan(plan,'') if localize else plan
    finally:
        host._cmds=previous
