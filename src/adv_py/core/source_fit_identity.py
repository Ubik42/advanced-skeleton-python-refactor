"""Resolve authored Fit settings through actual symmetry provenance.

The left output may mirror a right Fit joint or come from an independently
authored _NonSymmetry branch. A Body name alone cannot choose its settings.
"""
from .fit_settings import FitSkeletonValidationError


def source_fit_reference(body_name, instances):
    found = [instance.source_joint for instance in instances if instance.output_name==body_name]
    if len(found)>1:
        raise FitSkeletonValidationError('来源 Body 对应多个 Fit 关节：'+body_name)
    return found[0] if found else None


def source_fit_metadata(body_name, metadata, instances=()):
    reference = source_fit_reference(body_name,instances)
    if reference is not None:
        found = [item for item in metadata if item.joint==reference]
    else:
        source_name = body_name.rsplit('_',1)[0]
        found = [item for item in metadata if item.joint.rsplit('|',1)[-1].rsplit(':',1)[-1]==source_name]
    if len(found)>1:
        raise FitSkeletonValidationError('来源 Fit 设置身份不唯一：'+body_name)
    return found[0] if found else None


def source_fit_build_name(name):
    return name.rsplit(':',1)[-1].removesuffix('_NonSymmetry')
