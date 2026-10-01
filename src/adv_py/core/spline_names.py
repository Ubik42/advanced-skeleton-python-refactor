"""Independent source Spline system names without changing graph topology."""
from dataclasses import fields,is_dataclass,replace
from functools import wraps
import re


def spline_system_valid(name):
    return isinstance(name,str) and (name=='' or bool(re.fullmatch('[A-Za-z][A-Za-z0-9_]*',name)))


def remap_spline_value(value,system,*,canonical=False):
    prefix='AdvPy_Spline_'+system+'_'
    if isinstance(value,str):
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
