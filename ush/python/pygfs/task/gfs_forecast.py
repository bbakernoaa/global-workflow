import os
import logging
import shutil
import shlex
from typing import Dict, Any

from wxflow import logit, Task, mkdir_p, Executable
from pygfs.ufswm.gfs import GFS

logger = logging.getLogger(__name__.split('.')[-1])


class GFSForecast(Task):
    """
    UFS-weather-model forecast task for the GFS
    """

    @logit(logger, name="GFSForecast")
    def __init__(self, config: Dict[str, Any], *args, **kwargs):
        """
        Parameters
        ----------
        config : Dict
                 dictionary object containing configuration from environment

        *args : tuple
                Additional arguments to `Task`

        **kwargs : dict, optional
                   Extra keyword arguments to `Task`
        """

        super().__init__(config, *args, **kwargs)

        # Create and initialize the GFS variant of the UFS
        self.gfs = GFS(config)

    @logit(logger)
    def initialize(self):
        """
        Initialize the forecast task
        """
        # Ported from forecast_predet.sh
        # Create directories and links using FileHandler

        actions = {
            'mkdir': [],
            'link_opt': []
        }

        # Directories to create
        actions['mkdir'].extend([
            self.task_config.get('COMOUT_CONF'),
            os.path.join(self.task_config.DATA, 'INPUT'),
            self.task_config.get('COMOUT_ATMOS_HISTORY'),
            self.task_config.get('COMOUT_ATMOS_MASTER'),
            self.task_config.get('COMOUT_ATMOS_RESTART'),
        ])

        if 'DATAoutput' in self.task_config:
            actions['mkdir'].append(os.path.join(self.task_config.DATAoutput, 'FV3ATM_OUTPUT'))
            actions['link_opt'].append([os.path.join(self.task_config.DATAoutput, 'FV3ATM_OUTPUT'),
                                       os.path.join(self.task_config.DATA, 'FV3ATM_OUTPUT')])

        if 'DATArestart' in self.task_config:
            actions['mkdir'].append(os.path.join(self.task_config.DATArestart, 'FV3_RESTART'))
            actions['link_opt'].append([os.path.join(self.task_config.DATArestart, 'FV3_RESTART'),
                                       os.path.join(self.task_config.DATA, 'RESTART')])

        if self.task_config.get('DO_WAVE') == 'YES':
            actions['mkdir'].extend([
                self.task_config.get('COMOUT_WAVE_HISTORY'),
                self.task_config.get('COMOUT_WAVE_RESTART'),
            ])
            if 'DATAoutput' in self.task_config:
                actions['mkdir'].append(os.path.join(self.task_config.DATAoutput, 'WW3_OUTPUT'))
                actions['link_opt'].append([os.path.join(self.task_config.DATAoutput, 'WW3_OUTPUT'),
                                           os.path.join(self.task_config.DATA, 'WW3_OUTPUT')])
            if 'DATArestart' in self.task_config:
                actions['mkdir'].append(os.path.join(self.task_config.DATArestart, 'WW3_RESTART'))
                actions['link_opt'].append([os.path.join(self.task_config.DATArestart, 'WW3_RESTART'),
                                           os.path.join(self.task_config.DATA, 'WW3_RESTART')])

        if self.task_config.get('DO_OCN') == 'YES':
            actions['mkdir'].extend([
                self.task_config.get('COMOUT_OCEAN_HISTORY'),
                self.task_config.get('COMOUT_OCEAN_RESTART'),
                self.task_config.get('COMIN_OCEAN_INPUT'),
                self.task_config.get('COMOUT_MED_RESTART'),
            ])
            if 'DATAoutput' in self.task_config:
                actions['mkdir'].append(os.path.join(self.task_config.DATAoutput, 'MOM6_OUTPUT'))
                actions['link_opt'].append([os.path.join(self.task_config.DATAoutput, 'MOM6_OUTPUT'),
                                           os.path.join(self.task_config.DATA, 'MOM6_OUTPUT')])
            if 'DATArestart' in self.task_config:
                actions['mkdir'].append(os.path.join(self.task_config.DATArestart, 'MOM6_RESTART'))
                actions['link_opt'].append([os.path.join(self.task_config.DATArestart, 'MOM6_RESTART'),
                                           os.path.join(self.task_config.DATA, 'MOM6_RESTART')])
                actions['mkdir'].append(os.path.join(self.task_config.DATArestart, 'CMEPS_RESTART'))
                actions['link_opt'].append([os.path.join(self.task_config.DATArestart, 'CMEPS_RESTART'),
                                           os.path.join(self.task_config.DATA, 'CMEPS_RESTART')])

        if self.task_config.get('DO_ICE') == 'YES':
            actions['mkdir'].extend([
                self.task_config.get('COMOUT_ICE_HISTORY'),
                self.task_config.get('COMOUT_ICE_RESTART'),
                self.task_config.get('COMIN_ICE_INPUT'),
            ])
            if 'DATAoutput' in self.task_config:
                actions['mkdir'].append(os.path.join(self.task_config.DATAoutput, 'CICE_OUTPUT'))
                actions['link_opt'].append([os.path.join(self.task_config.DATAoutput, 'CICE_OUTPUT'),
                                           os.path.join(self.task_config.DATA, 'CICE_OUTPUT')])
            if 'DATArestart' in self.task_config:
                actions['mkdir'].append(os.path.join(self.task_config.DATArestart, 'CICE_RESTART'))
                actions['link_opt'].append([os.path.join(self.task_config.DATArestart, 'CICE_RESTART'),
                                           os.path.join(self.task_config.DATA, 'CICE_RESTART')])

        if self.task_config.get('DO_AERO_FCST') == 'YES':
            actions['mkdir'].append(self.task_config.get('COMOUT_CHEM_HISTORY'))
            target = self.task_config.get('COMIN_CHEM_INPUT')
            if target:
                actions['link_opt'].append([target, os.path.join(self.task_config.DATA, 'ChemInput')])

        # Remove None/Empty from mkdir
        actions['mkdir'] = [d for d in actions['mkdir'] if d]

        # Sync using FileHandler
        FileHandler(actions).sync()

    @logit(logger)
    def configure(self):
        """
        Configure the forecast task (namelists, etc.)
        """
        # Ported from ush/parsing_namelists_FV3.sh and exglobal_forecast.sh

        # 1. Setup tables
        parm_ufs = os.path.join(self.task_config.PARMgfs, 'ufs')
        diag_table_src = self.task_config.get('DIAG_TABLE', os.path.join(parm_ufs, 'fv3', 'diag_table'))
        diag_table_append = self.task_config.get('DIAG_TABLE_APPEND', os.path.join(parm_ufs, 'fv3', 'diag_table_aod'))
        data_table_src = self.task_config.get('DATA_TABLE', os.path.join(parm_ufs, 'MOM6_data_table.IN'))
        field_table_src = self.task_config.get('FIELD_TABLE', os.path.join(parm_ufs, 'fv3', 'field_table'))

        # Build diag_table
        diag_table_out = os.path.join(self.task_config.DATA, 'diag_table')
        diag_template = os.path.join(self.task_config.DATA, 'diag_table.template')

        with open(diag_template, 'w') as f:
            f.write("UFS_Weather_Model_Forecast\n")
            if self.task_config.get('DOIAU') == 'YES':
                cycle = self.task_config.previous_cycle
            else:
                cycle = self.task_config.current_cycle
            f.write(f"{cycle.strftime('%Y %m %d %H')} 0 0\n")

            for src in [diag_table_src, self.task_config.get('AERO_DIAG_TABLE'), diag_table_append]:
                if src and os.path.exists(src):
                    with open(src, 'r') as sf:
                        f.write(sf.read())

        # Parse diag_table
        ctx = self.task_config.deepcopy()
        ctx['MOM6_OUTPUT_DIR'] = './MOM6_OUTPUT'
        self.gfs.parse_ufs_templates(diag_template, diag_table_out, ctx)

        # 2. Copy data_table
        if os.path.exists(data_table_src):
            shutil.copy2(data_table_src, os.path.join(self.task_config.DATA, 'data_table'))

        # 3. Build field_table
        field_table_out = os.path.join(self.task_config.DATA, 'field_table')
        aero_field_table = self.task_config.get('AERO_FIELD_TABLE')
        if aero_field_table and os.path.exists(aero_field_table):
            # Port complex concatenation from shell if needed, but for now just append
            with open(field_table_out, 'w') as f:
                with open(field_table_src, 'r') as sf:
                    f.write(sf.read())
                with open(aero_field_table, 'r') as af:
                    f.write(af.read())
        else:
            shutil.copy2(field_table_src, field_table_out)

        # 4. Parse other templates
        templates = [
            (os.path.join(parm_ufs, 'ufs.configure.IN'), 'ufs.configure'),
            (os.path.join(parm_ufs, 'model_configure.IN'), 'model_configure'),
            (os.path.join(parm_ufs, 'global_control.nml.IN'), 'input.nml'),
        ]

        for tmpl, out in templates:
            if os.path.exists(tmpl):
                self.gfs.parse_ufs_templates(tmpl, os.path.join(self.task_config.DATA, out), self.task_config)
            else:
                # Try to find them in other common locations if needed
                logger.warning(f"Template {tmpl} not found!")

    @logit(logger)
    def execute(self):
        """
        Execute the forecast
        """
        # Copy executable
        fcst_exec_name = self.task_config.get('FCSTEXEC', 'gfs_model.x')
        src_exec = os.path.join(self.task_config.EXECgfs, fcst_exec_name)
        dst_exec = os.path.join(self.task_config.DATA, fcst_exec_name)

        logger.info(f"Copying executable from {src_exec} to {dst_exec}")
        shutil.copy2(src_exec, dst_exec)

        # Run
        aprun_ufs = self.task_config.get('APRUN_UFS', '')
        if not aprun_ufs:
            logger.warning("APRUN_UFS is empty, running executable directly.")
            exe = Executable(dst_exec)
            exe(output=os.path.join(self.task_config.DATA, 'stdout'),
                error=os.path.join(self.task_config.DATA, 'stderr'))
        else:
            cmd_parts = shlex.split(aprun_ufs)
            launcher = cmd_parts[0]
            launcher_args = cmd_parts[1:]

            exe = Executable(launcher)
            logger.info(f"Executing: {launcher} {' '.join(launcher_args)} {dst_exec}")
            exe(*launcher_args, dst_exec,
                output=os.path.join(self.task_config.DATA, 'stdout'),
                error=os.path.join(self.task_config.DATA, 'stderr'))

    @logit(logger)
    def finalize(self):
        """
        Finalize the forecast task (copy output, etc.)
        """
        # Copy configuration files back to COM for provenance
        # Ported from FV3_out in ush/forecast_postdet.sh
        comout_conf = self.task_config.get('COMOUT_CONF')
        if comout_conf:
            mkdir_p(comout_conf)
            for f in ['input.nml', 'model_configure', 'ufs.configure', 'diag_table']:
                src = os.path.join(self.task_config.DATA, f)
                if os.path.exists(src):
                    dst = os.path.join(comout_conf, f'ufs.{f}')
                    logger.info(f"Copying {src} to {dst}")
                    shutil.copy2(src, dst)
