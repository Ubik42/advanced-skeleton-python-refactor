"""Independent source Spline system names without changing graph topology."""
from dataclasses import fields,is_dataclass,replace
from functools import wraps
from enum import Enum
import re


def spline_system_valid(name):
    return isinstance(name,str) and (name=='' or bool(re.fullmatch('[A-Za-z][A-Za-z0-9_]*',name)))


def remap_spline_value(value,system,*,canonical=False):
    prefix='AdvPy_Spline_'+system+'_'
    # Role/side enums inherit str, but replacing names must not turn them
    # into plain strings. Each scoped plan still carries typed identities.
    if isinstance(value,Enum):return value
    if isinstance(value,str):
        # asParentConstraint inserts MM/PM before the final underscore token.
        # Local Spline helpers are localized before planning; map these native
        # derived names to the same names the physical driven node implies.
        for kind in ('MM', 'PM', 'DM'):
            local = 'AdvPy' + kind + '_SplineChestSpace'
            scoped = 'AdvPy_Spline_' + system + kind + '_ChestSpace'
            value = value.replace(scoped, local) if canonical else value.replace(local, scoped)
        return value.replace(prefix,'AdvPy_Spline') if canonical else re.sub(
            r'AdvPy_Spline(?=[A-Z])',prefix,value)
    if is_dataclass(value):
        return replace(value,**{field.name:remap_spline_value(getattr(value,field.name),system,
                         canonical=canonical) for field in fields(value)})
    if isinstance(value,dict):
        return {key:remap_spline_value(item,system,canonical=canonical) for key,item in value.items()}
    if isinstance(value,(tuple,list)):
        return type(value)(remap_spline_value(item,system,canonical=canonical) for item in value)
    return value


def scope_spline_plan(plan,system):
    if not spline_system_valid(system):
        raise ValueError('Spline 系统名称无效')
    if plan.system_name:
        plan=replace(remap_spline_value(plan,plan.system_name,canonical=True),system_name='')
    return replace(remap_spline_value(plan,system),system_name=system) if system else plan


def scoped_spline_property(function):
    @wraps(function)
    def get(plan):
        if not plan.system_name:
            return function(plan)
        local=scope_spline_plan(plan,'')
        return remap_spline_value(function(local),plan.system_name)
    return property(get)


def scoped_spline_method(function):
    @wraps(function)
    def call(plan,*args,**kwargs):
        if not plan.system_name:
            return function(plan,*args,**kwargs)
        local=scope_spline_plan(plan,'')
        return remap_spline_value(function(local,*args,**kwargs),plan.system_name)
    return call
