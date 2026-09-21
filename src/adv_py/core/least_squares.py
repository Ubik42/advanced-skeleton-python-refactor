"""Small bounded damped least-squares solve without a numerical runtime dependency."""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class LeastSquaresResult:
    parameters: tuple[float, ...]
    residual: tuple[float, ...]
    iterations: int
    evaluations: int
    converged: bool


def _linear(matrix, values):
    rows = [list(row)+[value] for row,value in zip(matrix,values)]
    for column in range(len(rows)):
        pivot = max(range(column,len(rows)),key=lambda index:abs(rows[index][column]))
        rows[column],rows[pivot] = rows[pivot],rows[column]
        divisor = rows[column][column]
        if abs(divisor)<1e-18:
            raise ValueError('Least-squares normal matrix is singular')
        rows[column] = [value/divisor for value in rows[column]]
        for index in range(len(rows)):
            if index==column:continue
            factor = rows[index][column]
            rows[index] = [a-factor*b for a,b in zip(rows[index],rows[column])]
    return tuple(row[-1] for row in rows)


def least_squares(evaluate, initial, *, bounds=None, tolerance=1e-7, max_iterations=60, step=1e-4):
    """Minimize a residual vector; always leave evaluate at the returned parameters.

    Parameters should use comparable units. Bounds are optional (lower, upper)
    pairs. A non-converged result retains the best accepted candidate, allowing
    the caller to report residuals and roll back the owning scene transaction.
    """
    initial = tuple(float(value) for value in initial)
    if not initial or not all(isfinite(value) for value in initial):
        raise ValueError('Finite initial parameters are required')
    if not isfinite(tolerance) or tolerance<=0 or not isfinite(step) or step<=0 or type(max_iterations) is not int or max_iterations<1:
        raise ValueError('Invalid least-squares iteration limits')
    bounds = tuple(bounds) if bounds is not None else ((None,None),)*len(initial)
    if len(bounds)!=len(initial):raise ValueError('Bounds dimension mismatch')
    for value,(low,high) in zip(initial,bounds):
        if ((low is not None and (not isfinite(low) or value<low))
                or (high is not None and (not isfinite(high) or value>high))
                or (low is not None and high is not None and low>=high)):
            raise ValueError('Invalid parameter bounds')
    evaluations = 0
    dimension = None
    def sample(parameters):
        nonlocal evaluations,dimension
        values = tuple(float(value) for value in evaluate(tuple(parameters)))
        evaluations += 1
        if not values or not all(isfinite(value) for value in values):raise ValueError('Nonfinite fit residual')
        if dimension is not None and len(values)!=dimension:raise ValueError('Residual dimension changed')
        dimension = len(values)
        return values
    def clamp(value,index):
        low,high = bounds[index]
        return max(low if low is not None else value,min(high if high is not None else value,value))
    parameters = initial
    residual = sample(parameters)
    damping = 1e-3
    iteration = 0
    for iteration in range(max_iterations):
        if max(abs(value) for value in residual)<=tolerance:break
        columns = []
        for index,value in enumerate(parameters):
            delta = step*max(1.,abs(value))
            lower,upper = list(parameters),list(parameters)
            lower[index],upper[index] = clamp(value-delta,index),clamp(value+delta,index)
            left,right = sample(lower),sample(upper)
            columns.append(tuple((b-a)/(upper[index]-lower[index]) for a,b in zip(left,right)))
        normal = tuple(tuple(sum(a*b for a,b in zip(left,right)) for right in columns) for left in columns)
        gradient = tuple(sum(a*b for a,b in zip(column,residual)) for column in columns)
        cost = sum(value*value for value in residual)
        accepted = False
        for trial in range(10):
            system = tuple(tuple(value+(damping*max(1.,normal[i][i]) if i==j else 0.)
                                 for j,value in enumerate(row)) for i,row in enumerate(normal))
            delta = _linear(system,tuple(-value for value in gradient))
            candidate = tuple(clamp(value+change,index) for index,(value,change) in enumerate(zip(parameters,delta)))
            candidate_residual = sample(candidate)
            if sum(value*value for value in candidate_residual)<cost:
                parameters,residual = candidate,candidate_residual
                damping = max(1e-12,damping/3.)
                accepted = True
                break
            damping *= 10.
        if not accepted:break
    residual = sample(parameters)
    return LeastSquaresResult(parameters,residual,iteration+1,evaluations,
                              max(abs(value) for value in residual)<=tolerance)
