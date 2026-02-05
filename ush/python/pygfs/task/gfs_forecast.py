import os
import shutil
from pygfs.ufswm.ufs import UFS
from wxflow import Logger, AttrDict

logger = Logger(level=os.environ.get("LOGGING_LEVEL", "INFO"))


class GFSForecast(UFS):
    def __init__(self, config):
        super().__init__(config)
        self.DATA = self.config.get('DATA')

    def initialize(self):
        """
        Setup the working directory and symlinks
        """
        logger.info("Initializing GFS Forecast task")
        if not os.path.exists(self.DATA):
            os.makedirs(self.DATA)

        # Create symlinks to COMIN/COMOUT if needed
        # Ported from exglobal_forecast.sh logic
        pass

    def configure(self):
        """
        Prepare namelists and model tables
        """
        logger.info("Configuring GFS Forecast task")

        # Define the templates for UFS (mimicking declare_from_tmpl results)
        input_nml = self.config.get('INPUT_NML_TMPL', '')
        model_configure = self.config.get('MODEL_CONFIGURE_TMPL', '')

        tmpls = {
            'input.nml': input_nml,
            'model_configure': model_configure
        }

        self.parse_ufs_templates(tmpls, self.DATA)

        # Handle fix files
        fix_files = []
        # Logic to populate fix_files based on resolution
        # fix_files.append((src, dest))
        self.copy_fix_files(fix_files, self.DATA)

    def execute(self):
        """
        Run the forecast
        """
        logger.info("Executing GFS Forecast")

        exec_path = os.path.join(
            self.config.HOMEgfs, "exec", "global_forecast")
        ntasks = self.config.get('total_tasks', 1)

        # Setup links for initial conditions
        self._setup_ics()

        self.run_ufs(self.DATA, exec_path, ntasks)

    def _setup_ics(self):
        """
        Links initial condition files to DATA directory
        """
        logger.info("Setting up initial conditions")
        # Logic to link sfc_data, gfs_data, etc. from COMIN
        # Example:
        # ln -sf ${COMIN_ATMOS_INPUT}/${CDUMP}.t${cyc}z.atmf${fhr}.nc \
        #        ${DATA}/gfs_data.nc
        comin = self.config.get('COMIN_ATMOS_INPUT')
        if comin:
            src = os.path.join(
                comin,
                f"{self.config.RUN}.t{self.config.cyc}z.atminit.nc"
            )
            dest = os.path.join(self.DATA, "gfs_data.nc")
            if os.path.exists(src):
                if os.path.exists(dest):
                    os.remove(dest)
                os.symlink(src, dest)

    def finalize(self):
        """
        Post-execution cleanup and moving results to COMOUT
        """
        logger.info("Finalizing GFS Forecast")
        comout = self.config.get('COMOUT_ATMOS_HISTORY')
        if comout and os.path.exists(self.DATA):
            if not os.path.exists(comout):
                os.makedirs(comout)

            # Move history files
            for f in os.listdir(self.DATA):
                if f.startswith('atmf') and f.endswith('.nc'):
                    src = os.path.join(self.DATA, f)
                    dest = os.path.join(comout, f)
                    logger.info(f"Moving {f} to {comout}")
                    shutil.move(src, dest)

            # Move restart files to COMOUT_ATMOS_RESTART
            comout_restart = self.config.get('COMOUT_ATMOS_RESTART')
            if comout_restart:
                if not os.path.exists(comout_restart):
                    os.makedirs(comout_restart)
                # ... move logic ...
