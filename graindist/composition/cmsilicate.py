import numpy as np
from scipy.interpolate import interp1d

from newdust import constants as c
from newdust.graindist.composition import _find_cmfile

__all__ = ['CmSilicate']

ALLOWED_UNITS = ['kev', 'angs']
RHO_SIL       = 3.8  # g cm^-3

class CmSilicate(object):
    """
    | **ATTRIBUTES**
    | cmtype : 'Silicate'
    | citation : A string containing citation to the original work
    | interps : Tuple containing to scipy.interp1d objects (rp, ip)
    |
    | **FUNCTIONS**
    | rp(lam, unit='kev')  : returns real part (unit='kev'|'angs')
    | ip(lam, unit='kev')  : returns real part (unit='kev'|'angs')
    | plot(lam=None, unit='kev') : Plots Re(m-1) and Im(m)
    |   if lam is *None*, plots the original interp objects
    |   otherwise, plots with user defined wavelength (lam)
    """
    def __init__(self, rho=RHO_SIL):
        self.cmtype = 'Silicate'
        self.rho    = rho
        self.citation = "Using optical constants for astrosilicate,\nDraine, B. T. 2003, ApJ, 598, 1026\nhttp://adsabs.harvard.edu/abs/2003ApJ...598.1026D"

        D03file = _find_cmfile('CM_D03.pysav')
        D03vals = c.restore(D03file)      # look up file

        lamvals = D03vals['Sil_lam']
        revals  = D03vals['Sil_re']
        imvals  = D03vals['Sil_im']

        lamEvals = c.hc / c.micron2cm / lamvals  # keV
        rp  = interp1d(lamEvals, revals)
        ip  = interp1d(lamEvals, imvals)
        self.interps = (rp, ip)

    def rp(self, lam, unit='kev'):
        assert unit in ALLOWED_UNITS
        if unit == 'kev':
            E = lam
        if unit == 'angs':
            E = c.hc_angs / lam
        igood = (E >= self.interps[0].x[0]) & (E <= self.interps[0].x[-1])
        result = np.zeros(len(E))+1.0
        result[igood] = self.interps[0](E[igood])
        return result

    def ip(self, lam, unit='kev'):
        assert unit in ALLOWED_UNITS
        if unit == 'kev':
            E = lam
        if unit == 'angs':
            E = c.hc_angs / lam
        igood = (E >= self.interps[1].x[0]) & (E <= self.interps[1].x[-1])
        result = np.zeros(len(E))
        result[igood] = self.interps[1](E[igood])
        return result

    def plot(self, ax, lam=None, unit='kev', rppart=True, impart=True):
        if lam is None:
            rp_m1 = np.abs(self.interps[0].y - 1.0)
            ip = self.interps[1].y
            x  = self.interps[0].x
            xlabel = "Energy (keV)"
        else:
            rp_m1 = np.abs(self.rp(lam, unit=unit)-1.0)
            ip = self.ip(lam, unit=unit)
            x  = lam
            assert unit in ALLOWED_UNITS
            if unit == 'kev': xlabel = "Energy (keV)"
            if unit == 'angs': xlabel = "Wavelength (Angstroms)"
        if rppart:
            ax.plot(x, rp_m1, ls='-', label='|Re(m-1)|')
        if impart:
            ax.plot(x, ip, ls='--', label='Im(m)')
        ax.set_xlabel(xlabel)
        ax.legend()