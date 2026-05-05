#!/usr/bin/env python3
# exgcdas_atmos_initialize.py
# Coldstart initialization for GCAFS: stages GDAS atmos/input files
# (gfs_data.tile*.nc, sfc_data.tile*.nc, gfs_ctrl.nc) directly into
# the GCAFS model/atmos/input COM directory without running any DA
# or increment calculation.
import os

from wxflow import Logger, cast_strdict_as_dtypedict
from pygfs.task.offline_analysis import OfflineAnalysis

# Initialize root logger
logger = Logger(
    level=os.environ.get("LOGGING_LEVEL", "DEBUG"), colored_log=True)


if __name__ == '__main__':

    # Take configuration from environment and cast it as python dictionary
    config = cast_strdict_as_dtypedict(os.environ)

    # Instantiate the offline analysis task
    offline_anl = OfflineAnalysis(config)

    # Stage GDAS atmos/input files to GCAFS atmos/input (coldstart only)
    offline_anl.coldstart_initialize()
