# noqa: D100
from typing import Optional

import numpy as np
import xarray

from xclim.core.calendar import resample_doy
from xclim.core.units import (
    convert_units_to,
    declare_units,
    pint2cfunits,
    rate2amount,
    str2pint,
    to_agg_units,
)

from . import run_length as rl
from ._conversion import rain_approximation, snowfall_approximation
from ._threshold import first_day_above, first_day_below
from .generic import aggregate_between_dates

# Frequencies : YS: year start, QS-DEC: seasons starting in december, MS: month start
# See http://pandas.pydata.org/pandas-docs/stable/timeseries.html#offset-aliases

# -------------------------------------------------- #
# ATTENTION: ASSUME ALL INDICES WRONG UNTIL TESTED ! #
# -------------------------------------------------- #

__all__ = [
    "corn_heat_units",
    "corn_heat_units_accumulation",
]


@declare_units(
    tasmin="[temperature]",
    tasmax="[temperature]",
    thresh_tasmin="[temperature]",
    thresh_tasmax="[temperature]",
)
def corn_heat_units(
    tasmin: xarray.DataArray,
    tasmax: xarray.DataArray,
    thresh_tasmin: str = "4.44 degC",
    thresh_tasmax: str = "10 degC",
) -> xarray.DataArray:
    r"""Corn heat units.

    Temperature-based index used to estimate the development of corn crops.

    Parameters
    ----------
    tasmin : xarray.DataArray
      Minimum daily temperature.
    tasmax : xarray.DataArray
      Maximum daily temperature.
    thresh_tasmin : str
      The minimum temperature threshold needed for corn growth.
    thresh_tasmax : str
      The maximum temperature threshold needed for corn growth.

    Returns
    -------
    xarray.DataArray, [dimensionless]
      Daily corn heat units.

    Notes
    -----
    The thresholds of 4.44°C for minimum temperatures and 10°C for maximum temperatures were selected following
    the assumption that no growth occurs below these values.

    Let :math:`TX_{i}` and :math:`TN_{i}` be the daily maximum and minimum temperature at day :math:`i`. Then the daily
    corn heat unit is:

    .. math::
        CHU_i = \frac{YX_{i} + YN_{i}}{2}

    with

    .. math::

        YX_i & = 3.33(TX_i -10) - 0.084(TX_i -10)^2, &\text{if } TX_i > 10°C

        YN_i & = 1.8(TN_i -4.44), &\text{if } TN_i > 4.44°C

    where :math:`YX_{i}` and :math:`YN_{i}` is 0 when :math:`TX_i \leq 10°C` and :math:`TN_i \leq 4.44°C`, respectively.

    References
    ----------
    Equations from Bootsma, A., G. Tremblay et P. Filion. 1999: Analyse sur les risques associés aux unités thermiques
    disponibles pour la production de maïs et de soya au Québec. Centre de recherches de l’Est sur les céréales et
    oléagineux, Ottawa, 28 p.

    Can be found in Audet, R., Côté, H., Bachand, D. and Mailhot, A., 2012: Atlas agroclimatique du Québec. Évaluation
    des opportunités et des risques agroclimatiques dans un climat en évolution.
    """

    tasmin = convert_units_to(tasmin, "degC")
    tasmax = convert_units_to(tasmax, "degC")
    thresh_tasmin = convert_units_to(thresh_tasmin, "degC")
    thresh_tasmax = convert_units_to(thresh_tasmax, "degC")

    mask_tasmin = tasmin > thresh_tasmin
    mask_tasmax = tasmax > thresh_tasmax

    chu = (
        xarray.where(mask_tasmin, 1.8 * (tasmin - thresh_tasmin), 0)
        + xarray.where(
            mask_tasmax,
            (3.33 * (tasmax - thresh_tasmax) - 0.084 * (tasmax - thresh_tasmax) ** 2),
            0,
        )
    ) / 2

    chu.attrs["units"] = ""
    return chu


@declare_units(
    tasmin="[temperature]",
    tasmax="[temperature]",
    tas="[temperature]",
    thresh_tasmin="[temperature]",
    thresh_tasmax="[temperature]",
    seas_start_thresh="[temperature]",
    seas_end_thresh="[temperature]",
)
def corn_heat_units_accumulation(
    tasmin: xarray.DataArray,
    tasmax: xarray.DataArray,
    tas: xarray.DataArray,
    thresh_tasmin: str = "4.44 degC",
    thresh_tasmax: str = "10 degC",
    seas_start_window: int = 5,
    seas_end_window: int = 1,
    seas_start_thresh: str = "12.8 degC",
    seas_end_thresh: str = "-2 degC",
    freq: str = "YS",
) -> xarray.DataArray:
    r"""Corn heat units accumulation.

    Sum of the daily corn heat units over the corn growth season each year.

    The default season start/end thresholds and windows are valid for the province of Quebec.

    Parameters
    ----------
    tasmin : xarray.DataArray
      Minimum daily temperature.
    tasmax : xarray.DataArray
      Maximum daily temperature.
    tas : xarray.DataArray
      Mean daily temperature.
    thresh_tasmin : str
      The minimum temperature threshold needed for corn growth.
    thresh_tasmax : str
      The maximum temperature threshold needed for corn growth.
    seas_start_window : int
      Minimum number of days with temperature above threshold needed for the start of the growth season.
    seas_end_window : int
      Minimum number of days with temperature below threshold needed for the end of the growth season.
    seas_start_thresh : str
      The minimum temperature threshold needed for the start of the growth season.
    seas_end_thresh : str
      The minimum temperature threshold needed for the end of the growth season.
    freq : str
      Resampling frequency.

    Returns
    -------
    xarray.DataArray, [dimensionless]
      Sum of daily corn heat units over the corn growth season each year.

    Notes
    -----
    Let :math:`CHU_{ij}` be the daily corn heat units at day :math:`i` and period :math:`j`. Then the corn heat unit
    accumulation is the sum over a period between the start and the end dates of the corn growth season:

    .. math::
        CHU_j = \sum_i CHU_{ij}

    References
    ----------
    """

    chu = corn_heat_units(tasmin, tasmax, thresh_tasmin, thresh_tasmax)
    # last day of the window where tas >= {seas_start_thresh}
    start = first_day_above(
        tas, seas_start_thresh, window=seas_start_window, freq=freq
    ) + (seas_start_window - 1)
    end = first_day_below(tasmin, seas_end_thresh, window=seas_end_window, freq=freq)

    out = aggregate_between_dates(chu, start, end, op="sum", freq=freq)

    out.attrs["units"] = ""
    return out
