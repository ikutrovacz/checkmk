#!/usr/bin/env python3

from .agent_based_api.v1 import *

AWSStrings = bytes | str

Dimension = dict[Literal["Name", "Value"], str | None]

class MetricData(TypedDict):
    Namespace: str
    MetricName: str
    Dimensions: Sequence[Dimension]

class MetricStat(TypedDict):
    Metric: MetricData
    Period: int
    Stat: str
    Unit: NotRequired[str]

class MetricRequired(TypedDict):
    Id: str
    Label: str

class AWSColleagueContents(NamedTuple):
    content: Any
    cache_timestamp: float

class Metric(MetricRequired, total=False):
    Expression: str
    MetricStat: MetricStat
    Period: int

class AWSRawContent(NamedTuple):
    content: Any
    cache_timestamp: float

class AWSComputedContent(NamedTuple):
    content: Any
    cache_timestamp: float

class AWSSectionResults(NamedTuple):
    results: list
    cache_timestamp: float


class AWSSectionResult(NamedTuple):
    piggyback_hostname: AWSStrings
    content: Any
    piggyback_host_labels: Mapping[str, str] | None = None

Metrics = list[Metric]

class StatusEnum(StrEnum):
    active = "ACTIVE"
    provisioning = "PROVISIONING"
    deprovisioning = "DEPROVISIONING"
    failed = "FAILED"
    inactive = "INACTIVE"


class Tag(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    Key: str = Field(..., alias="key")
    Value: str = Field(..., alias="value")


class Cluster(BaseModel):
    clusterArn: str
    clusterName: str
    status: StatusEnum
    tags: Sequence[Tag]
    registeredContainerInstancesCount: int
    activeServicesCount: int
    capacityProviders: Sequence[str]

def get_ecs_cluster_arns(ecs_client: BaseClient) -> Iterable[str]:
    for page in ecs_client.get_paginator("list_clusters").paginate():
        yield from page["clusterArns"]


def get_ecs_clusters(ecs_client: BaseClient, cluster_ids: Sequence[str]) -> Iterable[Cluster]:
    # the ECS.Client API allows fetching up to 100 clusters at once
    for chunk in _chunks(cluster_ids, length=100):
        clusters = ecs_client.describe_clusters(clusters=chunk, include=["TAGS"])  # type: ignore[attr-defined]
        yield from [Cluster(**cluster_data) for cluster_data in clusters["clusters"]]

class ECS(AWSSectionCloudwatch):
    @property
    def name(self) -> str:
        return "ecs"

    @property
    def cache_interval(self) -> int:
        return 300

    @property
    def granularity(self) -> int:
        return 300

    def _get_colleague_contents(self) -> AWSColleagueContents:
        colleague = self._received_results.get("ecs_summary")
        if colleague and colleague.content:
            return AWSColleagueContents(
                [cluster.clusterName for cluster in colleague.content],
                colleague.cache_timestamp,
            )
        return AWSColleagueContents([], 0.0)

    def _get_metrics(self, colleague_contents: AWSColleagueContents) -> Metrics:
        muv: list[tuple[str, str]] = [
            ("CPUUtilization", "Percent"),
            ("CPUReservation", "Percent"),
            ("MemoryUtilization", "Percent"),
            ("MemoryReservation", "Percent"),
        ]
        metrics: Metrics = []
        for idx, cluster_name in enumerate(colleague_contents.content):
            for metric_name, unit in muv:
                metric: Metric = {
                    "Id": self._create_id_for_metric_data_query(idx, metric_name),
                    "Label": cluster_name,
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/ECS",
                            "MetricName": metric_name,
                            "Dimensions": [
                                {
                                    "Name": "ClusterName",
                                    "Value": cluster_name,
                                }
                            ],
                        },
                        "Period": self.period,
                        "Stat": "Average",
                    },
                }
                if unit:
                    metric["MetricStat"]["Unit"] = unit
                metrics.append(metric)
        return metrics

    def _compute_content(
        self, raw_content: AWSRawContent, colleague_contents: AWSColleagueContents
    ) -> AWSComputedContent:
        return AWSComputedContent(raw_content.content, raw_content.cache_timestamp)

    def _create_results(self, computed_content: AWSComputedContent) -> list[AWSSectionResult]:
        return [AWSSectionResult("", computed_content.content)]        

def discover_aws_ecs(section):
    for cluster_name in section.content:
        yield Service(
            item=Item(cluster_name),
            discovery_data={"ClusterName": cluster_name},
        )       

def check_aws_ecs(item, params, section):
    cpu_utilization = section.get("CPUUtilization", 0)  # Replace with actual metric name
    cpu_reservation = section.get("CPUReservation", 0)  # Replace with actual metric name
    memory_utilization = section.get("MemoryUtilization", 0)  # Replace with actual metric name
    memory_reservation = section.get("MemoryReservation", 0)  # Replace with actual metric name

    cpu_threshold = params.get("cpu_threshold", 90)  # Replace with your desired CPU threshold
    memory_threshold = params.get("memory_threshold", 90)  # Replace with your desired memory threshold

    if cpu_utilization > cpu_threshold and memory_utilization > memory_threshold:
        return Result(
            state=State.CRIT,
            summary=f"CPU Utilization is {cpu_utilization}% and Memory Utilization is {memory_utilization}%",
        )
    elif cpu_utilization > cpu_threshold:
        return Result(
            state=State.CRIT,
            summary=f"CPU Utilization is {cpu_utilization}%",
        )
    elif memory_utilization > memory_threshold:
        return Result(
            state=State.CRIT,
            summary=f"Memory Utilization is {memory_utilization}%",
        )
    else:
        return Result(
            state=State.OK,
            summary=f"CPU Utilization is {cpu_utilization}% and Memory Utilization is {memory_utilization}%",
        )
    
register.check_plugin(
    name="aws_ecs",
    service_name="AWS ECS",
    discovery_function=discover_aws_ecs,
    check_function=check_aws_ecs,
) 
