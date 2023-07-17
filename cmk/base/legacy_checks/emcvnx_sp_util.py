#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

# <<<emcvnx_sp_util:sep(58)>>>
# Controller busy ticks: 1639432
# Controller idle ticks: 1773844

# suggested by customer


# mypy: disable-error-code="var-annotated"

import time

from cmk.base.check_api import get_rate, LegacyCheckDefinition
from cmk.base.config import check_info

emcvnx_sp_util_default_levels = (50.0, 60.0)


def parse_emcvnx_sp_util(string_table):
    parsed = {}
    for line in string_table:
        if len(line) == 2 and "busy" in line[0]:
            parsed.setdefault("busy", float(line[1]))
        elif len(line) == 2 and "idle" in line[0]:
            parsed.setdefault("idle", float(line[1]))
    return parsed


def inventory_emcvnx_sp_util(parsed):
    if "idle" in parsed and "busy" in parsed:
        return [(None, emcvnx_sp_util_default_levels)]
    return []


def check_emcvnx_sp_util(item, params, parsed):
    if not ("idle" in parsed and "busy" in parsed):
        return None

    now = time.time()
    warn, crit = params
    busy_ticks_rate = get_rate("emcvnx_sp_util.busy_ticks", now, parsed["busy"])
    idle_ticks_rate = get_rate("emcvnx_sp_util.idle_ticks", now, parsed["idle"])
    if busy_ticks_rate + idle_ticks_rate == 0:
        sp_util = 0.0
    else:
        sp_util = 100 * (
            busy_ticks_rate / (busy_ticks_rate + idle_ticks_rate)
        )  # fixed: true-division
    infotext = "%.1f%%" % sp_util
    if sp_util >= crit:
        state = 2
    elif sp_util >= warn:
        state = 1
    else:
        state = 0

    if state > 0:
        infotext += " (warn/crit at %.1f%%/%.1f%%)" % (warn, crit)

    return state, infotext, [("storage_processor_util", sp_util, warn, crit, 0, 100.0)]


check_info["emcvnx_sp_util"] = LegacyCheckDefinition(
    parse_function=parse_emcvnx_sp_util,
    service_name="Storage Processor Utilization",
    discovery_function=inventory_emcvnx_sp_util,
    check_function=check_emcvnx_sp_util,
    check_ruleset_name="sp_util",
)
