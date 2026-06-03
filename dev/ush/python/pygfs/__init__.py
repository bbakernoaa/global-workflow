"""
pygfs
=====

This package provides task classes and utilities for the GFS workflow, including analysis, chemistry, ensemble, marine, snow, and forecast processing.

Modules
-------
- task.analysis: Analysis task
- task.chem_fire_emission: Chemistry fire emissions task
- task.nxs_emission: NEXUS emissions task
- task.aero_analysis: Aerosol analysis task
- task.aero_bmatrix: Aerosol background matrix task
- task.atm_analysis: Atmospheric analysis task
- task.atmens_analysis: Atmospheric ensemble analysis task
- task.ensemble_recenter: Ensemble recentering task
- task.fv3_analysis_calc: FV3 analysis calculation task
- task.marine_bmat: Marine background matrix task
- task.offline_analysis: Offline analysis task
- task.snow_analysis: Snow analysis task
- task.snowens_analysis: Snow ensemble analysis task
- task.upp: Unified Post Processor (UPP) task
- task.oceanice_products: Ocean/ice products task
- task.gfs_forecast: GFS forecast task
- utils.marine_da_utils: Marine data assimilation utilities
- task.fetch: Fetch task

Attributes
----------
__docformat__ : str
    The documentation format for the module.
__version__ : str
    The version of the pygfs package.
pygfs_directory : str
    The absolute path to the pygfs package directory.
"""

import os

from .task.aero_analysis import AerosolAnalysis as AerosolAnalysis
from .task.aero_bmatrix import AerosolBMatrix as AerosolBMatrix
from .task.analysis import Analysis as Analysis
from .task.atm_analysis import AtmAnalysis as AtmAnalysis
from .task.atmens_analysis import AtmEnsAnalysis as AtmEnsAnalysis
from .task.chem_fire_emission import ChemFireEmissions as ChemFireEmissions
from .task.ensemble_recenter import EnsembleRecenter as EnsembleRecenter
from .task.fetch import Fetch as Fetch
from .task.fv3_analysis_calc import FV3AnalysisCalc as FV3AnalysisCalc
from .task.gfs_forecast import GFSForecast as GFSForecast
from .task.marine_bmat import MarineBMat as MarineBMat
from .task.marine_recenter import MarineRecenter as MarineRecenter
from .task.nexus_emission import NEXUSEmissions as NEXUSEmissions
from .task.oceanice_products import OceanIceProducts as OceanIceProducts
from .task.offline_analysis import OfflineAnalysis as OfflineAnalysis
from .task.snow_analysis import SnowAnalysis as SnowAnalysis
from .task.snowens_analysis import SnowEnsAnalysis as SnowEnsAnalysis
from .task.upp import UPP as UPP
from .utils import marine_da_utils as marine_da_utils

__docformat__ = "restructuredtext"
__version__ = "0.1.0"
pygfs_directory = os.path.dirname(__file__)
