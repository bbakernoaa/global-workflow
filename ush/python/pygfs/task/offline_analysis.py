#!/usr/bin/env python3

import os
from collections import OrderedDict
from logging import getLogger
from typing import Dict, Any
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
        # TODO: Re-stage all of the inputs on HPSS to match EE2-compliant filenames
        anl_file_in = os.path.join(self.task_config.COMINgfs_ATMOS_ANALYSIS.replace('analysis', ''), f"{self.task_config.APREFIX_IN}atmanl.nc")
        files_to_copy.append([anl_file_in, os.path.join(self.task_config.DATA, "atmanl.input.nc")])
        sfcanl_file_in = os.path.join(self.task_config.COMINgfs_ATMOS_ANALYSIS.replace('analysis', ''), f"{self.task_config.APREFIX_IN}sfcanl.nc")
        files_to_copy.append([sfcanl_file_in, os.path.join(self.task_config.DATA, "sfcanl.input.nc")])

        if not self.task_config.get('COLDSTART', False):
            fcst_file_in = os.path.join(self.task_config.COMIN_ATMOS_HISTORY_PREV,
                                        f"{self.task_config.GPREFIX}atm.f006.nc")
            files_to_copy.append([fcst_file_in, os.path.join(self.task_config.DATA, "atmges_mem001")])
            sfcfcst_file_in = os.path.join(self.task_config.COMIN_ATMOS_HISTORY_PREV,
                                           f"{self.task_config.GPREFIX}sfc.f006.nc")
            files_to_copy.append([sfcfcst_file_in, os.path.join(self.task_config.DATA, "sfcges_mem001")])

        FileHandler({'copy': files_to_copy}).sync()

        if self.task_config.get('COLDSTART', False):
            # For cold start, write fort.41 namelist for chgres_cube to regrid
            # the offline analysis directly to FV3 cube-sphere tiles
            logger.info("Generating fort.41 namelist for 'chgres_cube' (cold start)")
            ntiles = 6
            orog_files = ",\n".join(
                f'                         "{self.task_config.CASE}.mx{self.task_config.OCNRES}_oro_data.tile{i}.nc"'
                for i in range(1, ntiles + 1)
            )
            fort41 = f"""&config
  mosaic_file_target_grid="./{self.task_config.CASE}_mosaic.nc"
  fix_dir_target_grid="./"
  orog_dir_target_grid="./"
  orog_files_target_grid={orog_files}
  vcoord_file_target_grid="./global_hyblev.l{self.task_config.LEVS}.txt"
  mosaic_file_input_grid="NULL"
  orog_dir_input_grid="NULL"
  orog_files_input_grid="NULL"
  data_dir_input_grid="./"
  atm_files_input_grid="./atmanl.input.nc"
  atm_core_files_input_grid="NULL"
  atm_tracer_files_input_grid="NULL"
  sfc_files_input_grid="./sfcanl.input.nc"
  nst_files_input_grid="NULL"
  grib2_file_input_grid="NULL"
  geogrid_file_input_grid="NULL"
  varmap_file="NULL"
  wam_parm_file="NULL"
  cycle_year={self.task_config.PDY[:4]}
  cycle_mon={self.task_config.PDY[4:6]}
  cycle_day={self.task_config.PDY[6:8]}
  cycle_hour={self.task_config.cyc}
  convert_atm=.true.
  convert_sfc=.true.
  convert_nst=.true.
  input_type="gaussian_netcdf"
  tracers="sphum","liq_wat","o3mr","ice_wat","rainwat","snowwat","graupel"
  tracers_input="spfh","clwmr","o3mr","icmr","rwmr","snmr","grle"
  regional=0
  halo_bndy=0
  halo_blend=0
  sotyp_from_climo=.true.
  vgtyp_from_climo=.true.
  vgfrc_from_climo=.true.
  minmax_vgfrc_from_climo=.true.
  tg3_from_soil=.false.
  lai_from_climo=.true.
  external_model="GFS"
  nsoill_out=4
  thomp_mp_climo_file="NULL"
  wam_cold_start=.false.
/
"""
            fort41_path = os.path.join(self.task_config.DATA, 'fort.41')
            with open(fort41_path, 'w') as fort41_file:
                fort41_file.write(fort41)
            logger.info(f"Wrote fort.41 to {fort41_path}")

            # stage fix files needed by chgres_cube
            logger.info("Staging fix files for chgres_cube")
            fix_files_to_copy = []
            fix_files_to_copy.append([
                os.path.join(self.task_config.FIXglobal, 'am', f"global_hyblev.l{self.task_config.LEVS}.txt"),
                os.path.join(self.task_config.DATA, f"global_hyblev.l{self.task_config.LEVS}.txt")
            ])
            fix_files_to_copy.append([
                os.path.join(self.task_config.FIXglobal, 'orog', self.task_config.CASE,
                             f"{self.task_config.CASE}_mosaic.nc"),
                os.path.join(self.task_config.DATA, f"{self.task_config.CASE}_mosaic.nc")
            ])
            for i in range(1, ntiles + 1):
                fix_files_to_copy.append([
                    os.path.join(self.task_config.FIXglobal, 'orog', self.task_config.CASE,
                                 f"{self.task_config.CASE}_grid.tile{i}.nc"),
                    os.path.join(self.task_config.DATA, f"{self.task_config.CASE}_grid.tile{i}.nc")
                ])
                fix_files_to_copy.append([
                    os.path.join(self.task_config.FIXglobal, 'orog', self.task_config.CASE,
                                 f"{self.task_config.CASE}.mx{self.task_config.OCNRES}_oro_data.tile{i}.nc"),
                    os.path.join(self.task_config.DATA,
                                 f"{self.task_config.CASE}.mx{self.task_config.OCNRES}_oro_data.tile{i}.nc")
                ])
                for sfc_fix in ['slope_type', 'maximum_snow_albedo', 'snowfree_albedo',
                                'soil_type', 'vegetation_type', 'substrate_temperature',
                                'vegetation_greenness', 'facsf']:
                    fix_files_to_copy.append([
                        os.path.join(self.task_config.FIXglobal, 'orog', self.task_config.CASE, 'sfc',
                                     f"{self.task_config.CASE}.mx{self.task_config.OCNRES}.{sfc_fix}.tile{i}.nc"),
                        os.path.join(self.task_config.DATA,
                                     f"{self.task_config.CASE}.mx{self.task_config.OCNRES}.{sfc_fix}.tile{i}.nc")
                    ])
            FileHandler({'copy': fix_files_to_copy}).sync()

            # copy chgres_cube executable to $DATA
            executables_to_copy = [[
                os.path.join(self.task_config.EXECglobal, 'chgres_cube'),
                os.path.join(self.task_config.DATA, 'chgres_cube')
            ]]
            FileHandler({'copy': executables_to_copy}).sync()

        else:
            # generate namelists for the warm-start executables
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
    def generate_coldstart_ics(self) -> None:
        """Regrid the offline analysis to FV3 cube-sphere tiles for a cold start
        forecast using chgres_cube. No increment calculation is performed.

        Parameters
        ----------
        self : OfflineAnalysis
            Instance of the OfflineAnalysis object
        """

        exe = Executable(self.task_config.APRUN_CHGRES)
        exe.add_default_arg(os.path.join(self.task_config.DATA, 'chgres_cube'))
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
        if self.task_config.get('COLDSTART', False):
            # Copy chgres_cube output tiles to COMOUT_ATMOS_INPUT
            ntiles = 6
            output_files = []
            for i in range(1, ntiles + 1):
                output_files.append([
                    os.path.join(self.task_config.DATA, f"out.atm.tile{i}.nc"),
                    os.path.join(self.task_config.COMOUT_ATMOS_INPUT, f"gfs_data.tile{i}.nc")
                ])
                output_files.append([
                    os.path.join(self.task_config.DATA, f"out.sfc.tile{i}.nc"),
                    os.path.join(self.task_config.COMOUT_ATMOS_INPUT, f"sfc_data.tile{i}.nc")
                ])
            output_files.append([
                os.path.join(self.task_config.DATA, "gfs_ctrl.nc"),
                os.path.join(self.task_config.COMOUT_ATMOS_INPUT, "gfs_ctrl.nc")
            ])
            FileHandler({'copy': output_files}).sync()
        else:
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
