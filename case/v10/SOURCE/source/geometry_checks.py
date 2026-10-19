"""OCC boolean-result classification; empty is not a successful BOP test."""
import math

def check_boolean_result(shape):
    empty=not any(len(getattr(shape,name)) for name in ('Solids','Shells','Wires','Faces','Edges','Vertexes'))
    values=[shape.Volume,shape.Area,shape.Length]
    if not all(math.isfinite(v) for v in values):raise ValueError('Nonfinite shape measure')
    if empty:
        if any(v!=0 for v in values):raise ValueError('Empty topology with nonzero measure')
        if not shape.isNull():
            shape.check(False)
            if not shape.isValid():raise ValueError('Invalid empty topology')
        return 'NOT_APPLICABLE_EMPTY_TOPOLOGY'
    # Nonempty wires/faces/edges with zero volume must still receive a full check.
    shape.check(True)
    if not shape.isValid():raise ValueError('Invalid nonempty topology')
    return 'PASS'
