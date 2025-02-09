#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.check_legacy_includes.temperature import check_temperature
from cmk.base.config import check_info
from cmk.base.plugins.agent_based.agent_based_api.v1 import all_of, contains, equals, SNMPTree

from cmk.agent_based.v2.type_defs import StringTable

# .1.3.6.1.4.1.31560.3.1.1.1.48 33 --> ARTEC-MIB::hddTemperature

# suggested by customer


def inventory_artec_temp(info):
    return [("Disk", {})]


def check_artec_temp(item, params, info):
    return check_temperature(int(info[0][0]), params, "artec_%s" % item)


def parse_artec_temp(string_table: StringTable) -> StringTable:
    return string_table


check_info["artec_temp"] = LegacyCheckDefinition(
    parse_function=parse_artec_temp,
    detect=all_of(
        equals(".1.3.6.1.2.1.1.2.0", ".1.3.6.1.4.1.8072.3.2.10"),
        contains(".1.3.6.1.2.1.1.1.0", "version"),
        contains(".1.3.6.1.2.1.1.1.0", "serial"),
    ),
    fetch=SNMPTree(
        base=".1.3.6.1.4.1.31560.3.1.1.1",
        oids=["48"],
    ),
    service_name="Temperature %s",
    discovery_function=inventory_artec_temp,
    check_function=check_artec_temp,
    check_ruleset_name="temperature",
    check_default_parameters={
        "levels": (36.0, 40.0),
    },
)
