"""Complementary pitched-tone evidence, not a second trained chord model.

Fits harmonic spectra to CQT magnitudes with nonnegative least squares. The
mid register receives more weight than walking bass; chord/root decisions stay
with the bar decoder and require agreement with BTC. No weights are trained.
"""
import numpy as np
from scipy.optimize import nnls

VERSION='harmonic-pitch-evidence-v1'


def from_cqt(magnitude):
    frequencies=32.70319566257483*2**(np.arange(144)/24)
    notes=np.arange(36,85);dictionary=np.zeros((144,len(notes)))
    for i,midi in enumerate(notes):
        fundamental=440*2**((midi-69)/12)
        for harmonic in range(1,7):
            cents=24*np.log2(frequencies/(fundamental*harmonic))
            dictionary[:,i]+=np.exp(-.5*(cents/.65)**2)/harmonic**1.5
    energy=np.zeros((magnitude.shape[1],12))
    for i,column in enumerate(magnitude.T):
        if column.max()<1e-7:continue
        activation,_=nnls(dictionary,column)
        for k,midi in enumerate(notes):energy[i,midi%12]+=activation[k]*(.25 if midi<48 else 1.)
    return energy
