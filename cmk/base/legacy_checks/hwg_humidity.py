#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from cmk.base.check_api import contains, LegacyCheckDefinition
from cmk.base.check_legacy_includes.hwg import (
    check_hwg_humidity,
    HWG_HUMIDITY_DEFAULTLEVELS,
    inventory_hwg_humidity,
    parse_hwg,
)
from cmk.base.config import check_info
from cmk.base.plugins.agent_based.agent_based_api.v1 import SNMPTree

check_info["hwg_humidity"] = LegacyCheckDefinition(
    detect=contains(".1.3.6.1.2.1.1.1.0", "hwg"),
    parse_function=parse_hwg,
    check_function=check_hwg_humidity,
    discovery_function=inventory_hwg_humidity,
    service_name="Humidity %s",
    fetch=SNMPTree(
        base=".1.3.6.1.4.1.21796.4.1.3.1",
        oids=["1", "2", "3", "4", "7"],
    ),
    check_ruleset_name="humidity",
    check_default_parameters=HWG_HUMIDITY_DEFAULTLEVELS,
)
