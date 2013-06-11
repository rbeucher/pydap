"""Basic functions related to the DAP spec."""
import sys
import urllib
import itertools
import operator

import pkg_resources

from pydap.exceptions import ConstraintExpressionError


__dap__ = '2.15'
__version__ = pkg_resources.get_distribution("Pydap").version


START_OF_SEQUENCE = '\x5a\x00\x00\x00'
END_OF_SEQUENCE = '\xa5\x00\x00\x00'
STRING = '|S128'


def quote(name):
    """Return quoted name according to the DAP specification.

        >>> quote("White space")
        'White%20space'

    This function is similar to `urllib.quote`, with the difference that
    periods are also quoted:

        >>> urllib.quote("Period.")
        'Period.'
        >>> quote("Period.")
        'Period%2E'

    """
    safe = '%_!~*\'-"'
    return urllib.quote(name.encode('utf-8'), safe=safe).replace('.', '%2E')


def encode(obj):
    """Return an object encoded to its DAP representation."""
    try:
        return '%.6g' % obj
    except:
        if isinstance(obj, unicode):
            obj = obj.encode('utf-8')
        return '"%s"' % str(obj).replace('"', r'\"')


def fix_slice(slice_, shape):
    """Return a normalized slice.

    This function returns a slice so that it has the same length of `shape`,
    and no negative indexes, if possible.

    This is based on this document:

        http://docs.scipy.org/doc/numpy/reference/arrays.indexing.html

    """
    # convert `slice_` to a tuple
    if not isinstance(slice_, tuple):
        slice_ = (slice_,)

    # expand Ellipsis and make `slice_` at least as long as `shape`
    expand = len(shape) - len(slice_)
    out = []
    for s in slice_:
        if s is Ellipsis:
            out.extend((slice(None),) * (expand+1))
            expand = 0
        else:
            out.append(s)
    slice_ = tuple(out) + (slice(None),) * expand

    out = []
    for s, n in zip(slice_, shape):
        if isinstance(s, int):
            if s < 0:
                s += n
            out.append(s)
        else:
            k = s.step or 1

            i = s.start
            if i is not None and i < 0:
                i += n

            j = s.stop
            if j is not None and j < 0:
                j += n

            out.append(slice(i, j, k))

    return tuple(out)


def combine_slices(slice1, slice2):
    """Return two tuples of slices combined sequentially.

    These two should be equal:

        x[ combine_slices(s1, s2) ] == x[s1][s2]

    """
    out = []
    for exp1, exp2 in itertools.izip_longest(
            slice1, slice2, fillvalue=slice(None)):
        if isinstance(exp1, int):
            exp1 = slice(exp1, exp1+1)
        if isinstance(exp2, int):
            exp2 = slice(exp2, exp2+1)

        start = (exp1.start or 0) + (exp2.start or 0)
        step = (exp1.step or 1) * (exp2.step or 1)

        if exp1.stop is None and exp2.stop is None:
            stop = None
        elif exp1.stop is None:
            stop = (exp1.start or 0) + exp2.stop
        elif exp2.stop is None:
            stop = exp1.stop
        else:
            stop = min(exp1.stop, (exp1.start or 0) + exp2.stop)

        out.append(slice(start, stop, step))
    return tuple(out)


def hyperslab(slice_):
    """Return a DAP representation of a multidimensional slice."""
    if not isinstance(slice_, tuple):
        slice_ = [slice_]
    else:
        slice_ = list(slice_)

    while slice_ and slice_[-1] == slice(None):
        slice_.pop(-1)

    return ''.join('[%s:%s:%s]' % (
        s.start or 0, s.step or 1, (s.stop or sys.maxint)-1) for s in slice_)


def walk(var, type=object):
    """Yield all variables of a given type from a dataset.

    The iterator returns also the parent variable.

    """
    if isinstance(var, type):
        yield var
    for child in var.children():
        for var in walk(child, type):
            yield var


def fix_shorthand(projection, dataset):
    """Fix shorthand notation in the projection.

    Some clients request variables by their name, not by the id. This is called
    the "shorthand notation", and it has to be fixed. This function will return
    a new projection with no shorthand calls.

    """
    out = []
    for var in projection:
        if len(var) == 1 and var[0][0] not in dataset.keys():
            token, slice_ = var.pop(0)
            for child in walk(dataset):
                if token == child.name:
                    if var:
                        raise ConstraintExpressionError(
                            'Ambiguous shorthand notation request: %s' % token)
                    var = [
                        (parent, ()) for parent in child.id.split('.')[:-1]
                    ] + [(token, slice_)]
        out.append(var)
    return out


def get_var(dataset, id_):
    """Given an id, return the corresponding variable from the dataset."""
    tokens = id_.split('.')
    return reduce(operator.getitem, [dataset] + tokens)
