import numpy as np
from scipy.integrate import trapz
from astropy.io import fits

from . import graindist
from . import scatteringmodel

__all__ = ['SingleGrainPop','GrainPop','make_MRN','make_MRN_drude']

MD_DEFAULT    = 1.e-4  # g cm^-2
AMIN, AMAX, P = 0.005, 0.3, 3.5  # um, um, unitless
RHO_AVG       = 3.0  # g cm^-3

# Make this a subclass of GrainDist at some point
class SingleGrainPop(graindist.GrainDist):
    """
    SingleGrainPop unifies the grain size distribution (its parent class) 
    with extinction model calculations. It provides attributes and convenience
    functions for easy access to frequently needed information. Only one dust 
    composition can be modeled at a time.

    Attributes
    ----------
    In addition to those supplied by newdust.graindist.GraindDist

    lam : astropy.units.Quantity : wavelength or energy used for the extinction computation

    tau_sca : numpy.ndarray float : scattering optical depth for this grain population

    tau_abs : numpy.ndarray float : absorption optical depth for this grain population

    tau_ext : numpy.ndarray float : extinction (scattering + absorption) optical depth 
    for this grain population

    diff : numpy.ndarray float : [cm^2 ster^-1] differential scattering cross-section 
    as a function of wavelength/energy, grain size, and angle (NE x NA x NTH)

    int_diff : numpy.ndarray float : [ster^-1] differential cross-section integrated 
    over grain size, effectively $d\tau / d\Omega$
    """
    def __init__(self, dtype, cmtype, stype, shape='Sphere', md=MD_DEFAULT, scatm_from_file=None, **kwargs):
        """
        Inputs
        ------

        dtype : string ('Grain', 'Powerlaw', 'ExpCutoff') or 
        newdust.graindist.sizedist object defining the grain radius distribution

        cmtype : string ('Drude', 'Silicate', 'Graphite') or
        newdust.graindist.composition object defining the optical constants and compound density

        stype : string ('Mie' or 'RG') : defines what extinction model calculator to use. If an
        input for `scatm_from_file` is provided, then the `stype` input will be ignored.

        shape : string ('Sphere' is the only option), otherwise could be used to define a custom shape

        md : float : dust mass column [g cm^-2]
        
        **kwargs : extra inputs passed to GrainDist.__init__
        """
        graindist.GrainDist.__init__(self, dtype, cmtype, shape=shape, md=md, **kwargs)

        self.lam      = None  # NE
        self.lam_unit = None  # string
        self.tau_sca  = None  # NE
        self.tau_abs  = None  # NE
        self.tau_ext  = None  # NE
        self.diff     = None  # NE x NA x NTH [cm^2 ster^-1]
        self.int_diff = None  # NE x NTH [ster^-1], differential xsect integrated over grain size

        # Handling scattering model FITS input, if requested
        if scatm_from_file is not None:
            self.scatm = scatteringmodel.ScatModel(from_file=scatm_from_file)
            assert isinstance(stype, str)
            self.scatm.stype = stype
            self.lam = self.scatm.pars['lam']
            self.lam_unit = self.scatm.pars['unit']
            self._calculate_tau()
        # Otherwise choose from existing (or custom) scattering calculators
        elif isinstance(stype, str):
            self._assign_scatm_from_string(stype)
        else:
            self.scatm = stype

    def _assign_scatm_from_string(self, stype):
        assert stype in ['RG', 'Mie']
        if stype == 'RG':
            self.scatm = scatteringmodel.RGscattering()
        if stype == 'Mie':
            self.scatm = scatteringmodel.Mie()

    # Run scattering model calculation, then compute optical depths
    def calculate_ext(self, lam, theta=0.0, **kwargs):
        """
        Calculate the extinction model.

        lam : astropy.units.Quantity -or- numpy.ndarray
            Wavelength or energy values for calculating the cross-sections;
            if no units specified, defaults to keV
        
        theta : astropy.units.Quantity -or- numpy.ndarray -or- float
            Scattering angles for computing the differential scattering cross-section;
            if no units specified, defaults to radian
        
        **kwargs passed to self.scatm.calculate
        """
        self.scatm.calculate(lam, self.a, self.comp, theta=theta, **kwargs)
        self.lam      = self.scatm.pars['lam']
        self._calculate_tau()

    # Compute optical depths only
    def _calculate_tau(self):
        NE, NA, NTH = np.shape(self.scatm.diff)
        # Recall cgeo is cm^2 and ndens is cm^-2 um^-1
        # In single size grain case
        if len(self.a) == 1:
            self.tau_ext = self.ndens * self.scatm.qext[:,0] * self.cgeo
            self.tau_sca = self.ndens * self.scatm.qsca[:,0] * self.cgeo
            self.tau_abs = self.ndens * self.scatm.qabs[:,0] * self.cgeo
        # Otherwise, integrate over grain size (axis=1)
        else:
            geo_fac = self.ndens * self.cgeo  # array of length NA, unit is um^-1
            geo_2d  = np.repeat(geo_fac.reshape(1, NA), NE, axis=0)  # NE x NA
            a_um = self.a.to('micron').value
            self.tau_ext = trapz(geo_2d * self.scatm.qext, a_um, axis=1)
            self.tau_sca = trapz(geo_2d * self.scatm.qsca, a_um, axis=1)
            self.tau_abs = trapz(geo_2d * self.scatm.qabs, a_um, axis=1)

        # Recall that scatm.diff is diffrential scattering efficiency [ster^-1]
        # diff shape is NE x NA x NTH
        area_2d = np.repeat(self.cgeo.reshape(1, NA), NE, axis=0) # cm^2
        area_3d = np.repeat(area_2d.reshape(NE, NA, 1), NTH, axis=2)
        self.diff = self.scatm.diff * area_3d # NE x NA x NTH, [cm^2 ster^-1]

        # If a single grain size, operate in 2D (shape: NE x NTH)
        if np.size(self.a) == 1:
            int_diff = np.sum(self.scatm.diff * self.cgeo[0] * self.ndens[0], axis=1)
        # Otherwise, integrate differential scattering cross-section over NA
        else:
            a_um = self.a.to('micron').value
            agrid        = np.repeat(
                np.repeat(a_um.reshape(1, NA, 1), NE, axis=0),
                NTH, axis=2)
            ndgrid       = np.repeat(
                np.repeat(self.ndens.reshape(1, NA, 1), NE, axis=0),
                NTH, axis=2)
            int_diff = trapz(self.scatm.diff * area_3d * ndgrid, agrid, axis=1)

        self.int_diff = int_diff  # NE x NTH, [ster^-1]

    # Plot information about the grain size distribution
    def plot_sdist(self, ax, **kwargs):
        """
        Plot information about the grain size distribution.
        (Calls GrainDist.plot)

        Inputs
        ------

        ax : matplotlib.pyplot.axes object
        """
        self.plot(ax, **kwargs)

    # Plot the extinction properties
    def plot_ext(self, ax, keyword, unit=None, **kwargs):
        """
        Plot  the extinction properties of the grain population.

        Inputs
        ------

        ax : matplotlib.pyplot.axes object

        keyword : string ('ext', 'sca', 'abs', 'all') : extinction value(s) to plot

        unit : string parsable by astropy.units : unit to use for the x-axis values

        **kwargs passed to ax.legend()
        """
        assert keyword in ['ext','sca','abs','all']
        try:
            assert self.lam is not None
        except:
            print("Need to run calculate_ext")
            pass

        # Handle units on the wavelength/energy scale
        xval = self.lam.value
        xunit = self.lam.unit.to_string()
        if unit is not None:
            xval = self.lam.to(unit, equivalencies=u.spectral()).value
            xunit = unit

        if keyword == 'ext':
            ax.plot(xval, self.tau_ext, **kwargs)
            ax.set_xlabel(xunit)
            ax.set_ylabel(r"$\tau_{ext}$")
        if keyword == 'sca':
            ax.plot(xval, self.tau_sca, **kwargs)
            ax.set_xlabel(xunit)
            ax.set_ylabel(r"$\tau_{sca}$")
        if keyword == 'abs':
            ax.plot(xval, self.tau_abs, **kwargs)
            ax.set_xlabel(xunit)
            ax.set_ylabel(r"$\tau_{abs}$")
        if keyword == 'all':
            ax.plot(xval, self.tau_ext, 'k-', lw=2, label='Extinction')
            ax.plot(xval, self.tau_sca, 'r--', label='Scattering')
            ax.plot(xval, self.tau_abs, 'r:', label='Absorption')
            ax.set_xlabel(xunit)
            ax.set_ylabel(r"$\tau$")
            ax.legend(**kwargs)

    # Printing information
    def info(self):
        """
        Print information about this grain population
        """
        print("Size distribution: %s" % self.size.dtype)
        print("Extinction calculated with: %s" % self.scatm.stype)
        print("Grain composition: %s" % self.comp.cmtype)
        print("rho = %.2f g cm^-3, M_d = %.2e g cm^-2" % (self.rho, self.md))

    # Write an extinction table
    def write_extinction_table(self, outfile, **kwargs):
        """
        Write the contents of the extinction calculation to a FITS file. 
        (Runs ScatteringModel.write_table)

        Inputs
        ------

        outfile : string : Name of file to write

        **kwargs passed to self.scatm.write_table
        """
        self.scatm.write_table(outfile, **kwargs)
        return

class GrainPop(object):
    """
    | A collection of dust grain distributions (SingeGrainPop).
    | Can add a string describing this Grain population using the `description` keyword
    |
    | **ATTRIBUTES**
    | keys     : A list of keys corresponding to each SingleGrainPop (default: list of integers starting with 0)
    | gpoplist : A list of SingleGrainPop objects
    | description : A string describing this collection
    | lam      : The energy / wavelength used for calculating extinction
    | lam_unit : The unit for energy ('kev') or wavelength ('angs') used for calculating extinction
    |
    | *properties*
    | tau_ext : Total extinction optical depth as a function of wavelength / energy
    | tau_sca : Total scattering optical depth as a function of wavelength / energy
    | tau_abs : Total absorption optical depth as a function of wavelength / energy
    |
    | *functions*
    | __getitem__(key) will return the SingleGrainPop indexed by ``key``
    | calculate_ext(lam, unit='kev', **kwargs) runs the extinction calculation on the wavelength grid specified by lam and unit
    | plot_ext(ax, keyword, **kwargs) plots the extinction properties (see *astrodust.extinction*)
    |   - ``keyword`` options are "ext", "sca", "abs", "all"
    | info(key=None) prints information about the SingleGrainPop indexed by ``key``
    |   - if ``key`` is *None*, information about every grain population will be printed to screen
    """
    def __init__(self, gpoplist, keys=None, description='Custom_GrainPopDict'):
        assert isinstance(gpoplist, list)
        if keys is None:
            self.keys = list(range(len(gpoplist)))
        else:
            self.keys = keys
        self.description = description
        self.gpoplist    = gpoplist
        for k in self.keys:
            i = self.keys.index(k)
            self.gpoplist[i].description = str(self.keys[i])
        self.lam = None
        self.lam_unit = None

    def calculate_ext(self, lam, unit='kev', **kwargs):
        for gp in self.gpoplist:
            gp.calculate_ext(lam, unit=unit, **kwargs)
        self.lam = lam
        self.lam_unit = unit

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.gpoplist[key]
        else:
            assert key in self.keys
            k = self.keys.index(key)
            return self.gpoplist[k]

    @property
    def md(self):
        result = 0.0
        for gp in self.gpoplist:
            result += gp.md
        return result

    @property
    def tau_ext(self):
        result = 0.0
        if self.lam is None:
            print("ERROR: Extinction properties need to be calculated")
        else:
            for gp in self.gpoplist:
                result += gp.tau_ext
        return result

    @property
    def tau_sca(self):
        result = 0.0
        if self.lam is None:
            print("ERROR: Extinction properties need to be calculated")
        else:
            for gp in self.gpoplist:
                result += gp.tau_sca
        return result

    @property
    def tau_abs(self):
        result = 0.0
        if self.lam is None:
            print("ERROR: Extinction properties need to be calculated")
        else:
            for gp in self.gpoplist:
                result += gp.tau_abs
        return result

    def plot_ext(self, ax, keyword, **kwargs):
        assert keyword in ['all','ext','sca','abs']
        if keyword == 'ext':
            ax.plot(self.lam, self.tau_ext, **kwargs)
            ax.set_xlabel(UNIT_LABELS[self.lam_unit])
            ax.set_ylabel(r"$\tau_{ext}$")
        if keyword == 'sca':
            ax.plot(self.lam, self.tau_sca, **kwargs)
            ax.set_xlabel(UNIT_LABELS[self.lam_unit])
            ax.set_ylabel(r"$\tau_{sca}$")
        if keyword == 'abs':
            ax.plot(self.lam, self.tau_abs, **kwargs)
            ax.set_xlabel(UNIT_LABELS[self.lam_unit])
            ax.set_ylabel(r"$\tau_{abs}$")
        if keyword == 'all':
            ax.plot(self.lam, self.tau_ext, 'k-', lw=2, label='Extinction')
            ax.plot(self.lam, self.tau_sca, 'r--', label='Scattering')
            ax.plot(self.lam, self.tau_abs, 'r:', label='Absorption')
            ax.set_xlabel(UNIT_LABELS[self.lam_unit])
            ax.set_ylabel(r"$\tau$")
            ax.set_title(self.description)
            ax.legend(**kwargs)

    def info(self, key=None):
        if key is None:
            print("General information for %s dust grain population" % self.description)
            for gp in self.gpoplist:
                print("---")
                gp.info()
        else:
            assert key in self.keys
            self[key].info()


#---------- Basic helper functions for fast production of GrainPop objects

def make_MRN(amin=AMIN, amax=AMAX, p=P, md=MD_DEFAULT, fsil=0.6, **kwargs):
    """
    | Returns a GrainPop describing an MRN dust grain size distribution, which is a mixture of silicate and graphite grains.
    | Applies the 1/3 parallel, 2/3 perpendicular assumption of graphite grain orientations.
    |
    | **INPUTS**
    | amin : minimum grain size in microns
    | amax : maximum grain size in microns
    | p    : power law slope for grain size distribution
    | md   : dust mass column [g cm^-2]
    | fsil : fraction of dust mass in silicate grains
    """
    assert isinstance(fsil, float)
    assert fsil >= 0.0 and fsil <= 1.0
    md_sil  = fsil * md
    # Graphite grain assumption: 1/3 parallel and 2/3 perpendicular
    md_gra_para = (1.0 - fsil) * md * (1.0/3.0)
    md_gra_perp = (1.0 - fsil) * md * (2.0/3.0)

    pl_sil  = graindist.sizedist.Powerlaw(amin=amin, amax=amax, p=p, **kwargs)
    pl_gra  = graindist.sizedist.Powerlaw(amin=amin, amax=amax, p=p, **kwargs)

    sil    = graindist.composition.CmSilicate()
    gra_ll = graindist.composition.CmGraphite(orient='para')
    gra_T  = graindist.composition.CmGraphite(orient='perp')

    mrn_sil = SingleGrainPop(pl_sil, sil, 'Mie', md=md_sil)
    mrn_gra_para = SingleGrainPop(pl_gra, gra_ll, 'Mie', md=md_gra_para)
    mrn_gra_perp = SingleGrainPop(pl_gra, gra_T, 'Mie', md=md_gra_perp)

    gplist = [mrn_sil, mrn_gra_para, mrn_gra_perp]
    keys   = ['sil','gra_para','gra_perp']
    return GrainPop(gplist, keys=keys, description='MRN')

def make_MRN_drude(amin=AMIN, amax=AMAX, p=P, rho=RHO_AVG, md=MD_DEFAULT, **kwargs):
    """
    | Returns a GrainPop describing an MRN dust grain size distribution, and uses the Drude approximation,
    | which approximates the dust grain as a sphere of free electrons
    |
    | **INPUTS**
    | amin : minimum grain size in microns
    | amax : maximum grain size in microns
    | p    : power law slope for grain size distribution
    | rho  : density of dust grain material [g cm^-3]
    | md   : dust mass column [g cm^-2]
    """
    pl      = graindist.sizedist.Powerlaw(amin=amin, amax=amax, p=p, **kwargs)
    dru     = graindist.composition.CmDrude(rho=rho)
    mrn_dru = SingleGrainPop(pl, dru, 'RG', md=md)
    gplist  = [mrn_dru]
    keys    = ['RGD']
    return GrainPop(gplist, keys=keys, description='MRN_rgd')
