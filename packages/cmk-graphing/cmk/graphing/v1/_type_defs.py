#!/usr/bin/env python3
# Copyright (C) 2023 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from typing import TypeAlias

from . import metric

Quantity: TypeAlias = (
    str
    | metric.Constant
    | metric.WarningOf
    | metric.CriticalOf
    | metric.MinimumOf
    | metric.MaximumOf
    | metric.Sum
    | metric.Product
    | metric.Difference
    | metric.Fraction
)

Bound: TypeAlias = int | float | Quantity
