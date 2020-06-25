from xclim.core.cfchecks import check_valid
from xclim.core.indicator import Daily
from xclim.core.utils import wrapped_partial
from xclim.indices import base_flow_index
from xclim.indices import generic


__all__ = ["base_flow_index", "freq_analysis", "stats", "fit", "doy_qmax", "doy_qmin"]


class Streamflow(Daily):
    context = "hydro"
    units = "m^3 s-1"
    standard_name = "discharge"

    @staticmethod
    def cfcheck(q):
        check_valid(q, "standard_name", "water_volume_transport_in_river_channel")


class Stats(Streamflow):
    missing = "any"


# Disable the missing value check because the output here is not a time series.
class FA(Streamflow):
    missing = "skip"


# Disable the daily checks because the inputs are period extremas.
class Fit(FA):
    @staticmethod
    def cfcheck(**das):
        pass

    @staticmethod
    def datacheck(**das):
        pass


base_flow_index = Streamflow(
    identifier="base_flow_index",
    units="",
    long_name="Base flow index",
    description="Minimum 7-day average flow divided by the mean flow.",
    compute=base_flow_index,
)


freq_analysis = FA(
    identifier="freq_analysis",
    var_name="q{window}{mode}{indexer}",
    long_name="N-year return period {mode} {indexer} {window}-day flow",
    description="Streamflow frequency analysis for the {mode} {indexer} {window}-day flow "
    "estimated using the {dist} distribution.",
    compute=generic.frequency_analysis,
)


stats = Stats(
    identifier="stats",
    var_name="q{indexer}{op}",
    long_name="{freq} {op} of {indexer} daily flow ",
    description="{freq} {op} of {indexer} daily flow",
    compute=generic.select_resample_op,
)


fit = Fit(
    identifier="fit",
    var_name="params",
    units="",
    standard_name="{dist} parameters",
    long_name="{dist} distribution parameters",
    description="Parameters of the {dist} distribution",
    cell_methods="time: fit",
    compute=generic.fit,
)


doy_qmax = Streamflow(
    identifier="doy_qmax",
    var_name="q{indexer}_doy_qmax",
    long_name="Day of the year of the maximum over {indexer}",
    description="Day of the year of the maximum over {indexer}",
    units="",
    _partial=True,
    compute=wrapped_partial(generic.select_resample_op, op=generic.doymax),
)


doy_qmin = Streamflow(
    identifier="doy_qmin",
    var_name="q{indexer}_doy_qmin",
    long_name="Day of the year of the minimum over {indexer}",
    description="Day of the year of the minimum over {indexer}",
    units="",
    _partial=True,
    compute=wrapped_partial(generic.select_resample_op, op=generic.doymin),
)
