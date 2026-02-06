#!/usr/bin/env python3
"""
This script modifies the default global-workflow
to set up the GCAFS workflow for NCO.

This includes:
- Copying relevant files from dev/jobs and dev/scripts
- Renaming files where appropriate
- Changing variables/paths in the copied files
- Removing unused files where appropriate
"""
import os
import re
from wxflow import FileHandler

# Get the absolute path of the directory containing this file
current_dir_path = os.path.dirname(os.path.abspath(__file__))
# Get the absolute path of the global-workflow directory
# which is assumed to be two directories up from the current file
global_workflow_dir = os.path.abspath(os.path.join(current_dir_path, "../.."))


def replace_gfs_with_gcafs(input_file):
    """
    Replace all instances of FOOgfs with FOOgcafs in the given input file.
    This matches patterns like HOMEgfs -> HOMEgcafs, USHgfs -> USHgcafs, etc.

    Parameters
    ----------
    input_file : str
        Path to the file to modify

    Returns
    -------
    int
        Number of replacements made
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"File not found: {input_file}")

    # Read the file content
    with open(input_file, 'r') as f:
        content = f.read()

    # Count and replace all instances of FOOgfs with FOOgcafs
    # This will match patterns like: HOMEgfs, USHgfs, PARMgfs, etc.
    # Does NOT match standalone "gfs" or quoted "gfs"
    # Match word characters followed by "gfs" at word boundary, but ensure prefix has at least 2 chars
    # This ensures we match variable names like HOMEgfs but not just "gfs" or "Xgfs"
    pattern = r'(\w{2,})gfs\b'

    replacement_count = 0

    def replace_func(match):
        nonlocal replacement_count
        replacement_count += 1
        prefix = match.group(1)
        return f"{prefix}gcafs"

    modified_content = re.sub(pattern, replace_func, content)

    # Write the modified content back to the file
    with open(input_file, 'w') as f:
        f.write(modified_content)

    return replacement_count


def get_template_dict(global_workflow_dir):
    """
    Extract and resolve templates from config.com and other config files,
    prioritizing NCO branch in config.com.

    Parameters
    ----------
    global_workflow_dir : str
        Path to the global workflow directory

    Returns
    -------
    dict
        Dictionary of resolved templates
    """
    templates = {}
    config_dir = os.path.join(global_workflow_dir, 'dev', 'parm', 'config', 'gfs')
    if not os.path.exists(config_dir):
        return templates

    # Priority 1: config.com (with NCO logic)
    config_com_path = os.path.join(config_dir, 'config.com')
    if os.path.exists(config_com_path):
        with open(config_com_path, 'r') as f:
            lines = f.readlines()

        in_nco_branch = False
        in_else_branch = False

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if 'if [[ "${RUN_ENVIR:-emc}" == "nco" ]]' in line:
                in_nco_branch = True
                continue
            if in_nco_branch and 'else' == line:
                in_nco_branch = False
                in_else_branch = True
                continue
            if (in_nco_branch or in_else_branch) and 'fi' == line:
                in_nco_branch = False
                in_else_branch = False
                continue

            if in_else_branch:
                continue

            match = re.search(r'(?:declare\s+-[^\s]+\s+)?(\w+)=(.+)', line)
            if match:
                var_name = match.group(1)
                var_value = match.group(2).strip()
                # Remove trailing comments
                var_value = var_value.split(' #')[0].strip()

                # Remove outermost quotes and concatenation quotes
                if (var_value.startswith("'") and var_value.endswith("'")) or \
                   (var_value.startswith('"') and var_value.endswith('"')):
                    var_value = var_value[1:-1]

                var_value = var_value.replace("'", "").replace('"', "")

                if var_name.endswith('_TMPL') or var_name == 'COM_BASE':
                    templates[var_name] = var_value

    # Also scan other config.* files for any missing templates
    for filename in os.listdir(config_dir):
        if filename.startswith('config.') and filename != 'config.com':
            path = os.path.join(config_dir, filename)
            with open(path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    match = re.search(r'(?:declare\s+-[^\s]+\s+|export\s+)?(\w+)=(.+)', line)
                    if match:
                        var_name = match.group(1)
                        if var_name.endswith('_TMPL') or var_name == 'COM_BASE':
                            if var_name not in templates:
                                var_value = match.group(2).strip()
                                var_value = var_value.split(' #')[0].strip()
                                if (var_value.startswith("'") and var_value.endswith("'")) or \
                                   (var_value.startswith('"') and var_value.endswith('"')):
                                    var_value = var_value[1:-1]
                                var_value = var_value.replace("'", "").replace('"', "")
                                templates[var_name] = var_value

    # Recursive resolution of templates

    def resolve(val):
        vars_found = re.findall(r'\$\{(\w+)\}', val)
        changed = False
        for v in vars_found:
            if v in templates:
                val = val.replace(f'${{{v}}}', templates[v])
                changed = True
        if changed:
            return resolve(val)
        return val

    resolved_templates = {}
    for k, v in templates.items():
        resolved_templates[k] = resolve(v)

    return resolved_templates


def resolve_template(template_str, overrides):
    """
    Substitute overrides into a template string.

    Parameters
    ----------
    template_str : str
        Template string to substitute into
    overrides : dict
        Dictionary of variable names and their override values

    Returns
    -------
    str
        Substituted template string
    """
    res = template_str
    # Sort overrides by length descending to avoid partial replacements
    for k in sorted(overrides.keys(), key=len, reverse=True):
        v = overrides[k]
        res = res.replace(f'${{{k}}}', v)
        res = re.sub(f'\\${k}\\b', v, res)
    return res


def parse_overrides(overrides_str):
    """
    Parse bash-style overrides like VAR=VAL or VAR="VAL".

    Parameters
    ----------
    overrides_str : str
        String containing overrides

    Returns
    -------
    dict
        Dictionary of overrides
    """
    overrides = {}
    pos = 0
    while pos < len(overrides_str):
        match = re.match(r'(\w+)=', overrides_str[pos:])
        if not match:
            pos += 1
            continue
        var_name = match.group(1)
        pos += match.end()
        if pos < len(overrides_str) and overrides_str[pos] in ("'", '"'):
            quote = overrides_str[pos]
            pos += 1
            end_quote = overrides_str.find(quote, pos)
            if end_quote == -1:
                val = overrides_str[pos:]
                pos = len(overrides_str)
            else:
                val = overrides_str[pos:end_quote]
                pos = end_quote + 1
        else:
            match = re.match(r'([^ \t\n\\]+)', overrides_str[pos:])
            if match:
                val = match.group(1)
                pos += match.end()
            else:
                val = ""
        overrides[var_name] = val
        while pos < len(overrides_str) and overrides_str[pos] in " \t":
            pos += 1
    return overrides


def replace_declare_from_tmpl_in_file(file_path, templates):
    """
    Replace declare_from_tmpl calls in a file with explicit export statements.

    Parameters
    ----------
    file_path : str
        Path to the file to modify
    templates : dict
        Dictionary of resolved templates

    Returns
    -------
    int
        Number of replacements made
    """
    if not os.path.exists(file_path):
        return 0
    with open(file_path, 'r') as f:
        content = f.read()

    # Match optional overrides, declare_from_tmpl, flags, and arguments
    # Handles multiline arguments with backslashes
    pattern = r'((?:[ \t]*[\w{}="$.:/%-]+=[^ \t\n\\]+[ \t]*)*)declare_from_tmpl\s+([-rx\s\\]*)\s+((?:[ \t]*[:\w${}./-]+(?:[ \t]*\\[ \t]*\n[ \t]*| [ \t]*)*)+)'

    replacement_count = 0

    def replacement(match):
        nonlocal replacement_count
        replacement_count += 1
        full_match = match.group(0)
        indent = re.match(r'[ \t]*', full_match).group(0)
        overrides_str = match.group(1).strip()
        # flags = match.group(2).strip() # Unused as per user request (no -r handling)
        args_str = match.group(3).strip()

        overrides = parse_overrides(overrides_str)

        # Parse args, handling backslashes and newlines
        args_str = args_str.replace('\\\n', ' ').replace('\\', ' ')
        args = args_str.split()

        new_lines = []
        for arg in args:
            if ':' in arg:
                var_name, tmpl_name = arg.split(':')
            else:
                var_name = arg
                tmpl_name = f"{var_name}_TMPL"

            if tmpl_name in templates:
                template_val = templates[tmpl_name]
                resolved_val = resolve_template(template_val, overrides)
                new_lines.append(f'export {var_name}="{resolved_val}"')
            else:
                new_lines.append(f'# Template {tmpl_name} not found for {var_name}')

        # Preserve leading overrides that were not part of declare_from_tmpl (if any)
        # Actually, our regex captures all overrides on the line.
        # If they were part of the call, they are now redundant if they were only for the call.
        # But in bash, YMD=... HH=... cmd, YMD and HH are only for cmd.
        # So replacing with export is correct.

        return '\n'.join([f'{indent}{line}' for line in new_lines])

    modified_content = re.sub(pattern, replacement, content)

    with open(file_path, 'w') as f:
        f.write(modified_content)

    return replacement_count


def copy_job_files(global_workflow_dir):
    """
    Copy job files from dev/jobs to jobs directory with appropriate renaming.

    Parameters
    ----------
    global_workflow_dir : str
        Path to the global workflow directory

    Returns
    -------
    list
        List of tuples containing (src_path, dest_path) for copied files
    """
    gcafs_jobs = {
        "JGCAFS_FORECAST": "JGLOBAL_FORECAST",
        "JGCAFS_PREP_EMISSIONS": "JGLOBAL_PREP_EMISSIONS",
        "JGCAFS_ATMOS_POST_MANAGER": "JGLOBAL_ATMOS_POST_MANAGER",
        "JGCAFS_ATMOS_PRODUCTS": "JGLOBAL_ATMOS_PRODUCTS",
    }
    gcdas_jobs = {
        "JGCDAS_FORECAST": "JGLOBAL_FORECAST",
        "JGCDAS_PREP_EMISSIONS": "JGLOBAL_PREP_EMISSIONS",
        "JGCDAS_ATMOS_POST_MANAGER": "JGLOBAL_ATMOS_POST_MANAGER",
        "JGCDAS_ATMOS_PRODUCTS": "JGLOBAL_ATMOS_PRODUCTS",
        "JGCDAS_ATMOS_INITIALIZE": "JGLOBAL_OFFLINE_ATMOS_ANALYSIS",
        "JGCDAS_SURFACE_INITIALIZE": "JGLOBAL_ATMOS_SFCANL",
        "JGCDAS_AERO_ANALYSIS_INITIALIZE": "JGLOBAL_AERO_ANALYSIS_INITIALIZE",
        "JGCDAS_AERO_ANALYSIS_VARIATIONAL": "JGLOBAL_AERO_ANALYSIS_VARIATIONAL",
        "JGCDAS_AERO_ANALYSIS_FINALIZE": "JGLOBAL_AERO_ANALYSIS_FINALIZE",
        "JGCDAS_AERO_ANALYSIS_CALC": "JGLOBAL_ATMOS_ANALYSIS_CALC",
        "JGCDAS_AERO_ANALYSIS_STATS": "JGLOBAL_ANALYSIS_STATS",
        "JGCDAS_AERO_ANALYSIS_GENERATE_BMATRIX": "JGDAS_AERO_ANALYSIS_GENERATE_BMATRIX",
        # JGCDAS_PREPARE_OBS is taken from ObsForge for v1, not in global-workflow, do this manually!!
        # need to add something here for the post job once Yaping's PR is in
    }

    job_file_copy_list = []
    for dest_job, src_job in {**gcafs_jobs, **gcdas_jobs}.items():
        src_job_path = os.path.join(global_workflow_dir, 'dev', 'jobs', src_job)
        dest_job_path = os.path.join(global_workflow_dir, 'jobs', dest_job)
        job_file_copy_list.append((src_job_path, dest_job_path))

    # Create a FileHandler dictionary
    job_file_handler = {
        'mkdir': [os.path.join(global_workflow_dir, 'jobs')],
        'copy': job_file_copy_list,
    }
    # Execute the file operations
    FileHandler(job_file_handler).sync()

    return job_file_copy_list


def copy_script_files(global_workflow_dir):
    """
    Copy script files from dev/scripts to scripts directory with appropriate renaming.

    Parameters
    ----------
    global_workflow_dir : str
        Path to the global workflow directory

    Returns
    -------
    list
        List of tuples containing (src_path, dest_path) for copied files
    """
    gcafs_ex_scripts = {
        "exgcafs_forecast.sh": "exglobal_forecast.sh",
        "exgcafs_prep_emissions.sh": "exglobal_prep_emissions.py",
        "exgcafs_atmos_post_manager.sh": "exglobal_atmos_pmgr.sh",
        "exgcafs_atmos_products.sh": "exglobal_atmos_products.sh",
    }
    gcdas_ex_scripts = {
        "exgcdas_forecast.sh": "exglobal_forecast.sh",
        "exgcdas_prep_emissions.sh": "exglobal_prep_emissions.py",
        "exgcdas_atmos_post_manager.sh": "exglobal_atmos_pmgr.sh",
        "exgcdas_atmos_products.sh": "exglobal_atmos_products.sh",
        "exgcdas_atmos_initialize.py": "exglobal_offline_atmos_analysis.py",
        "exgcdas_surface_initialize.sh": "exglobal_atmos_sfcanl.sh",
        "exgcdas_aero_analysis_initialize.py": "exglobal_aero_analysis_initialize.py",
        "exgcdas_aero_analysis_variational.py": "exglobal_aero_analysis_variational.py",
        "exgcdas_aero_analysis_finalize.py": "exglobal_aero_analysis_finalize.py",
        "exgcdas_aero_analysis_calc.sh": "exglobal_atmos_analysis_calc.sh",
        "exgcdas_aero_analysis_stats.py": "exglobal_analysis_stats.py",
        "exgcdas_aero_analysis_generate_bmatrix.py": "exgdas_aero_analysis_generate_bmatrix.py",
        # exgcdas_prepare_obs is taken from ObsForge for v1, not in global-workflow, do this manually!!
        # need to add something here for the post job once Yaping's PR is in
    }

    # if the scripts directory exists as a symlink, remove it first
    scripts_dir = os.path.join(global_workflow_dir, 'scripts')
    if os.path.islink(scripts_dir):
        os.unlink(scripts_dir)
    ex_script_file_copy_list = []
    for dest_script, src_script in {**gcafs_ex_scripts, **gcdas_ex_scripts}.items():
        src_script_path = os.path.join(global_workflow_dir, 'dev', 'scripts', src_script)
        dest_script_path = os.path.join(global_workflow_dir, 'scripts', dest_script)
        ex_script_file_copy_list.append((src_script_path, dest_script_path))

    # Create a FileHandler dictionary for scripts
    ex_script_file_handler = {
        'mkdir': [os.path.join(global_workflow_dir, 'scripts')],
        'copy': ex_script_file_copy_list,
    }
    # Execute the file operations for scripts
    FileHandler(ex_script_file_handler).sync()

    return ex_script_file_copy_list


def remove_unused_executables(global_workflow_dir):
    """
    Remove unused executables from the exec directory.

    Parameters
    ----------
    global_workflow_dir : str
        Path to the global workflow directory

    Returns
    -------
    list
        List of files that were successfully removed
    """
    unused_executables = [
        "gdas_apply_incr.x",
        "gdas_fv3jedi_correction_increment.x",
        "gdas_fv3jedi_ensemble_add_increment.x",
        "gdas_fv3jedi_fv3inc.x",
        "gdas_fv3jedi_land_ensrecenter.x",
        "gdas_fv3jedi_scf_to_ioda.x",
        "gdas_ioda_mean.x",
        "gdas_soca_anpproc.x",
        "gdas_soca_diagb.x",
        "gdas_soca_diagnostics.x",
        "gdas_soca_ens_handler.x",
        "gdas_soca_error_covariance_toolbox.x",
        "gdas_soca_gridgen.x",
        "gdas_soca_hybridweights.x",
        "gdas_soca_incr_handler.x",
        "gdas_soca_obsstats.x",
        "gdas_soca_setcorscales.x",
        "gdas_soca_to_fv3.x",
        "emcsfc_snow2mdl",
        "emcsfc_ice_blend",
        "calc_increment_ens.x",
        "ensadd.x",
        "ensppf.x",
        "ensstat.x",
        "fbwndgfs.x",
        "fregrid",
        "getsfcensmeanp.x",
        "getsigensmeanp_smooth.x",
        "getsigensstatp.x",
        "gfs_bufr.x",
        "mkgfsawps.x",
        "ocnicepost.x",
        "overgridid.x",
        "oznmon_horiz.x",
        "oznmon_time.x",
        "radmon_angle.x",
        "radmon_bcoef.x",
        "radmon_bcor.x",
        "rdbfmsua.x",
        "radmon_time.x",
        "recentersigp.x",
        "regridStates.x",
        "supvit.x",
        "syndat_getjtbul.x",
        "syndat_maksynrc.x",
        "syndat_qctropcy.x",
        "tave.x",
        "tocsbufr.x",
        "vint.x",
        "wave_stat.x",
        "webtitle.x"
    ]

    exec_dir = os.path.join(global_workflow_dir, 'exec')
    removed_files = []

    for executable in unused_executables:
        executable_path = os.path.join(exec_dir, executable)
        if os.path.exists(executable_path):
            try:
                os.remove(executable_path)
                removed_files.append(executable)
                print(f"Removed unused executable: {executable}")
            except OSError as e:
                print(f"Error removing {executable}: {e}")
        else:
            print(f"Executable not found (already removed?): {executable}")

    return removed_files


def setup_gcafs_for_nco():
    # first, copy jobs from dev to the global workflow directory
    job_file_copy_list = copy_job_files(global_workflow_dir)

    # Next, copy ex-scripts from dev/scripts to the global workflow directory
    ex_script_file_copy_list = copy_script_files(global_workflow_dir)

    # Remove unused executables from the exec directory
    removed_files = remove_unused_executables(global_workflow_dir)

    # Extract templates for declare_from_tmpl replacement
    templates = get_template_dict(global_workflow_dir)

    # Go through the copied job and ex-script files and replace FOOgfs with FOOgcafs
    all_copied_files = [dest for _, dest in job_file_copy_list + ex_script_file_copy_list]
    for file_path in all_copied_files:
        num_replacements = replace_gfs_with_gcafs(file_path)
        print(f"Modified {file_path}: {num_replacements} replacements made.")

        # For job files, also replace declare_from_tmpl with explicit exports
        if '/jobs/' in file_path:
            num_tmpl_replacements = replace_declare_from_tmpl_in_file(file_path, templates)
            print(f"Replaced {num_tmpl_replacements} declare_from_tmpl calls in {file_path}")

            # Ensure common variables are defined even for single member or deterministic runs
            with open(file_path, 'r') as f:
                content = f.read()

            vars_to_define = ['MEMDIR', 'COMINgcafs', 'COMOUTgcafs']
            modified = False
            for var in vars_to_define:
                if var in content and f'export {var}=' not in content:
                    # Insert after jjob_header.sh source
                    header_pattern = r'(source\s+.*jjob_header\.sh.*)'
                    match = re.search(header_pattern, content)
                    if match:
                        content = re.sub(header_pattern, f'\\1\nexport {var}=${{{var}:-""}}', content)
                        modified = True
                        print(f"Added {var} export to {file_path}")

            if modified:
                with open(file_path, 'w') as f:
                    f.write(content)


if __name__ == "__main__":
    setup_gcafs_for_nco()
