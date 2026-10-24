"""asSetFixedWrapOptions, ADV 6.925 MEL 8203–8209."""


def set_fixed_wrap_options(commands):
    raw=getattr(commands,'raw',commands)
    for name,value in (('autoWeightThreshold',1),('exclusiveBind',0),('renderInfl',1)):
        raw.optionVar(intValue=(name,value))
    raw.optionVar(stringValue=('falloffMode','volume'))
