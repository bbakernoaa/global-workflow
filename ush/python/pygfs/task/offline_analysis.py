#!/usr/bin/env python3

import os
from collections import OrderedDict
from logging import getLogger
from typing import Dict, Any
import numpy as np
import f90nml
from wxflow import (AttrDict,
                    Task,
                    FileHandler,
                    Executable,
                    logit,
                    WorkflowException)

logger = getLogger(__name__.split('.')[-1])


class OfflineAnalysis(Task):
    """
    Class for tasks to compute analysis increments from
    an offline analysis and previous forecast
    """
    @logit(logger, name="SnowAnalysis")
    def __init__(self, config: Dict[str, Any]):
        """Constructor global offline analysis task

        This method will construct a global offline analysis task.
        This includes:
        - extending the task_config attribute AttrDict to include parameters required for this task

        Parameters
        ----------
        config: Dict
            dictionary object containing task configuration

        Returns
        ----------
        None
        """
        super().__init__(config)

        _res = int(self.task_config['CASE'][1:])

        # fix ocnres
        self.task_config.OCNRES = f"{self.task_config.OCNRES:03d}"

        # Create a local dictionary that is repeatedly used across this class
        local_dict = AttrDict(
            {
                'npz': self.task_config.LEVS - 1,
                'nlon_interp': _res * 4,
                'nlat_interp': _res * 2,
            }
        )

        # Extend task_config with local_dict
        self.task_config = AttrDict(**self.task_config, **local_dict)

    @logit(logger)
    def initialize(self) -> None:
        """Initialize a global offline atmospheric analysis

        This method will initialize a global offline atmospheric analysis.
        This includes:
        - Staging input files
        - Generating namelists from templates
        - copy executables to $DATA

        Parameters
        ----------
        None

        Returns
        ----------
        None
        """

        # stage analysis and forecast files
        logger.info("Copy input files from $COM to $DATA")
        files_to_copy = []
        fcst_file_in = os.path.join(self.task_config.COMIN_ATMOS_HISTORY_PREV,
                                    f"{self.task_config.GPREFIX}atm.f006.nc")
        files_to_copy.append([fcst_file_in, os.path.join(self.task_config.DATA, "atmges_mem001")])
        sfcfcst_file_in = os.path.join(self.task_config.COMIN_ATMOS_HISTORY_PREV,
                                       f"{self.task_config.GPREFIX}sfc.f006.nc")
        files_to_copy.append([sfcfcst_file_in, os.path.join(self.task_config.DATA, "sfcges_mem001")])
        # TODO: Re-stage all of the inputs on HPSS to match EE2-compliant filenames
        anl_file_in = os.path.join(self.task_config.COMINgfs_ATMOS_ANALYSIS.replace('analysis', ''), f"{self.task_config.APREFIX_IN}atmanl.nc")
        files_to_copy.append([anl_file_in, os.path.join(self.task_config.DATA, "atmanl.input.nc")])
        sfcanl_file_in = os.path.join(self.task_config.COMINgfs_ATMOS_ANALYSIS.replace('analysis', ''), f"{self.task_config.APREFIX_IN}sfcanl.nc")
        files_to_copy.append([sfcanl_file_in, os.path.join(self.task_config.DATA, "sfcanl.input.nc")])
        FileHandler({'copy': files_to_copy}).sync()

        # generate namelists for the executables
        # set up the namelist for the background interpolation code
        logger.info("Generating namelist for 'chgres_nc'")
        namelist = {
            'chgres_setup': {
                "i_output": self.task_config.nlon_interp,
                "j_output": self.task_config.nlat_interp,
                "input_file": "atmanl.input.nc",
                "output_file": "atmanl_mem001",
                "terrain_file": "atmges_mem001",
                "ref_file": "atmges_mem001",
            }
        }
        logger.info(namelist)

        with open(os.path.join(self.task_config.DATA, 'chgres_nc_gauss.nml'), 'w') as nmlfile:
            f90nml.write(namelist, nmlfile)
        logger.info(f"Wrote namelist to {os.path.join(self.task_config.DATA, 'chgres_nc_gauss.nml')}")

        logger.info("Generating namelist for 'calc_increment'")
        # set up the namelist for the calc increment code
        namelist = {
            "setup": {
                "datapath": "./",
                "analysis_filename": "atmanl",
                "firstguess_filename": "atmges",
                "increment_filename": "atminc",
                "debug": False,
                "nens": 1,
                "imp_physics": self.task_config.imp_physics
            },
            "zeroinc": {
                "incvars_to_zero": self.task_config.INCREMENTS_TO_ZERO
            }
        }
        logger.info(namelist)

        with open(os.path.join(self.task_config.DATA, 'calc_increment.nml'), 'w') as nmlfile:
            f90nml.write(namelist, nmlfile)
        logger.info(f"Wrote namelist to {os.path.join(self.task_config.DATA, 'calc_increment.nml')}")

        # setup namelist for tref increment calculation
        logger.info("Generating namelist for 'tref_calc'")
        namelist = {
            "tref_calc_setup": {
                "i_output": self.task_config.nlon_interp,
                "j_output": self.task_config.nlat_interp,
                "sfcanl_file": "sfcanl.input.nc",
                "sfcf006_file": "sfcges_mem001",
                "output_file": "dtfanl.nc",
            }
        }

        logger.info(namelist)
        with open(os.path.join(self.task_config.DATA, 'tref_calc.nml'), 'w') as nmlfile:
            f90nml.write(namelist, nmlfile)
        logger.info(f"Wrote namelist to {os.path.join(self.task_config.DATA, 'tref_calc.nml')}")

        # copy executables to $DATA
        executables_to_copy = []
        executable_list = ['enkf_chgres_recenter_nc.x', 'calc_increment_ens_ncio.x', 'tref_calc.x']
        for exec_name in executable_list:
            executables_to_copy.append([os.path.join(self.task_config.EXECglobal, exec_name),
                                        os.path.join(self.task_config.DATA, exec_name)])
        FileHandler({'copy': executables_to_copy}).sync()

    @logit(logger)
    def interpolate_analysis(self) -> None:
        """If necessary, interpolate the offline analysis
        from its original resolution to the resolution of the
        previous model forecast.

        Parameters
        ----------
        self : OfflineAnalysis
            Instance of the OfflineAnalysis object
        """

        # set up and run the executable
        exe = Executable(self.task_config.APRUN_CHGRES)
        exe.add_default_arg(os.path.join(self.task_config.DATA, 'enkf_chgres_recenter_nc.x'))
        exe.add_default_arg(os.path.join(self.task_config.DATA, 'chgres_nc_gauss.nml'))
        try:
            logger.debug(f"Executing {exe}")
            exe()
        except OSError:
            logger.exception(f"Failed to execute {exe}")
            raise
        except Exception as err:
            logger.exception(f"An error occured during execution of {exe}")
            raise WorkflowException(f"An error occured during execution of {exe}") from err

    @logit(logger)
    def calc_tref_inc(self) -> None:
        """Interpolate the tref analysis and compute the dtf increment.

        Parameters
        ----------
        self : OfflineAnalysis
            Instance of the OfflineAnalysis object
        """

        # set up and run the executable
        exe = Executable(self.task_config.APRUN_CHGRES)
        exe.add_default_arg(os.path.join(self.task_config.DATA, 'tref_calc.x'))
        exe.add_default_arg(os.path.join(self.task_config.DATA, 'tref_calc.nml'))
        try:
            logger.debug(f"Executing {exe}")
            exe()
        except OSError:
            logger.exception(f"Failed to execute {exe}")
            raise
        except Exception as err:
            logger.exception(f"An error occured during execution of {exe}")
            raise WorkflowException(f"An error occured during execution of {exe}") from err

    @logit(logger)
    def calc_increment(self) -> None:
        """Compute the analysis increment for input to the forecast model
        by subtracting the previous model forecast from the provided analysis.

        Parameters
        ----------
        self : OfflineAnalysis
            Instance of the OfflineAnalysis object
        """

        # set up and run the executable
        exe = Executable(self.task_config.APRUN_CALCINC)
        exe.add_default_arg(os.path.join(self.task_config.DATA, 'calc_increment_ens_ncio.x'))
        try:
            logger.debug(f"Executing {exe}")
            exe()
        except OSError:
            logger.exception(f"Failed to execute {exe}")
            raise
        except Exception as err:
            logger.exception(f"An error occured during execution of {exe}")
            raise WorkflowException(f"An error occured during execution of {exe}") from err

    @logit(logger)
    def coldstart_initialize(self) -> None:
        """Initialize a coldstart offline atmospheric analysis using GDAS files.

        In a coldstart there is no previous GCAFS forecast, so this method
        substitutes the corresponding GDAS history files as the background
        (atm.f006, sfc.f006), then performs the same namelist generation and
        executable staging as initialize(). It also stages GDAS atmos/input
        IC files and applies the MERRA2 aerosol climatology to them.

        Parameters
        ----------
        None

        Returns
        ----------
        None
        """
        logger.info("Coldstart: staging GDAS history files as background")
        gdas_prefix = f"gdas.t{self.task_config.gcyc:02d}z."
        files_to_copy = []
        fcst_file_in = os.path.join(self.task_config.COMIN_GDAS_ATMOS_HISTORY_PREV,
                                    f"{gdas_prefix}atm.f006.nc")
        files_to_copy.append([fcst_file_in, os.path.join(self.task_config.DATA, "atmges_mem001")])
        sfcfcst_file_in = os.path.join(self.task_config.COMIN_GDAS_ATMOS_HISTORY_PREV,
                                       f"{gdas_prefix}sfc.f006.nc")
        files_to_copy.append([sfcfcst_file_in, os.path.join(self.task_config.DATA, "sfcges_mem001")])
        # TODO: Re-stage all of the inputs on HPSS to match EE2-compliant filenames
        anl_file_in = os.path.join(self.task_config.COMINgfs_ATMOS_ANALYSIS.replace('analysis', ''),
                                   f"{self.task_config.APREFIX_IN}atmanl.nc")
        files_to_copy.append([anl_file_in, os.path.join(self.task_config.DATA, "atmanl.input.nc")])
        sfcanl_file_in = os.path.join(self.task_config.COMINgfs_ATMOS_ANALYSIS.replace('analysis', ''),
                                      f"{self.task_config.APREFIX_IN}sfcanl.nc")
        files_to_copy.append([sfcanl_file_in, os.path.join(self.task_config.DATA, "sfcanl.input.nc")])
        FileHandler({'copy': files_to_copy}).sync()

        # Namelists and executables are identical to the non-coldstart path
        logger.info("Generating namelist for 'chgres_nc'")
        namelist = {
            'chgres_setup': {
                "i_output": self.task_config.nlon_interp,
                "j_output": self.task_config.nlat_interp,
                "input_file": "atmanl.input.nc",
                "output_file": "atmanl_mem001",
                "terrain_file": "atmges_mem001",
                "ref_file": "atmges_mem001",
            }
        }
        logger.info(namelist)
        with open(os.path.join(self.task_config.DATA, 'chgres_nc_gauss.nml'), 'w') as nmlfile:
            f90nml.write(namelist, nmlfile)

        logger.info("Generating namelist for 'calc_increment'")
        namelist = {
            "setup": {
                "datapath": "./",
                "analysis_filename": "atmanl",
                "firstguess_filename": "atmges",
                "increment_filename": "atminc",
                "debug": False,
                "nens": 1,
                "imp_physics": self.task_config.imp_physics
            },
            "zeroinc": {
                "incvars_to_zero": self.task_config.INCREMENTS_TO_ZERO
            }
        }
        logger.info(namelist)
        with open(os.path.join(self.task_config.DATA, 'calc_increment.nml'), 'w') as nmlfile:
            f90nml.write(namelist, nmlfile)

        logger.info("Generating namelist for 'tref_calc'")
        namelist = {
            "tref_calc_setup": {
                "i_output": self.task_config.nlon_interp,
                "j_output": self.task_config.nlat_interp,
                "sfcanl_file": "sfcanl.input.nc",
                "sfcf006_file": "sfcges_mem001",
                "output_file": "dtfanl.nc",
            }
        }
        logger.info(namelist)
        with open(os.path.join(self.task_config.DATA, 'tref_calc.nml'), 'w') as nmlfile:
            f90nml.write(namelist, nmlfile)

        executables_to_copy = []
        executable_list = ['enkf_chgres_recenter_nc.x', 'calc_increment_ens_ncio.x', 'tref_calc.x']
        for exec_name in executable_list:
            executables_to_copy.append([os.path.join(self.task_config.EXECglobal, exec_name),
                                        os.path.join(self.task_config.DATA, exec_name)])
        FileHandler({'copy': executables_to_copy}).sync()

        # Stage GDAS atmos/input IC files and apply MERRA2 aerosol climatology
        logger.info("Coldstart: staging GDAS atmos/input files to GCAFS atmos/input")
        n_tiles = 6
        ic_files = []
        for itile in range(1, n_tiles + 1):
            ic_files.append([
                os.path.join(self.task_config.COMIN_GDAS_ATMOS_INPUT, f"gfs_data.tile{itile}.nc"),
                os.path.join(self.task_config.COMOUT_ATMOS_INPUT, f"gfs_data.tile{itile}.nc"),
            ])
            ic_files.append([
                os.path.join(self.task_config.COMIN_GDAS_ATMOS_INPUT, f"sfc_data.tile{itile}.nc"),
                os.path.join(self.task_config.COMOUT_ATMOS_INPUT, f"sfc_data.tile{itile}.nc"),
            ])
        ic_files.append([
            os.path.join(self.task_config.COMIN_GDAS_ATMOS_INPUT, "gfs_ctrl.nc"),
            os.path.join(self.task_config.COMOUT_ATMOS_INPUT, "gfs_ctrl.nc"),
        ])
        FileHandler({'copy': ic_files}).sync()
        self._apply_merra2_climo_to_inputs()

    @logit(logger)
    def _apply_merra2_climo_to_inputs(self) -> None:
        """Apply MERRA2 aerosol climatology to staged gfs_data IC files.

        After coldstart staging of GDAS atmos/input files, this method performs
        horizontal and vertical interpolation of MERRA2 aerosol climatology onto
        the GFS cubed-sphere grid and writes the result into each
        gfs_data.tile{N}.nc file in COMOUT_ATMOS_INPUT.

        Inspired by https://github.com/noaa-oar-arl/MERRA2_UFS_ICS

        The gfs_data IC files store aerosols in kg/kg (unlike restart files
        which use µg/kg). ak/bk vertical coordinates are read from the
        already-staged gfs_ctrl.nc file.

        Parameters
        ----------
        None

        Returns
        ----------
        None
        """
        import xarray as xr
        from pygfs.utils.merra2climo_to_gdas import (
            open_dataset, get_merra2_plevs,
            horizontal_interp, vertical_interp
        )

        current_month = self.task_config.current_cycle.strftime('%m')
        merra_file = os.path.join(self.task_config.FIXaer,
                                  f"merra2.aerclim.2014-2023.m{current_month}.nc")

        # ak/bk come from gfs_ctrl.nc which is already staged
        ctrl_file = os.path.join(self.task_config.COMOUT_ATMOS_INPUT, 'gfs_ctrl.nc')
        ds_ctrl = open_dataset(ctrl_file)
        ak = ds_ctrl.vcoord.values[0, :]
        bk = ds_ctrl.vcoord.values[1, :]
        fv3_press = (ak + bk * 100000.) / 100.

        merra_press = get_merra2_plevs()[1:]
        ds_merra = open_dataset(merra_file).isel(time=0)

        rename_dict = dict(BCPHILIC='bc2', BCPHOBIC='bc1', DMS='dms',
                           DU001='dust1', DU002='dust2', DU003='dust3', DU004='dust4', DU005='dust5',
                           SS001='seas1', SS002='seas2', SS003='seas3', SS004='seas4', SS005='seas5',
                           OCPHILIC='oc2', OCPHOBIC='oc1', SO2='so2', SO4='so4', MSA='msa')
        # Molecular weights for gas-phase ppm conversions
        mw_dict = {'dms': 63.15, 'so2': 64.066, 'msa': 96.11}
        # IC files store aerosols as kg/kg; gas species as ppm
        gas_species = {'so2', 'dms', 'msa'}

        ds_merra = ds_merra[list(rename_dict.keys())].rename(rename_dict)

        n_tiles = 6
        for itile in range(1, n_tiles + 1):
            input_file = os.path.join(self.task_config.COMOUT_ATMOS_INPUT, f"gfs_data.tile{itile}.nc")
            oro_file = os.path.join(self.task_config.FIXorog, self.task_config.CASE,
                                    f"{self.task_config.CASE}.mx{self.task_config.OCNRES}_oro_data.tile{itile}.nc")

            logger.info(f"Applying MERRA2 climatology to IC file {input_file}")

            ds_input = xr.load_dataset(input_file)

            # Temperature (lowercase 't') and shape from IC file
            temp = ds_input['t'].squeeze().values
            o3mr_shape = ds_input['o3mr'].squeeze().shape

            with open_dataset(oro_file) as ds_oro:
                grid = ds_oro[['geolon', 'geolat']].load()

            hinterp = horizontal_interp(ds_merra, grid)
            hvinterp = vertical_interp(hinterp, np.log(merra_press), np.log(fv3_press))

            # 3D pressure (Pa) from ak/bk — no averaging, use layer interfaces directly
            p = (ak[1:] + bk[1:] * 101325.0).reshape(-1, 1, 1) * np.ones(o3mr_shape)
            density = p / (287.0 * temp)

            for orig_name, field in rename_dict.items():
                interp_data = hvinterp[field].fillna(0.).values

                if field in gas_species:
                    # Convert kg/m3 → ppm using air density
                    mw = mw_dict[field]
                    interp_data = interp_data / 1e9 * density * 1e6 * 24.45 / mw
                else:
                    # MERRA2 µg/kg → IC kg/kg
                    interp_data = interp_data / 1e9

                if field in ds_input:
                    ds_input[field].values[:] = interp_data
                else:
                    # Field does not exist in GDAS IC — create from o3mr template
                    logger.info(f"Creating new variable '{field}' in {input_file}")
                    new_var = ds_input['o3mr'].copy(data=interp_data)
                    new_var.attrs['long_name'] = field
                    new_var.attrs['units'] = 'ppm' if field in gas_species else 'kg/kg'
                    ds_input[field] = new_var

            ds_input.to_netcdf(input_file, mode='w', format='NETCDF4')
            ds_input.close()

    @logit(logger)
    def finalize(self) -> None:
        """Performs closing actions of the offline analysis task
        This method:
        - copies the analysis files to the COM/
        - copies the increment files to the COM/
        - copy some files from GDAS COM/ to GCAFS COM/

        Parameters
        ----------
        self : OfflineAnalysis
            Instance of the OfflineAnalysis object
        """
        output_files = []
        output_files.append([os.path.join(self.task_config.DATA, 'atmanl_mem001'),
                             os.path.join(self.task_config.COMOUT_ATMOS_ANALYSIS, f"{self.task_config.APREFIX}analysis.atm.a006.nc")])
        output_files.append([os.path.join(self.task_config.DATA, 'atminc_mem001'),
                             os.path.join(self.task_config.COMOUT_ATMOS_ANALYSIS, f"{self.task_config.APREFIX}increment.atm.i006.nc")])
        FileHandler({'copy': output_files}).sync()
        # these files are for the surface analysis
        transfer_files = []
        transfer_files.append([os.path.join(self.task_config.COMINobsproc, f"{self.task_config.APREFIX_IN}rtgssthr.grb"),
                               os.path.join(self.task_config.COMOUT_OBS, f"{self.task_config.APREFIX}rtgssthr.grb")])
        transfer_files.append([os.path.join(self.task_config.COMINgfs_ATMOS_ANALYSIS, f"{self.task_config.APREFIX_IN}seaice.5min.blend.grb"),
                               os.path.join(self.task_config.COMOUT_OBS, f"{self.task_config.APREFIX}seaice.5min.blend.grb")])
        transfer_files.append([os.path.join(self.task_config.COMINgfs_ATMOS_ANALYSIS, f"{self.task_config.APREFIX_IN}snogrb_t1534.3072.1536"),
                               os.path.join(self.task_config.COMOUT_OBS, f"{self.task_config.APREFIX}snogrb_t1534.3072.1536")])
        # TODO: Re-stage the inputs for the GCDAS offline analysis on HPSS following EE2-compliant filenames, then update this line
        transfer_files.append([
            os.path.join(self.task_config.DATA, "dtfanl.nc"),
            os.path.join(self.task_config.COMOUT_ATMOS_ANALYSIS,
                         f"{self.task_config.APREFIX}increment.dtf.i006.nc")
        ])
        FileHandler({'copy': transfer_files}).sync()
