import numpy as np
from scipy.integrate import trapz

import pytest

from newdust import constants as c
from newdust import graindist
from newdust import extinction
from . import percent_diff

NE, NA, NTH = 2, 20, 1000
LAMVALS = np.linspace(1000.,5000.,NE)  # angs
AVALS   = np.linspace(0.1, 0.5, NA)    # um

THETA    = np.logspace(-10.0, np.log10(np.pi), NTH)  # 0->pi scattering angles (rad)
ASEC2RAD = (2.0 * np.pi) / (360.0 * 60. * 60.)     # rad / arcsec
TH_asec  = THETA / ASEC2RAD  # rad * (arcsec/rad)

MRN_SIL = graindist.make_GrainDist('Powerlaw','Silicate')
MRN_DRU = graindist.make_GrainDist('Powerlaw','Drude')
EXP_SIL = graindist.make_GrainDist('ExpCutoff','Silicate')
GRAIN   = graindist.make_GrainDist('Grain','Drude')

RG  = extinction.scatmodels.RGscat()
MIE = extinction.scatmodels.Mie()

@pytest.mark.parametrize(('gd','sm'),
                         [(MRN_SIL, RG), (MRN_SIL, MIE),
                          (MRN_DRU, RG), (MRN_DRU, MIE),
                          (EXP_SIL, RG), (EXP_SIL, MIE),
                          (GRAIN, RG), (GRAIN, MIE)])
def test_calculations(gd, sm):
    test = extinction.Extinction(sm)
    test.calculate(gd, LAMVALS, unit='angs', theta=TH_asec)
    assert np.shape(test.tau_ext) == (NE,)
    assert np.shape(test.tau_sca) == (NE,)
    assert np.shape(test.tau_abs) == (NE,)
    assert all(percent_diff(test.tau_ext, test.tau_abs + test.tau_sca) <= 0.01)
