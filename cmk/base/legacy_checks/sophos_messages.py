#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

# .1.3.6.1.4.1.2604.1.1.1.4.1.2.1 Legit --> SOPHOS::counterType.1
# .1.3.6.1.4.1.2604.1.1.1.4.1.2.2 Blocked --> SOPHOS::counterType.2
# .1.3.6.1.4.1.2604.1.1.1.4.1.2.9 InvalidRecipient --> SOPHOS::counterType.9

# .1.3.6.1.4.1.2604.1.1.1.4.1.3.1 92 --> SOPHOS::counterInbound.1
# .1.3.6.1.4.1.2604.1.1.1.4.1.3.2 10 --> SOPHOS::counterInbound.2
# .1.3.6.1.4.1.2604.1.1.1.4.1.3.9 2 --> SOPHOS::counterInbound.9

# .1.3.6.1.4.1.2604.1.1.1.4.1.4.1 8 --> SOPHOS::counterOutbound.1
# .1.3.6.1.4.1.2604.1.1.1.4.1.4.2 0 --> SOPHOS::counterOutbound.2
# .1.3.6.1.4.1.2604.1.1.1.4.1.4.9 0 --> SOPHOS::counterOutbound.9

# TODO levels?


import time

from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.config import check_info
from cmk.base.plugins.agent_based.agent_based_api.v1 import (
    equals,
    get_rate,
    get_value_store,
    SNMPTree,
)

from cmk.agent_based.v2.type_defs import StringTable


def inventory_sophos_messages(info):
    return [(line[0].replace("InvalidRecipient", "Invalid Recipient"), None) for line in info]


def check_sophos_messages(item, params, info):
    for counter_type, inbound_str, outbound_str in info:
        if counter_type.replace("InvalidRecipient", "Invalid Recipient") == item:
            now = time.time()
            inbound = get_rate(
                get_value_store(), "inbound", now, int(inbound_str), raise_overflow=True
            )
            outbound = get_rate(
                get_value_store(), "outbound", now, int(outbound_str), raise_overflow=True
            )
            infotext = (
                "{:.1f} Inbounds and Outbounds/s, {:.1f} Inbounds/s, {:.1f} Outbounds/s".format(
                    inbound + outbound,
                    inbound,
                    outbound,
                )
            )
            return 0, infotext, [("messages_inbound", inbound), ("messages_outbound", outbound)]
    return None


def parse_sophos_messages(string_table: StringTable) -> StringTable:
    return string_table


check_info["sophos_messages"] = LegacyCheckDefinition(
    parse_function=parse_sophos_messages,
    detect=equals(".1.3.6.1.2.1.1.2.0", ".1.3.6.1.4.1.2604"),
    fetch=SNMPTree(
        base=".1.3.6.1.4.1.2604.1.1.1.4.1",
        oids=["2", "3", "4"],
    ),
    service_name="Messages %s",
    discovery_function=inventory_sophos_messages,
    check_function=check_sophos_messages,
)
