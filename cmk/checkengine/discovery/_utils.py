#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from __future__ import annotations

import enum
from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass
from typing import Final, Generic, Literal, Protocol, Self, TypeVar

__all__ = ["DiscoveryMode", "QualifiedDiscovery", "DiscoverySettings"]

DiscoveryVsSetting = dict[
    Literal["add_new_services", "remove_vanished_services", "update_host_labels"], bool
]
DiscoveryVsSettings = tuple[Literal["update_everything", "custom"], DiscoveryVsSetting]


@dataclass(frozen=True)
class DiscoverySettings:
    update_host_labels: bool
    add_new_services: bool
    remove_vanished_services: bool
    # this will be separated into service labels and parameters at some point
    update_changed_services: bool

    @classmethod
    def from_discovery_mode(cls, mode: DiscoveryMode) -> Self:
        return cls(
            update_host_labels=mode is not DiscoveryMode.REMOVE,
            add_new_services=mode
            in (DiscoveryMode.NEW, DiscoveryMode.FIXALL, DiscoveryMode.REFRESH),
            remove_vanished_services=mode in (DiscoveryMode.REMOVE, DiscoveryMode.FIXALL),
            update_changed_services=mode is DiscoveryMode.REFRESH,
        )

    @classmethod
    def from_vs(cls, mode: DiscoveryVsSettings | None) -> Self:
        if mode is None:
            return cls(
                update_host_labels=False,
                add_new_services=False,
                remove_vanished_services=False,
                update_changed_services=False,
            )

        if "update_everything" in mode:
            return cls(
                update_host_labels=True,
                add_new_services=True,
                remove_vanished_services=True,
                update_changed_services=True,
            )

        return cls(
            update_host_labels=mode[1].get("update_host_labels", False),
            add_new_services=mode[1].get("add_new_services", False),
            remove_vanished_services=mode[1].get("remove_vanished_services", False),
            update_changed_services=False,
        )


class DiscoveryMode(enum.Enum):
    # NOTE: the values 0-3 are used in WATO rules and must not be changed!
    NEW = 0
    REMOVE = 1
    FIXALL = 2
    REFRESH = 3
    ONLY_HOST_LABELS = 4
    FALLBACK = 5  # not sure why this could happen

    @classmethod
    def _missing_(cls, value: object) -> DiscoveryMode:
        return cls.FALLBACK

    @classmethod
    def from_str(cls, value: str) -> DiscoveryMode:
        # NOTE: 'only-host-labels' is sent by an automation call, so we need to deal with that.
        return cls[value.upper().replace("-", "_")]


class _Discoverable(Protocol):
    """
    Required interface for a qualified discovery.

    For discovered things (e.g. host labels, services) we need to decide
    wether things are new, old, vanished, or *changed*.
    Currently the "changed" is WIP.

    Anyway: we need a proper distiction between being the same entity and
    comparing equal.
    """

    def id(self) -> Hashable:
        ...

    # tbd: def comperator(self) -> object:
    #    ...


_DiscoveredItem = TypeVar("_DiscoveredItem", bound=_Discoverable)


class QualifiedDiscovery(Generic[_DiscoveredItem]):
    """Classify items into "new", "old" and "vanished" ones."""

    def __init__(
        self,
        *,
        preexisting: Sequence[_DiscoveredItem],
        current: Sequence[_DiscoveredItem],
    ) -> None:
        current_dict = {v.id(): v for v in current}
        preexisting_dict = {v.id(): v for v in preexisting}

        self.vanished: Final = [v for k, v in preexisting_dict.items() if k not in current_dict]
        self.old: Final = [v for k, v in preexisting_dict.items() if k in current_dict]
        self.new: Final = [v for k, v in current_dict.items() if k not in preexisting_dict]
        self.present: Final = self.old + self.new

    @classmethod
    def empty(cls) -> QualifiedDiscovery:
        """create an empty instance"""
        return cls(preexisting=(), current=())

    def chain_with_qualifier(
        self,
    ) -> Iterable[tuple[Literal["vanished", "old", "new"], _DiscoveredItem]]:
        yield from (("vanished", value) for value in self.vanished)
        yield from (("old", value) for value in self.old)
        yield from (("new", value) for value in self.new)
