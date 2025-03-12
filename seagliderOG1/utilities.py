# Based on https://github.com/voto-ocean-knowledge/votoutils/blob/main/votoutils/utilities/utilities.py
import re
import numpy as np
import pandas as pd
import logging
import subprocess
import datetime
import xarray as xr
#from votoutils.upload.sync_functions import sync_script_dir

_log = logging.getLogger(__name__)


def _reorder_attributes(ds, ordered_list):
    """
    Reorders the attributes of the given xarray Dataset to the given order.
    Parameters:
    ds (xarray.Dataset): The dataset to reorder the attributes of.
    ordered_list (list): The list of attribute names in the desired order.
    Returns:
    xarray.Dataset: The dataset with the attributes reordered.
    Notes:
    - The attributes not in the given ordered_list are appended at the end in the order they appear in the dataset.
    """

    new_attributes = ds.attrs
    # Reorder attributes according to vocabularies.order_of_attr
    ordered_attributes = {attr: new_attributes[attr] for attr in ordered_list if attr in new_attributes}

    # Add any remaining attributes that were not in the order_of_attr list
    for attr in new_attributes:
        if attr not in ordered_attributes:
            ordered_attributes[attr] = new_attributes[attr]
    ds.attrs = ordered_attributes

    return ds

def _validate_coords(ds1):
    """
    Validates and assigns coordinates to the given xarray Dataset.
    Parameters:
    ds1 (xarray.Dataset): The dataset to validate and assign coordinates to. 
                          It is expected to have an 'id' attribute and may contain 
                          'longitude', 'latitude', 'ctd_time', and 'ctd_depth' variables.
    Returns:
    xarray.Dataset: The validated dataset with necessary coordinates assigned. 
                    If 'ctd_time' variable is missing, an empty dataset is returned.
    Notes:
    - If 'longitude' or 'latitude' coordinates are missing, they are added as NaNs with the length of 'sg_data_point'.
    - If 'ctd_time' variable exists but 'ctd_time' or 'ctd_depth' coordinates are missing, they are assigned from the variable.
    - If 'ctd_time' variable is missing, an empty dataset is returned.
    - Prints messages indicating the actions taken for missing coordinates or variables.

    Based on: https://github.com/pydata/xarray/issues/3743
    """

    id = ds1.attrs['id']
    if 'longitude' not in ds1.coords:
        ds1 = ds1.assign_coords(longitude=("sg_data_point", [float('nan')] * ds1.dims['sg_data_point']))
        _log.warning(f"{id}: No coord longitude - adding as NaNs to length of sg_data_point")
    if 'latitude' not in ds1.coords:
        ds1 = ds1.assign_coords(latitude=("sg_data_point", [float('nan')] * ds1.dims['sg_data_point']))
        _log.warning(f"{id}: No coord latitude - adding as NaNs to length of sg_data_point")
    if 'ctd_time' in ds1.variables:
        if 'ctd_time' not in ds1.coords:
            ds1 = ds1.assign_coords(ctd_time=("sg_data_point", ds1['ctd_time'].values))
            _log.warning(f"{id}: No coord ctd_time, but exists as variable - assigning coord from variable")    
        if 'ctd_depth' not in ds1.coords:
            ds1 = ds1.assign_coords(ctd_depth=("sg_data_point", ds1['ctd_depth'].values))
            _log.warning(f"{id}: No coord ctd_depth, but exists as variable - assigning coord from variable")
    else:
        _log.warning(f"{id}: No variable ctd_time - returning an empty dataset")

        ds1 = xr.Dataset()
    return ds1


def _validate_dims(ds, expected_dims='N_MEASUREMENTS'):
    dim_name = list(ds.dims)[0] # Should be 'N_MEASUREMENTS' for OG1
    if dim_name != expected_dims:
        _log.error(f"Dimension name '{dim_name}' is not {expected_dims}.")
        return False
#        raise ValueError(f"Dimension name '{dim_name}' is not {expected_dims}.")
    else:
        return True
    

def _parse_calibcomm(calstr, firstrun=False):

    # Parse for calibration date
    cal_date = calstr
    cal_date_before_keyword = cal_date
    cal_date_YYYYmmDD = 'Unknown'
    formats = ['%d%b%y', '%d-%b-%y', '%m/%d/%y', '%b/%d/%y', '%b-%d-%y', '%b%d%y', '%d%b%y', '%d%B%y']
    for keyword in ['calibration', 'calibrated']:
        if keyword in cal_date:
            cal_date_before_keyword = cal_date.split(keyword)[0].strip()
            cal_date = cal_date.split(keyword)[-1].strip()
            cal_date = cal_date.replace(' ', '')
            for fmt in formats:
                try:
                    cal_date_YYYYmmDD = datetime.datetime.strptime(cal_date,  fmt).strftime('%Y%m%d')
                    break  # Exit the loop if parsing is successful
                except ValueError:
                    continue  # Try the next format if parsing fails
            break  # Exit the outer loop if keyword is found

    if firstrun:
        _log.info(f"     --> produces {cal_date_YYYYmmDD}")

    # Parse for serial number of sensor
    serial_number = 'unknown'
    for keyword in ['s/n', 'S/N', 'SN', 'SBE#', 'SBE']:
        if keyword in cal_date_before_keyword:
            serial_match = cal_date_before_keyword.split(keyword)[-1].strip()
            serial_number = serial_match.replace(keyword, '').replace('/','').replace(',','').strip()
            break # Exit the outer loop if keyword is found

    if len(calstr)<5:
        serial_number = calstr
    if firstrun:
        _log.info(f"     --> produces serial_number {serial_number}")



    return cal_date_YYYYmmDD, serial_number

def _clean_time_string(time_str):
    return time_str.replace('_', '').replace(':', '').rstrip('Z').replace('-', '')

def _clean_anc_vars_list(ancillary_variables_str):
    ancillary_variables_str = re.sub(r"(\w)(sg_cal)", r"\1 \2", ancillary_variables_str)
    ancilliary_vars_list = ancillary_variables_str.split()
    ancilliary_vars_list = [var.replace('sg_cal_', '') for var in ancilliary_vars_list]
    return ancilliary_vars_list

def _assign_calval(sg_cal, anc_var_list):
    calval = {}
    for anc_var in anc_var_list:
        # Check if anc_var exists in sg_cal which was not the case in Robs dataset
        if anc_var in sg_cal:  
            var_value = sg_cal[anc_var].values.item()
            calval[anc_var] = var_value
        else:
            calval[anc_var] = 'Unknown'
    return calval