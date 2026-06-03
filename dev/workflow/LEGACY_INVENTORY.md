# Legacy File Inventory

## Purpose

This document inventories root-level directories and files that are candidates for removal or migration now that the immutable DAG deployment pipeline operates exclusively from `dev/`. Each entry is classified by its current status and whether it's safe to remove.

## Removed Legacy Files (from `dev/workflow/`)

The following files were removed as they are fully superseded by the `deploy.py` pipeline:

| Removed File | Was | Replaced By |
|--------------|-----|-------------|
| `setup_expt.py` | Interactive experiment setup | `deploy.py` → `deployment/pipeline.py` Stages 2+3 |
| `setup_workflow.py` | Rocoto/ecFlow XML generator | `deploy.py` → `deployment/pipeline.py` Stage 5 |
| `create_experiment.py` | Wrapper around setup_expt + setup_workflow | `deploy.py` (single command) |
| `hosts.py` | Host detection class | Pipeline reads `hosts/<platform>.yaml` directly |
| `workflow_suite.py` | ABC for suite generation | `deployment/dag_generator.py` |
| `setup_ecf.py` | Older ecFlow setup script | `deployment/dag_generator.py` |
| `applications/` | Application factory classes | Workflow YAMLs in `dev/parm/workflow/` |
| `ecflow/*.py` | ecFlow suite factory + definitions | `deployment/dag_generator.py` |
| `prod.yml` | Legacy prod workflow config | `dev/parm/workflow/*.yaml` |
| `ecflow_build.yml` | Legacy ecFlow build config | Pipeline Stage 5 |

**Note:** `dev/ci/scripts/utils/ci_utils.sh` and `dev/workflow/generate_workflows.sh` still reference `create_experiment.py`. These need migration to call `deploy.py` directly.

---

## Classification Legend

| Status | Meaning |
|--------|---------|
| ✅ **Superseded** | Fully replaced by `dev/` equivalent; safe to remove after validation |
| ⚠️ **Active** | Still referenced by pipeline or runtime code; needs migration first |
| 🔄 **Partial** | Some contents superseded, others still needed |
| 🔗 **Symlink** | Compatibility symlink; removable but low priority |

---

## Root-Level Directory Inventory

### ✅ `ecf/` — SUPERSEDED

**Contents:** `defs/`, `include/` (head.h, tail.h, envir-p1.h), `scripts/` (enkfgdas/, gdas/, gfs/), `setup_ecf_links.sh`

**Superseded by:** `dev/workflow/ecflow/templates/` (task.ecf.j2, head.h.j2, tail.h.j2, envsetup.h.j2). The pipeline generates per-task `.ecf` scripts and the `.def` file directly into `<EXPDIR>/ecf/` during Stage 5.

**Why it's legacy:** These are hand-maintained NCO ecFlow scripts from before the DAG_Generator existed. The pipeline does not reference this directory.

**Safe to remove:** Yes — after confirming no external NCO tooling reads from the repository's root `ecf/` (as opposed to the deployed EXPDIR's `ecf/`).

---

### ⚠️ `env/` — STILL ACTIVE (primary source)

**Contents:** 11 platform `.env` files (AWSPW, AZUREPW, CONTAINER, DERECHO, GAEAC6, GOOGLEPW, HERA, HERCULES, ORION, URSA, WCOSS2)

**Referenced by:** `dev/workflow/deployment/platform_conditioner.py` searches `env/${PLATFORM}.env` at the project root as the **primary** source (before falling back to `dev/env/`).

**Migration path:** Create `dev/env/` with these files; update `platform_conditioner.py` to look there first.

**Safe to remove:** No — pipeline will fail without it until migration is complete.

---

### ⚠️ `gempak/` — STILL ACTIVE (runtime)

**Contents:** `dictionaries/`, `fix/`, `ush/`

**Referenced by:** Multiple J-Jobs (`JGFS_ATMOS_GEMPAK`, `JGDAS_ATMOS_GEMPAK_META_NCDC`, `JGFS_ATMOS_GEMPAK_PGRB2_SPEC`, `JGLOBAL_WAVE_GEMPAK`) reference `${HOMEglobal}/gempak/` at runtime.

**Migration path:** Create `dev/gempak/` and update the file stager's `DEFAULT_SOURCE_TARGET_MAP` to include it. Then J-Jobs in the deployed EXPDIR reference `${HOMEglobal}/gempak/` which resolves to the EXPDIR copy.

**Safe to remove:** No — runtime J-Jobs depend on it. No `dev/gempak/` equivalent exists yet.

---

### ⚠️ `modulefiles/` — STILL ACTIVE (primary source)

**Contents:** 21 Lua modulefiles (gw_run.*.lua, gw_setup.*.lua, platform-specific variants)

**Referenced by:** `platform_conditioner.py`'s `stage_platform_modulefiles()` searches `modulefiles/` at project root as primary source.

**Migration path:** Create `dev/modulefiles/` with these files; update the platform conditioner search order.

**Safe to remove:** No — pipeline reads modulefiles from here.

---

### 🔄 `parm/` — PARTIALLY SUPERSEDED

**Contents:** 14 subdirectories: archive/, chem/, fetch/, gdas/, globus/, post/, prep_sfc/, product/, relo/, stage/, transfer/, ufs/, wave/, wmo/

**Superseded portions:**
- `parm/ufs/` — Fully superseded by `dev/parm/ufs/` (Jinja2 templates for FV3, MOM6, CICE, WW3, GOCART)
- `parm/ufs/MOM_input_*.IN` — Replaced by `dev/parm/ufs/ocean/MOM_input.j2`
- `parm/ufs/ice_in.IN` — Replaced by `dev/parm/ufs/ice/ice_in.j2`
- `parm/ufs/ww3_shel.nml.IN` — Replaced by `dev/parm/ufs/wave/ww3_shel.nml.j2`
- `parm/ufs/field_table_*` — Replaced by `dev/parm/ufs/fv3/field_table.j2`

**Still-active portions:**
- `parm/archive/` — Archive configuration (not yet migrated)
- `parm/chem/` — Populated via submodule copy from `sorc/nexus.fd/config/gocart/`
- `parm/post/` — Populated via submodule copy from `sorc/upp.fd/parm/`
- `parm/fetch/`, `parm/globus/`, `parm/prep_sfc/`, `parm/product/`, `parm/relo/`, `parm/stage/`, `parm/transfer/`, `parm/wave/`, `parm/wmo/` — Not yet migrated to `dev/parm/`

**Safe to remove:** Only `parm/ufs/` with its `.IN` files. The rest needs migration first.

---

### ✅ `ush/` — SUPERSEDED

**Contents:** ~77 shell/python/perl scripts + `python/pygfs/` subdirectory

**Superseded by:** `dev/ush/` which contains all the same scripts plus additional pipeline-specific ones (atomic_publish.sh, ecflow_helpers.sh, universal_wrapper.sh.j2, etc.).

**Why it's legacy:** The deployment pipeline stages from `dev/ush/` → `<EXPDIR>/ush/`. The root `ush/` is not referenced by any pipeline stage.

**Safe to remove:** Yes — the pipeline exclusively uses `dev/ush/`.

---

### ⚠️ `versions/` — STILL ACTIVE (runtime)

**Contents:** 20 files: build.*.ver, run.*.ver (per-platform), fix.ver, ic.ver, requirements_gcafs.txt, spack.ver

**Referenced by:** `dev/ush/load_modules.sh` sources `${HOMEglobal}/versions/run.ver` at runtime. The `file_stager.py` maps `dev/versions → versions` but `dev/versions/` doesn't exist yet.

**Migration path:** Create `dev/versions/` with these files. The pipeline will stage them into EXPDIR and the runtime reference `${HOMEglobal}/versions/run.ver` resolves correctly.

**Safe to remove:** No — runtime code depends on these files. Need to create `dev/versions/` first.

---

### 🔗 `scripts` (symlink at root) — TRANSITIONAL

**Type:** Symbolic link → `dev/scripts/`

**Purpose:** Compatibility shim so legacy code referencing `${HOMEglobal}/scripts/` still works during the transition period.

**Safe to remove:** Yes — the pipeline reads `dev/scripts/` directly. Any deployed EXPDIR has its own `scripts/` directory.

---

### ✅ `docs/` — KEEP (documentation)

**Contents:** Sphinx documentation source for ReadTheDocs

**Status:** Still needed for project documentation. Not a legacy artifact.

**Safe to remove:** No — active documentation.

---

## Files Superseded Within `parm/ufs/` (Safe to Delete)

These are the legacy `@[VAR]` atparse templates replaced by Jinja2:

| Legacy File | Replaced By |
|-------------|-------------|
| `parm/ufs/MOM_input_025.IN` | `dev/parm/ufs/ocean/MOM_input.j2` |
| `parm/ufs/MOM_input_050.IN` | `dev/parm/ufs/ocean/MOM_input.j2` |
| `parm/ufs/MOM_input_100.IN` | `dev/parm/ufs/ocean/MOM_input.j2` |
| `parm/ufs/MOM_input_500.IN` | `dev/parm/ufs/ocean/MOM_input.j2` |
| `parm/ufs/MOM6_data_table.IN` | `dev/parm/ufs/ocean/MOM6_data_table.j2` |
| `parm/ufs/ice_in.IN` | `dev/parm/ufs/ice/ice_in.j2` |
| `parm/ufs/ww3_shel.nml.IN` | `dev/parm/ufs/wave/ww3_shel.nml.j2` |
| `parm/ufs/input_global_nest.nml.IN` | `dev/parm/ufs/fv3/input_global_nest.nml.j2` |
| `parm/ufs/post_itag_gfs` | `dev/parm/ufs/post/post_itag.j2` |
| `parm/ufs/post_itag_gcafs` | `dev/parm/ufs/post/post_itag.j2` |
| `parm/ufs/field_table_*` (20+ variants) | `dev/parm/ufs/fv3/field_table.j2` |
| `parm/ufs/model_configure.IN` | `dev/parm/ufs/fv3/model_configure.j2` |
| `parm/ufs/input.nml.IN` | `dev/parm/ufs/fv3/input.nml.j2` |
| `parm/ufs/ufs.configure.*.IN` (7 variants) | `dev/parm/ufs/ufs.configure.j2` |
| `parm/ufs/diag_table` | `dev/parm/ufs/fv3/diag_table.j2` |
| `parm/ufs/AERO_HISTORY.rc` | `dev/parm/ufs/gocart/AERO_HISTORY.rc.j2` |

## Legacy Ush Scripts (Superseded by Deploy-Time Rendering)

| Legacy Script | Status |
|---------------|--------|
| `ush/parsing_namelists_FV3.sh` | Replaced by `dev/parm/ufs/fv3/input.nml.j2` |
| `ush/parsing_namelists_FV3_nest.sh` | Replaced by `dev/parm/ufs/fv3/input_global_nest.nml.j2` |
| `ush/parsing_namelists_MOM6.sh` | Replaced by `dev/parm/ufs/ocean/MOM_input.j2` |
| `ush/parsing_namelists_CICE.sh` | Replaced by `dev/parm/ufs/ice/ice_in.j2` |
| `ush/parsing_namelists_WW3.sh` | Replaced by `dev/parm/ufs/wave/ww3_shel.nml.j2` |
| `ush/parsing_namelists_GOCART.sh` | Replaced by `dev/parm/ufs/gocart/*.rc.j2` |
| `ush/parsing_model_configure_FV3.sh` | Replaced by `dev/parm/ufs/fv3/model_configure.j2` |
| `ush/parsing_ufs_configure.sh` | Replaced by `dev/parm/ufs/ufs.configure.j2` |
| `ush/atparse.bash` | atparse engine retired (Jinja2 only) |

---

## Recommended Migration Order

1. **Phase 1 (safe now):** Remove `ecf/`, root `ush/`, `scripts` symlink
2. **Phase 2 (create dev/ equivalents first):** Migrate `env/` → `dev/env/`, `versions/` → `dev/versions/`, `modulefiles/` → `dev/modulefiles/`
3. **Phase 3 (requires J-Job updates):** Migrate `gempak/` → `dev/gempak/`
4. **Phase 4 (selective):** Clean `parm/ufs/` of `.IN` files; migrate remaining `parm/` subdirs to `dev/parm/`

---

## Validation Before Removal

For any directory marked "safe to remove," run:

```bash
# Check no pipeline code references it
grep -r "ecf/" dev/workflow/ --include="*.py" | grep -v ".pyc"

# Check no test fixtures depend on it
grep -r "ecf/" dev/workflow/tests/ --include="*.py"

# Check no J-Jobs reference it at runtime
grep -r 'HOMEglobal.*ecf' dev/jobs/ dev/scripts/
```

Replace `ecf/` with the directory name being validated.
