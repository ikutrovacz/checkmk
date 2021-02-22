// Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
// This file is part of Checkmk (https://checkmk.com). It is subject to the
// terms and conditions defined in the file COPYING, which is part of this
// source code package.

#include "TableServiceGroups.h"

#include <memory>

#include "Column.h"
#include "IntLambdaColumn.h"
#include "MonitoringCore.h"
#include "NagiosGlobals.h"
#include "Query.h"
#include "ServiceGroupMembersColumn.h"
#include "ServiceListState.h"
#include "StringColumn.h"
#include "auth.h"
#include "nagios.h"

TableServiceGroups::TableServiceGroups(MonitoringCore *mc) : Table(mc) {
    addColumns(this, "", ColumnOffsets{});
}

std::string TableServiceGroups::name() const { return "servicegroups"; }

std::string TableServiceGroups::namePrefix() const { return "servicegroup_"; }

// static
void TableServiceGroups::addColumns(Table *table, const std::string &prefix,
                                    const ColumnOffsets &offsets) {
    auto offsets_members{
        offsets.add([](Row r) { return &r.rawData<servicegroup>()->members; })};
    table->addColumn(std::make_unique<StringColumn<servicegroup>>(
        prefix + "name", "The name of the service group", offsets,
        [](const servicegroup &r) {
            return r.group_name == nullptr ? "" : r.group_name;
        }));
    table->addColumn(std::make_unique<StringColumn<servicegroup>>(
        prefix + "alias", "An alias of the service group", offsets,
        [](const servicegroup &r) {
            return r.alias == nullptr ? "" : r.alias;
        }));
    table->addColumn(std::make_unique<StringColumn<servicegroup>>(
        prefix + "notes", "Optional additional notes about the service group",
        offsets, [](const servicegroup &r) {
            return r.notes == nullptr ? "" : r.notes;
        }));
    table->addColumn(std::make_unique<StringColumn<servicegroup>>(
        prefix + "notes_url",
        "An optional URL to further notes on the service group", offsets,
        [](const servicegroup &r) {
            return r.notes_url == nullptr ? "" : r.notes_url;
        }));
    table->addColumn(std::make_unique<StringColumn<servicegroup>>(
        prefix + "action_url",
        "An optional URL to custom notes or actions on the service group",
        offsets, [](const servicegroup &r) {
            return r.action_url == nullptr ? "" : r.action_url;
        }));
    auto *mc = table->core();
    table->addColumn(std::make_unique<ServiceGroupMembersColumn>(
        prefix + "members",
        "A list of all members of the service group as host/service pairs",
        offsets_members, mc, false));
    table->addColumn(std::make_unique<ServiceGroupMembersColumn>(
        prefix + "members_with_state",
        "A list of all members of the service group with state and has_been_checked",
        offsets_members, mc, true));

    auto get_service_auth = [mc]() { return mc->serviceAuthorization(); };
    table->addColumn(std::make_unique<IntLambdaColumn<servicegroup>>(
        prefix + "worst_service_state",
        "The worst soft state of all of the groups services (OK <= WARN <= UNKNOWN <= CRIT)",
        offsets,
        ServiceListState{get_service_auth,
                         ServiceListState::Type::worst_state}));
    table->addColumn(std::make_unique<IntLambdaColumn<servicegroup>>(
        prefix + "num_services", "The total number of services in the group",
        offsets,
        ServiceListState{get_service_auth, ServiceListState::Type::num}));
    table->addColumn(std::make_unique<IntLambdaColumn<servicegroup>>(
        prefix + "num_services_ok",
        "The number of services in the group that are OK", offsets,
        ServiceListState{get_service_auth, ServiceListState::Type::num_ok}));
    table->addColumn(std::make_unique<IntLambdaColumn<servicegroup>>(
        prefix + "num_services_warn",
        "The number of services in the group that are WARN", offsets,
        ServiceListState{get_service_auth, ServiceListState::Type::num_warn}));
    table->addColumn(std::make_unique<IntLambdaColumn<servicegroup>>(
        prefix + "num_services_crit",
        "The number of services in the group that are CRIT", offsets,
        ServiceListState{get_service_auth, ServiceListState::Type::num_crit}));
    table->addColumn(std::make_unique<IntLambdaColumn<servicegroup>>(
        prefix + "num_services_unknown",
        "The number of services in the group that are UNKNOWN", offsets,
        ServiceListState{get_service_auth,
                         ServiceListState::Type::num_unknown}));
    table->addColumn(std::make_unique<IntLambdaColumn<servicegroup>>(
        prefix + "num_services_pending",
        "The number of services in the group that are PENDING", offsets,
        ServiceListState{get_service_auth,
                         ServiceListState::Type::num_pending}));
    table->addColumn(std::make_unique<IntLambdaColumn<servicegroup>>(
        prefix + "num_services_handled_problems",
        "The number of services in the group that have handled problems",
        offsets,
        ServiceListState{get_service_auth,
                         ServiceListState::Type::num_handled_problems}));
    table->addColumn(std::make_unique<IntLambdaColumn<servicegroup>>(
        prefix + "num_services_unhandled_problems",
        "The number of services in the group that have unhandled problems",
        offsets,
        ServiceListState{get_service_auth,
                         ServiceListState::Type::num_unhandled_problems}));
    table->addColumn(std::make_unique<IntLambdaColumn<servicegroup>>(
        prefix + "num_services_hard_ok",
        "The number of services in the group that are OK", offsets,
        ServiceListState{get_service_auth,
                         ServiceListState::Type::num_hard_ok}));
    table->addColumn(std::make_unique<IntLambdaColumn<servicegroup>>(
        prefix + "num_services_hard_warn",
        "The number of services in the group that are WARN", offsets,
        ServiceListState{get_service_auth,
                         ServiceListState::Type::num_hard_warn}));
    table->addColumn(std::make_unique<IntLambdaColumn<servicegroup>>(
        prefix + "num_services_hard_crit",
        "The number of services in the group that are CRIT", offsets,
        ServiceListState{get_service_auth,
                         ServiceListState::Type::num_hard_crit}));
    table->addColumn(std::make_unique<IntLambdaColumn<servicegroup>>(
        prefix + "num_services_hard_unknown",
        "The number of services in the group that are UNKNOWN", offsets,
        ServiceListState{get_service_auth,
                         ServiceListState::Type::num_hard_unknown}));
}

void TableServiceGroups::answerQuery(Query *query) {
    for (const auto *sg = servicegroup_list; sg != nullptr; sg = sg->next) {
        const servicegroup *r = sg;
        if (!query->processDataset(Row(r))) {
            break;
        }
    }
}

Row TableServiceGroups::get(const std::string &primary_key) const {
    // "name" is the primary key
    return Row(find_servicegroup(const_cast<char *>(primary_key.c_str())));
}

bool TableServiceGroups::isAuthorized(Row row, const contact *ctc) const {
    return is_authorized_for_service_group(core()->groupAuthorization(),
                                           core()->serviceAuthorization(),
                                           rowData<servicegroup>(row), ctc);
}
