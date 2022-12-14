#! /usr/bin/env bash
export STRICT="NO"
source "${HOMEgfs}/ush/preamble.sh"

###############################################################
# Source UFSDA workflow modules
. "${HOMEgfs}/ush/load_ufsda_modules.sh"
status=$?
[[ ${status} -ne 0 ]] && exit "${status}"

export STRICT="YES"
###############################################################
# Execute the JJOB
"${HOMEgfs}/jobs/JGDAS_GLOBAL_AERO_ANALYSIS_RUN"
status=$?
exit "${status}"
