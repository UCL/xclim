# -*- coding: utf-8 -*-
# noqa: D205,D400
"""
Miscellaneous indices utilities
===============================

Helper functions for the indices computation, things that do not belong in neither
`xclim.indices.calendar`, `xclim.indices.fwi`, `xclim.indices.generic` or `xclim.indices.run_length`.
"""
from collections import defaultdict
from enum import IntEnum
from functools import partial
from inspect import Parameter
from types import FunctionType
from typing import Any, Callable, Dict, List, NewType, Optional, Sequence, Union

import numpy as np
import xarray as xr
from boltons.funcutils import update_wrapper
from dask import array as dsk
from xarray import DataArray, Dataset

#: Type annotation for strings representing full dates (YYYY-MM-DD), may include time.
DateStr = NewType("DateStr", str)

#: Type annotation for strings representing dates without a year (MM-DD).
DateOfYearStr = NewType("DateOfYearStr", str)


def wrapped_partial(
    func: FunctionType, suggested: Optional[dict] = None, **fixed
) -> Callable:
    """Wrap a function, updating its signature but keeping its docstring.

    Parameters
    ----------
    func : FunctionType
        The function to be wrapped
    suggested : dict
        Keyword arguments that should have new default values
        but still appear in the signature.
    fixed : kwargs
        Keyword arguments that should be fixed by the wrapped
        and removed from the signature.

    Examples
    --------
    >>> from inspect import signature
    >>> def func(a, b=1, c=1):
    ...     print(a, b, c)
    >>> newf = wrapped_partial(func, b=2)
    >>> signature(newf)
    <Signature (a, *, c=1)>
    >>> newf(1)
    1 2 1
    >>> newf = wrapped_partial(func, suggested=dict(c=2), b=2)
    >>> signature(newf)
    <Signature (a, *, c=2)>
    >>> newf(1)
    1 2 2
    """
    suggested = suggested or {}
    partial_func = partial(func, **suggested, **fixed)

    fully_wrapped = update_wrapper(
        partial_func, func, injected=list(fixed.keys()), hide_wrapped=True
    )
    return fully_wrapped


# TODO Reconsider the utility of this
def walk_map(d: dict, func: FunctionType):
    """Apply a function recursively to values of dictionary.

    Parameters
    ----------
    d : dict
      Input dictionary, possibly nested.
    func : FunctionType
      Function to apply to dictionary values.

    Returns
    -------
    dict
      Dictionary whose values are the output of the given function.
    """
    out = {}
    for k, v in d.items():
        if isinstance(v, (dict, defaultdict)):
            out[k] = walk_map(v, func)
        else:
            out[k] = func(v)
    return out


class ValidationError(ValueError):
    """xclim ValidationError class."""

    @property
    def msg(self):  # noqa
        return self.args[0]


class MissingVariableError(ValueError):
    """xclim Variable missing from dataset error."""


def ensure_chunk_size(da: xr.DataArray, max_iter: int = 10, **minchunks: int):
    """Ensure that the input dataarray has chunks of at least the given size.

    If only one chunk is too small, it is merged with an adjacent chunk.
    If many chunks are too small, they are grouped together by merging adjacent chunks.

    Parameters
    ----------
    da : xr.DataArray
      The input dataarray, with or without the dask backend. Does nothing when passed a non-dask array.
    **minchunks : Mapping[str, int]
      A kwarg mapping from dimension name to minimum chunk size.
      Pass -1 to force a single chunk along that dimension.
    """
    if not isinstance(da.data, dsk.Array):
        return da

    all_chunks = dict(zip(da.dims, da.chunks))
    chunking = dict()
    for dim, minchunk in minchunks.items():
        chunks = all_chunks[dim]
        if minchunk == -1 and len(chunks) > 1:
            # Rechunk to single chunk only if it's not already one
            chunking[dim] = -1

        toosmall = np.array(chunks) < minchunk  # Chunks that are too small
        if toosmall.sum() > 1:
            # Many chunks are too small, merge them by groups
            fac = np.ceil(minchunk / min(chunks)).astype(int)
            chunking[dim] = tuple(
                sum(chunks[i : i + fac]) for i in range(0, len(chunks), fac)
            )
            # Reset counter is case the last chunks are still too small
            chunks = chunking[dim]
            toosmall = np.array(chunks) < minchunk
        if toosmall.sum() == 1:
            # Only one, merge it with adjacent chunk
            ind = np.where(toosmall)[0][0]
            new_chunks = list(chunks)
            sml = new_chunks.pop(ind)
            new_chunks[max(ind - 1, 0)] += sml
            chunking[dim] = tuple(new_chunks)

    if chunking:
        return da.chunk(chunks=chunking)
    return da


def _calc_perc(arr, p=[50]):
    """Ufunc-like computing a percentile over the last axis of the array.

    Processes cases with invalid values separately, which makes it more efficent than np.nanpercentile for array with only a few invalid points.

    Parameters
    ----------
    arr : np.array
        Percentile is computed over the last axis.
    p : sequence of floats
        Percentile to compute, between 0 and 100. (the default is 50)

    Returns
    -------
    np.array
    """
    nan_count = np.isnan(arr).sum(axis=-1)
    out = np.moveaxis(np.percentile(arr, p, axis=-1), 0, -1)
    nans = (nan_count > 0) & (nan_count < arr.shape[-1])
    if np.any(nans):
        out_mask = np.stack([nans] * len(p), axis=-1)
        # arr1 = arr.reshape(int(arr.size / arr.shape[-1]), arr.shape[-1])
        # only use nanpercentile where we need it (slow performance compared to standard) :
        out[out_mask] = np.moveaxis(
            np.nanpercentile(arr[nans], p, axis=-1), 0, -1
        ).ravel()
    return out


class InputKind(IntEnum):
    """Constants for input parameter kinds.

    For use by external parses to determine what kind of data the indicator expects.
    On the creation of an indicator, the appropriate constant is stored in `Indicator.parameters[<varname>]['kind']`.

    For developpers : for each constant, the docstring specifies the annotation a parameter of an indice function
    should use in order to be picked up by the indicator constructor.
    """

    #: A data variable (DataArray or variable name).
    #: Annotation : `xr.DataArray`.
    VARIABLE = 0
    #: An optional data variable (DataArray or variable name).
    #: Annotation : `xr.DataArray` or `Optional[xr.DataArray]`.
    OPTIONAL_VARIABLE = 1
    #: A string representing a quantity with units.
    #: Annotation : `str` +  an entry in the `declare_units` decorator.
    QUANTITY_STR = 2
    #: A string representing an "offset alias", as defined by pandas (see https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#offset-aliases).
    #: Annotation : `str` + `freq` as the parameter name.
    FREQ_STR = 3
    #: A number.
    #: Annotation : `int`, `float` and Union's and optional's thereof.
    NUMBER = 4
    #: A simple string.
    #: Annotation : `str` or `Optional[str]`. In most cases, this kind of parameter makes sense with choices indicated
    #: in the docstring's version of the annotation with curly braces. See [Defining new indices](notebooks/customize.ipynb#Defining-new-indices).
    STRING = 5
    #: A calendar date without a year in the MM-DD format.
    #: Annotation : `xclim.core.utils.DateOfYearStr` (may be optional).
    DATE_OF_YEAR = 6
    #: A date in the YYYY-MM-DD format, may include a time (HH:MM:SS).
    #: Annotation : `xclim.core.utils.DateStr` (may be optional).
    DATE = 7
    #: A sequence of numbers
    #: Annotation : `Sequence[int]`, `Sequence[float]` and Union thereof, including single `int` and `float`.
    NUMBER_SEQUENCE = 8
    #: A mapping from argument name to value.
    #: Developpers : maps the "**kwargs"". Please use as little as possible.
    KWARGS = 50
    #: An xarray dataset.
    #: Developers : as indices only accept DataArrays, this should only be added on the indicator's initialization.
    DATASET = 70
    #: An object that fits None of the previous kinds. Returned for variadic keyword arguments (**kwargs).
    #: Developers : This the fallback kind and should be avoided as much as possible.
    OTHER_PARAMETER = 99


def _typehint_is_in(hint, hints):
    """Returns whether the first argument is in the other arguments.

    If the first arg is an Union of several typehints, this returns True only
    if all the members of that Union are in the given list.
    """
    # This code makes use of the "set-like" property of Unions and Optionals:
    # Optional[X, Y] == Union[X, Y, None] == Union[X, Union[X, Y], None] etc.
    return Union[(hint,) + tuple(hints)] == Union[tuple(hints)]


def infer_kind_from_parameter(param: Parameter, has_units: bool = False) -> InputKind:
    """Returns the approprite InputKind constant from an inspect.Parameter object.

    The correspondance between parameters and kinds is documented in :py:class:`InputKind`.
    The only information not inferable through the inspect object is whether the parameter
    has been assigned units through the :py:function:`xclim.core.units.declare_units` decorator.
    That can be given with the `has_units` flag.
    """
    if (
        param.annotation in [DataArray, Union[DataArray, str]]
        and param.default is not None
    ):
        return InputKind.VARIABLE

    if (
        Optional[param.annotation]
        in [Optional[DataArray], Optional[Union[DataArray, str]]]
        and param.default is None
    ):
        return InputKind.OPTIONAL_VARIABLE

    if _typehint_is_in(param.annotation, (str, None)) and has_units:
        return InputKind.QUANTITY_STR

    if param.name == "freq":
        return InputKind.FREQ_STR

    if _typehint_is_in(param.annotation, (None, int, float)):
        return InputKind.NUMBER

    if _typehint_is_in(
        param.annotation, (None, int, float, Sequence[int], Sequence[float])
    ):
        return InputKind.NUMBER_SEQUENCE

    if _typehint_is_in(param.annotation, (None, str)):
        return InputKind.STRING

    if _typehint_is_in(param.annotation, (None, DateOfYearStr)):
        return InputKind.DATE_OF_YEAR

    if _typehint_is_in(param.annotation, (None, DateStr)):
        return InputKind.DATE

    if _typehint_is_in(param.annotation, (None, Dataset)):
        return InputKind.DATASET

    if param.kind == param.VAR_KEYWORD:
        return InputKind.KWARGS

    return InputKind.OTHER_PARAMETER
