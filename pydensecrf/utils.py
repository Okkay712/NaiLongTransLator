import numpy as np


def unary_from_softmax(sm, scale=None, clip=1e-5):
    sm = np.asarray(sm, dtype=np.float32)
    sm = np.clip(sm, clip, 1.0)
    return -np.log(sm)


def compute_unary(*args, **kwargs):
    if args:
        return unary_from_softmax(args[0])
    raise TypeError("compute_unary requires a softmax array")
