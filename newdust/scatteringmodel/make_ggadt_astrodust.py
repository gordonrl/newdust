"""
This file turns multiple GGADT output files for grains of the same material, but mixed shapes, sizes, and orientations into a single FITS file

FITS files made by make_ggadt_astrodust do follow the same structure as those in ScatteringModel HOWEVER the 3rd HDU (containing radius data) now also contains the shape, axis ratio, and orientation.
"""

from make_ggadt import parse_file
import numpy as np
from astropy.io import fits

"""
Files follow the same naming structure as those for make_ggadt.py:

    [material]_[index].out
    
    [index] is 0-indexed, where grain radius increasing with index

    I structure my files by material so this program runs for one material at a time (The folder containing GGADT output data should be organized into subfolders by material) 
"""

def make_fits_astrodust(material, folder, indicies, outfile, overwrite=True):
    """
    Makes a FITS file for grains of the same material but mixed orientations, shapes, and sizes (radii)

    material: string: material of the grain as it appears in the file names -- this should be constant across all input files

    folder: string: file path to the folder containing the GGADT output data. (ex: tables/astrodust_data/fayalite)

    indicies: list[int]: a list of the indicies used in file naming -- should be consecutive integers range from 0 to the last index used in file naming (ex: if there are 32 files, indicies = range(32))

    outfile: string: name of the ouputted FITS file

    overwrite: bool: whether or not to overrite a preexisting FITS file with the same name

    Returns the name of the FITS file described above
    """

    #data to store
    radii = []
    shapes = [] 
    orientations = [] 
    axis_ratios = [] 
    qext = []
    qabs = []
    qsca = []
    diff = [] #NEED TO IMPLEMENT

    #constant parameters:
    evs = []
    theta = [] #NEED TO IMPLEMENT

    #Go file by file, parsing data and populating the lists above
    for i in indicies:

        filename = f'{folder}/{material}_{i}.out'
        data = parse_file(filename)

        qext.append(data['qext'])
        qabs.append(data['qabs'])
        qsca.append(data['qsca'])
        radii.append(data['radius'])
        shapes.append(data['shape'])
        orientations.append(data['orientation'])
        axis_ratios.append(data['axis ratio'])

        #evs and theta is still constant so once it's populated it just needs to be checked for consistency
        if not evs: 
            evs = data['evs']
        elif evs != data['evs']:
            raise Exception('Error: Incident energy range must be constant')

    #Radii, shapes, orientations, and axis ratios should all be the same length
    length = len(indicies)
    if length != len(radii):
        raise Exception('Error: Too many radii') if length < len(radii) else Exception('Error: Not enough radii')
    if length != len(shapes):
        raise Exception('Error: Too many radii') if length < len(radii) else Exception('Error: Not enough radii')
    if length != len(orientations):
        raise Exception('Error: Too many radii') if length < len(radii) else Exception('Error: Not enough radii')
    if length != len(axis_ratios):
        raise Exception('Error: Too many radii') if length < len(radii) else Exception('Error: Not enough radii')
    
    #make parameters and header
    header = make_header(material)
    pars = make_pars(evs, radii, shapes, orientations, axis_ratios, theta)
    
    img_list = []
    for (val, head) in zip([qext, qabs, qsca, diff],
                           ["Qext", "Qabs", "Qsca", "Diff-xsect (ster^-1)"]):
        htemp = fits.Header()
        htemp['TYPE'] = head
        img_list.append(fits.ImageHDU(val, header=htemp))

    #write table
    fnl_list = [header] + pars + img_list
    hdu_list = fits.HDUList(hdus=fnl_list)
    hdu_list.writeto(outfile, overwrite=overwrite)
    return outfile

#helper functions
def make_header(material):
    """
    Makes the PrimaryHDU header for the FITS file

    material: string: the material of the grains (this is the same for every GGADT output file)

    Returns the PrimaryHDU for make_fits_astrodust
    """
    result = fits.Header()
    result['MATERIAL'] = material
    result['COMMENT']  = "Extinction efficiency and differential cross-sections"
    result['COMMENT'] = "HDU 3 contains the radius, shape, orientation, and axis ratio for each grain"
    result['COMMENT']  = "HDUS 4-6 are Qext, Qsca, Qabs in wavelength (or energy) vs grain radius"
    result['COMMENT']  = "HDU 7 is the differential scattering cross-section (ster^-1)"
    return fits.PrimaryHDU(header=result)

def make_pars(evs, radii, shapes, orientations, axis_ratios, theta):
    """
    Makes three BinaryTableHDUs after the PrimaryHDU for make_fits

    evs: list[float]: list of the incident energies -- this list is the same for every GGADT output file

    radii: list[float]: list of the radii for each grain

    shapes: list[string]: list of the shapes for each grain

    orientations: list[string]: list of the orientations for each grain

    axis_ratio: list[float]: list of the axis ratios for each grain

    theta: list[float]: list of angles for the differential scattering cross sections

    Returns a list of the BinaryTableHDUs listed -- evs; a record array of radii, shapes, orientations, and axis ratios; and theta
    """

    c1 = fits.BinTableHDU.from_columns(
        [fits.Column(name='lam', array=np.array(evs), format='D', unit='keV')]
    )
    c2 = fits.BinTableHDU.from_columns(
        [fits.Column(name='a', array=np.array(radii), format='D', unit='micron'),
         fits.Column(name='shape', array=np.array(shapes), format='10A'), #Not sure about format
         fits.Column(name='orientation', array=np.array(orientations), format='10A'), #Not sure about format
         fits.Column(name='axis_ratio', array=np.array(axis_ratios), format='D')]
    )
    c3 = fits.BinTableHDU.from_columns(
        [fits.Column(name='theta', array=np.array(theta), format='D', unit='rad')]
    )

    return [c1, c2, c3]