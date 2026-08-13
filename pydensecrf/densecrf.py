import numpy as np


DIAG_KERNEL = 0
NO_NORMALIZATION = 0


class DenseCRF2D:
    def __init__(self, width, height, n_classes):
        self.width = width
        self.height = height
        self.n_classes = n_classes
        self.unary = None

    def setUnaryEnergy(self, unary):
        self.unary = np.asarray(unary, dtype=np.float32)

    def addPairwiseGaussian(self, *args, **kwargs):
        return None

    def addPairwiseBilateral(self, *args, **kwargs):
        return None

    def inference(self, iterations):
        if self.unary is None:
            q = np.zeros((self.n_classes, self.width * self.height), dtype=np.float32)
            q[0, :] = 1.0
            return q
        scores = -self.unary
        scores -= scores.max(axis=0, keepdims=True)
        exp = np.exp(scores)
        denom = exp.sum(axis=0, keepdims=True)
        denom[denom == 0] = 1.0
        return exp / denom
