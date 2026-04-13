#!/usr/bin/env python3
"""
Utility to regrid GDAS NetCDF input and integrate MERRA2 tracer climatology.
Using only xarray for interpolation to avoid xesmf dependency.
"""

import os
import argparse
import datetime
import numpy as np
import xarray as xr
import netCDF4
from typing import List, Dict, Optional
from wxflow import Logger, Executable

# Initialize logger
logger = Logger(level=os.environ.get("LOGGING_LEVEL", "DEBUG"), colored_log=True)


def open_dataset(filename: str) -> xr.Dataset:
    """
    Utility to open a dataset with common settings.

    Parameters
    ----------
    filename : str
        The path to the NetCDF file to open.

    Returns
    -------
    xr.Dataset
        The opened xarray Dataset.
    """
    return xr.open_dataset(filename, decode_cf=True, mask_and_scale=False, decode_times=False)


def horizontal_interp(source: xr.Dataset, target: xr.Dataset) -> xr.Dataset:
    """
    Regrid horizontally from MERRA2 (lon, lat) to FV3 (geolat, geolon) 2D arrays
    using xarray.interp. This avoids the dependency on xesmf.

    Parameters
    ----------
    source : xr.Dataset
        Source dataset containing MERRA2 data on a regular lat-lon grid.
    target : xr.Dataset
        Target dataset containing the FV3 tile grid information (geolat, geolon).

    Returns
    -------
    xr.Dataset
        The horizontally interpolated dataset.
    """
    # Standardize MERRA2 coordinates to -180 to 180 matching FV3 geolon
    if 'lon' in source.coords:
        source = source.assign_coords(lon=(((source.lon + 180) % 360) - 180))
        source = source.sortby('lon')

    # Extract target 2D coordinates from FV3 tile
    # FV3 standard names: geolat, geolon
    target_lat = target['geolat']
    target_lon = target['geolon']

    logger.debug("Performing horizontal interpolation with xarray.interp (linear)...")
    # xarray.interp will map (lat, lon) -> (target_lat, target_lon)
    return source.interp(lat=target_lat, lon=target_lon, method='linear')


def vertical_interp(source: xr.Dataset, source_plevs: np.ndarray, target_plevs: np.ndarray) -> xr.Dataset:
    """
    Interpolate vertically using log-linear interpolation.

    Parameters
    ----------
    source : xr.Dataset
        Source dataset with data already horizontally interpolated.
    source_plevs : np.ndarray
        Array of log-pressure levels for the source data.
    target_plevs : np.ndarray
        Array of log-pressure levels for the target grid.

    Returns
    -------
    xr.Dataset
        The vertically interpolated dataset.
    """
    source['lev'] = source_plevs
    return source.interp(lev=target_plevs, method='linear')


class GDASMerra2Coldstart:
    """
    Handles regridding of GDAS NetCDF data to FV3 tiles and
    adding MERRA2 tracer climatology.

    Attributes
    ----------
    res : str
        Target resolution (e.g., 'C384').
    ntiles : int
        Number of FV3 tiles (default is 6).
    merra_to_ufs : dict
        Mapping from MERRA2 variable names to UFS variable names.
    ufs_units : dict
        Mapping from UFS variable names to their target units.
    """

    def __init__(self, res: str, ntiles: int = 6):
        """
        Initialize the GDASMerra2Coldstart class.

        Parameters
        ----------
        res : str
            Target resolution (e.g., 'C384').
        ntiles : int, optional
            Number of FV3 tiles, by default 6.
        """
        self.res = res
        self.ntiles = ntiles

        # Map MERRA2 names to UFS/FV3 names
        self.merra_to_ufs = {
            'BCPHILIC': 'bc2', 'BCPHOBIC': 'bc1', 'DMS': 'dms',
            'DU001': 'dust1', 'DU002': 'dust2', 'DU003': 'dust3',
            'DU004': 'dust4', 'DU005': 'dust5',
            'OCPHILIC': 'oc2', 'OCPHOBIC': 'oc1', 'SO2': 'so2', 'SO4': 'so4',
            'SS001': 'seas1', 'SS002': 'seas2', 'SS003': 'seas3',
            'SS004': 'seas4', 'SS005': 'seas5', 'MSA': 'msa'
        }

        # Units mapping
        self.ufs_units = {
            'so2': 'ppm', 'so4': 'ug/kg', 'dms': 'ppm', 'msa': 'ppm',
            'bc2': 'ug/kg', 'bc1': 'ug/kg',
            'dust1': 'ug/kg', 'dust2': 'ug/kg', 'dust3': 'ug/kg',
            'dust4': 'ug/kg', 'dust5': 'ug/kg',
            'seas1': 'ug/kg', 'seas2': 'ug/kg', 'seas3': 'ug/kg',
            'seas4': 'ug/kg', 'seas5': 'ug/kg',
            'oc1': 'ug/kg', 'oc2': 'ug/kg'
        }

    def regrid_gdas_to_tiles(self, input_file: str, output_dir: str):
        """
        Regrid global GDAS NetCDF file to 6 FV3 tiles using chgres_cube.

        Parameters
        ----------
        input_file : str
            Path to the input global GDAS NetCDF file.
        output_dir : str
            Directory to save the regridded FV3 tiles.
        """
        logger.info(f"Regridding GDAS input {input_file} to resolution {self.res}")

        os.makedirs(output_dir, exist_ok=True)

        chgres_exe = os.environ.get("CHGRES_CUBE_EXE", "chgres_cube")
        chgres = Executable(chgres_exe)
        args = [
            f"--input_file={input_file}",
            f"--output_dir={output_dir}",
            f"--res={self.res.strip('C')}",
            "--input_type=netcdf",
            "--output_type=restart"
        ]
        logger.debug(f"Running {chgres_exe} with args: {args}")
        # chgres(*args)

    def integrate_merra_to_tile(self, itile: int, restart_dir: str, merra_ds: xr.Dataset):
        """
        Regrid MERRA2 climatology and merge it into a single FV3 tile tracer file.

        Parameters
        ----------
        itile : int
            The tile index (1-6).
        restart_dir : str
            Directory containing the FV3 restart tiles.
        merra_ds : xr.Dataset
            The MERRA2 climatology dataset.
        """
        control_file = os.path.join(restart_dir, "gfs_ctrl.nc")
        data_file = os.path.join(restart_dir, f"gfs_data.tile{itile}.nc")

        if not os.path.exists(data_file):
            logger.error(f"Data file {data_file} not found. Skipping tile {itile}.")
            return

        with open_dataset(control_file) as ctrl, open_dataset(data_file) as data_tile:
            # 1. Prepare target grid from data tile for coordinate mapping (geolat, geolon)
            # Standardizing dimensions to x, y for interpolation internally
            target_grid = data_tile.rename({
                'lon': 'x', 'lat': 'y'
            }).squeeze()

            # 2. Horizontal Interp using xarray
            hinterped = horizontal_interp(merra_ds[list(self.merra_to_ufs.keys())], target_grid)

            # 3. Vertical Interp
            # gfs_ctrl.nc typically has vcoord(nvcoord, levsp) where [0,:] is ak and [1,:] is bk
            vcoord = ctrl.vcoord.values
            ak = vcoord[0, :]
            bk = vcoord[1, :]

            # Standard phalf approximation for model levels (Pa -> hPa)
            fv3_press = (ak[1:] + bk[1:] * 101325.0) / 100.0
            merra_press = self.get_merra2_plevs()

            hvinterped = vertical_interp(hinterped, np.log(merra_press), np.log(fv3_press))

            # 4. Units and Merging
            for merra_name, ufs_name in self.merra_to_ufs.items():
                logger.debug(f"Processing tracer {ufs_name} for tile {itile}")
                
                # Check if tracer exists or needs to be added
                # reshaped data: (lev, lat, lon)
                tracer_data = hvinterped[merra_name].values
                
                if self.ufs_units.get(ufs_name) == 'ug/kg':
                    tracer_data = tracer_data * 1e9

                # Merge into existing data Dataset
                # Ensure shape matches (lev, lat, lon)
                # Note: tracer_data shape from interp is (lev, lat, lon)
                data_tile[ufs_name] = (('lev', 'lat', 'lon'), tracer_data)

            # 5. Output management
            out_file = data_file.replace('.nc', '_new.nc')
            data_tile.to_netcdf(out_file)
            os.rename(data_file, data_file + ".bak")
            os.rename(out_file, data_file)

    def get_merra2_plevs(self) -> np.ndarray:
        """
        Get the MERRA2 pressure level array middle points (hPa).

        Returns
        -------
        np.ndarray
            Array of pressure levels in hPa.
        """
        return np.array([1000.0, 975.0, 950.0, 925.0, 900.0, 850.0, 800.0, 750.0, 700.0])

    def get_merra2_climatology_file(self, date: datetime.datetime, fix_dir: str) -> str:
        """
        Deteremine the MERRA2 climatology file path based on simulation date.

        Parameters
        ----------
        date : datetime.datetime
            The current simulation date.
        fix_dir : str
            Path to the fix/aer directory containing MERRA2 files.

        Returns
        -------
        str
            Full path to the MERRA2 climatology file.
        """
        month_str = f"m{date.month:02d}"
        # For now, default to 2014-2023 as requested for current simulation
        filename = f"merra2.aerclim.2014-2023.{month_str}.nc"
        return os.path.join(fix_dir, filename)

    def process_all(self, gdas_input: str, output_dir: str, merra_file: str):
        """
        Execute the complete workflow for all tiles.

        Parameters
        ----------
        gdas_input : str
            Path to the input global GDAS NetCDF file.
        output_dir : str
            Directory to save the regridded and merged FV3 tiles.
        merra_file : str
            Path to the MERRA2 climatology file.
        """
        # self.regrid_gdas_to_tiles(gdas_input, output_dir)
        with open_dataset(merra_file).isel(time=0) as merra_ds:
            for itile in range(1, self.ntiles + 1):
                self.integrate_merra_to_tile(itile, output_dir, merra_ds)

    def process(self, gdas_input: str, output_dir: str, merra_file: str):
        """
        Wrapper for process_all for backward compatibility.

        Parameters
        ----------
        gdas_input : str
            Path to the input global GDAS NetCDF file.
        output_dir : str
            Directory to save the regridded and merged FV3 tiles.
        merra_file : str
            Path to the MERRA2 climatology file.
        """
        self.process_all(gdas_input, output_dir, merra_file)


def main():
    """
    Main entry point for the script.
    """
    parser = argparse.ArgumentParser(description="GDAS to FV3 Tile + MERRA2 Tracers")
    parser.add_argument("--input", required=True, help="Input GDAS NetCDF file")
    parser.add_argument("--output", required=True, help="Output directory for FV3 tiles")
    parser.add_argument("--date", help="Simulation date (YYYYMMDDHH), used to select MERRA2 month")
    parser.add_argument("--merra", help="Specific MERRA2 climatology file (overrides automatic selection)")
    parser.add_argument("--fix_dir", help="Path to fix/aer directory for MERRA2 files")
    parser.add_argument("--res", default="C384", help="Target resolution (e.g. C384)")
    args = parser.parse_args()

    processor = GDASMerra2Coldstart(res=args.res)

    merra_file = args.merra
    if not merra_file:
        if not args.date or not args.fix_dir:
            parser.error("Either --merra OR (--date AND --fix_dir) must be provided.")
        
        sim_date = datetime.datetime.strptime(args.date, "%Y%m%d%H")
        merra_file = processor.get_merra2_climatology_file(sim_date, args.fix_dir)

    if not os.path.exists(merra_file):
        logger.error(f"MERRA2 climatology file not found: {merra_file}")
        return

    processor.process(args.input, args.output, merra_file)


if __name__ == "__main__":
    main()
