#!/usr/bin/env python3
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

# TODO: Cluster with different data sources, eg. TCP node and SNMP node:
# - Discovery works.
# - Checking doesn't work - as it was before. Maybe we can handle this in the future.

import logging
from collections.abc import Iterable, Sequence
from contextlib import suppress
from typing import assert_never, Final

from cmk.utils.exceptions import OnError
from cmk.utils.type_defs import HostAddress, HostAgentConnectionMode, HostName, SectionName

from cmk.snmplib.type_defs import SNMPRawDataSection

from cmk.fetchers import Fetcher, FetcherType, SNMPFetcher
from cmk.fetchers.cache import SectionStore
from cmk.fetchers.config import make_persisted_section_dir
from cmk.fetchers.filecache import FileCache, FileCacheOptions, MaxAge

from cmk.checkers import Parser, SNMPParser, Source, SourceInfo
from cmk.checkers.type_defs import AgentRawDataSection, NO_SELECTION, SectionNameCollection

import cmk.base.api.agent_based.register as agent_based_register
import cmk.base.config as config
from cmk.base.api.agent_based.register.snmp_plugin_store import make_plugin_store
from cmk.base.config import ConfigCache
from cmk.base.ip_lookup import AddressFamily

from ._sources import (
    IPMISource,
    MgmtSNMPSource,
    MissingIPSource,
    PiggybackSource,
    ProgramSource,
    PushAgentSource,
    SNMPSource,
    SpecialAgentSource,
    TCPSource,
)

__all__ = [
    "make_sources",
    "make_parser",
]


def make_parser(
    config_cache: ConfigCache,
    source: SourceInfo,
    *,
    # Always from NO_SELECTION.
    checking_sections: frozenset[SectionName],
    keep_outdated: bool,
    logger: logging.Logger,
) -> Parser:
    hostname = source.hostname
    if source.fetcher_type is FetcherType.SNMP:
        return SNMPParser(
            hostname,
            SectionStore[SNMPRawDataSection](
                make_persisted_section_dir(
                    source.hostname,
                    fetcher_type=source.fetcher_type,
                    ident=source.ident,
                ),
                logger=logger,
            ),
            check_intervals={
                section_name: config_cache.snmp_fetch_interval(hostname, section_name)
                for section_name in checking_sections
            },
            keep_outdated=keep_outdated,
            logger=logger,
        )

    return config_cache.make_agent_parser(
        hostname,
        SectionStore[AgentRawDataSection](
            make_persisted_section_dir(
                source.hostname, fetcher_type=source.fetcher_type, ident=source.ident
            ),
            logger=logger,
        ),
        keep_outdated=keep_outdated,
        logger=logger,
    )


class _Builder:
    def __init__(
        self,
        host_name: HostName,
        ipaddress: HostAddress | None,
        address_family: AddressFamily,
        *,
        config_cache: ConfigCache,
        selected_sections: SectionNameCollection,
        on_scan_error: OnError,
        max_age_agent: MaxAge,
        max_age_snmp: MaxAge,
    ) -> None:
        super().__init__()
        self.host_name: Final = host_name
        self.config_cache: Final = config_cache
        self.ipaddress: Final = ipaddress
        self.address_family: Final = address_family
        self.selected_sections: Final = selected_sections
        self.on_scan_error: Final = on_scan_error
        self.max_age_agent: Final = max_age_agent
        self.max_age_snmp: Final = max_age_snmp

        assert not self.config_cache.is_cluster(self.host_name)
        self._elems: dict[str, Source] = {}
        self._initialize_agent_based()
        self._initialize_snmp_based()
        self._initialize_mgmt_boards()

    @property
    def sources(self) -> Sequence[Source]:
        # Always execute piggyback at the end
        return sorted(
            self._elems.values(),
            key=lambda args: (
                args.source_info().fetcher_type is FetcherType.PIGGYBACK,
                args.source_info().ident,
            ),
        )

    def _initialize_agent_based(self) -> None:
        # agent-based data sources use the cache and persisted directories
        # that existed before the data source concept has been added where
        # each data source has its own set of directories.
        #
        # TODO: We should cleanup these old directories one day, then we can
        #       remove this special case.
        #
        if self.config_cache.is_all_agents_host(self.host_name):
            self._get_agent()
            for elem in self._get_special_agents():
                self._add(elem)

        elif self.config_cache.is_all_special_agents_host(self.host_name):
            for elem in self._get_special_agents():
                self._add(elem)

        elif self.config_cache.is_tcp_host(self.host_name):
            special_agents = tuple(self._get_special_agents())
            if special_agents:
                self._add(special_agents[0])
            else:
                self._get_agent()

        if "no-piggyback" not in self.config_cache.tag_list(self.host_name):
            self._add(PiggybackSource(self.config_cache, self.host_name, self.ipaddress))

    def _initialize_snmp_plugin_store(self) -> None:
        if len(SNMPFetcher.plugin_store) != agent_based_register.len_snmp_sections():
            # That's a hack.
            #
            # `make_plugin_store()` depends on
            # `iter_all_snmp_sections()` and `iter_all_inventory_plugins()`
            # that are populated by the Check API upon loading the plugins.
            #
            # It is there, when the plugins are loaded, that we should
            # make the plugin store.  However, it is not clear whether
            # the API would let us register hooks to accomplish that.
            #
            # The current solution is brittle in that there is not guarantee
            # that all the relevant plugins are loaded at this point.
            SNMPFetcher.plugin_store = make_plugin_store()

    def _initialize_snmp_based(self) -> None:
        if not self.config_cache.is_snmp_host(self.host_name):
            return
        if self.address_family is AddressFamily.NO_IP:
            return
        if self.ipaddress is None:
            self._add(MissingIPSource(self.host_name, self.ipaddress, "snmp"))
            return
        self._initialize_snmp_plugin_store()
        self._add(
            SNMPSource(
                self.config_cache,
                self.host_name,
                self.ipaddress,
                max_age=self.max_age_snmp,
                on_scan_error=self.on_scan_error,
                selected_sections=self.selected_sections,
            )
        )

    def _initialize_mgmt_boards(self) -> None:
        protocol = self.config_cache.management_protocol(self.host_name)
        if protocol is None:
            return

        self._initialize_snmp_plugin_store()
        if protocol == "snmp":
            if self.address_family is AddressFamily.NO_IP:
                return
            if self.ipaddress is None:
                self._add(MissingIPSource(self.host_name, self.ipaddress, "mgmt_snmp"))
                return
            self._add(
                MgmtSNMPSource(
                    self.config_cache,
                    self.host_name,
                    self.ipaddress,
                    max_age=self.max_age_snmp,
                    on_scan_error=self.on_scan_error,
                    selected_sections=self.selected_sections,
                )
            )
        elif protocol == "ipmi":
            if self.address_family is AddressFamily.NO_IP:
                return
            ip_address = config.lookup_mgmt_board_ip_address(self.config_cache, self.host_name)
            if ip_address is None:
                self._add(MissingIPSource(self.host_name, ip_address, "mgmt_ipmi"))
                return
            self._add(
                IPMISource(
                    self.config_cache, self.host_name, ip_address, max_age=self.max_age_agent
                )
            )
        else:
            raise LookupError()

    def _add(self, source: Source) -> None:
        self._elems[source.source_info().ident] = source

    def _get_agent(self) -> None:
        with suppress(LookupError):
            self._add(
                ProgramSource(
                    self.config_cache,
                    self.host_name,
                    self.ipaddress,
                    max_age=self.max_age_agent,
                )
            )
            return

        connection_mode = self.config_cache.agent_connection_mode(self.host_name)
        match connection_mode:
            case HostAgentConnectionMode.PUSH:
                # convert to seconds and add grace period
                interval = int(1.5 * 60 * self.config_cache.check_mk_check_interval(self.host_name))
                self._add(
                    source=PushAgentSource(
                        self.host_name,
                        self.ipaddress,
                        max_age=MaxAge(interval, interval, interval),
                    )
                )
            case HostAgentConnectionMode.PULL:
                if self.address_family is AddressFamily.NO_IP:
                    return
                if self.ipaddress is None:
                    self._add(MissingIPSource(self.host_name, self.ipaddress, "agent"))
                    return
                self._add(
                    TCPSource(
                        self.config_cache,
                        self.host_name,
                        self.ipaddress,
                        max_age=self.max_age_agent,
                    )
                )
            case _:
                assert_never(connection_mode)

    def _get_special_agents(self) -> Iterable[Source]:
        for agentname, params in self.config_cache.special_agents(self.host_name):
            with suppress(KeyError):
                yield SpecialAgentSource(
                    self.host_name,
                    self.ipaddress,
                    max_age=self.max_age_agent,
                    agent_name=agentname,
                    params=params,
                )


def make_sources(
    host_name: HostName,
    ipaddress: HostAddress | None,
    address_family: AddressFamily,
    *,
    config_cache: ConfigCache,
    force_snmp_cache_refresh: bool = False,
    selected_sections: SectionNameCollection = NO_SELECTION,
    on_scan_error: OnError = OnError.RAISE,
    simulation_mode: bool,
    file_cache_options: FileCacheOptions,
    file_cache_max_age: MaxAge,
) -> Sequence[tuple[SourceInfo, FileCache, Fetcher]]:
    """Sequence of sources available for `host_config`."""
    if config_cache.is_cluster(host_name):
        # Cluster hosts do not have any actual data sources
        # Instead all data is provided by the nodes
        return ()

    def max_age_snmp() -> MaxAge:
        if simulation_mode:
            return MaxAge.unlimited()
        if force_snmp_cache_refresh:
            return MaxAge.zero()
        if file_cache_options.use_outdated:
            return MaxAge.unlimited()
        return file_cache_max_age

    def max_age_agent() -> MaxAge:
        if simulation_mode:
            return MaxAge.unlimited()
        if file_cache_options.use_outdated:
            return MaxAge.unlimited()
        return file_cache_max_age

    return [
        (
            source.source_info(),
            source.file_cache(
                simulation=simulation_mode,
                file_cache_options=file_cache_options,
            ),
            source.fetcher(),
        )
        for source in _Builder(
            host_name,
            ipaddress,
            address_family,
            config_cache=config_cache,
            selected_sections=selected_sections,
            on_scan_error=on_scan_error,
            max_age_agent=max_age_agent(),
            max_age_snmp=max_age_snmp(),
        ).sources
    ]
