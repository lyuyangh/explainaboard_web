from __future__ import annotations

import binascii
import dataclasses
import os
from functools import lru_cache
from typing import Optional, cast

from explainaboard import (
    DatalabLoaderOption,
    TaskType,
    get_processor,
    get_task_categories,
)
from explainaboard import metric as exb_metric
from explainaboard.feature import FeatureType
from explainaboard.info import SysOutputInfo
from explainaboard.loaders.loader_registry import get_supported_file_types_for_loader
from explainaboard.metric import MetricStats
from explainaboard.processors.processor_registry import get_metric_list_for_processor
from explainaboard_web.impl.auth import get_user
from explainaboard_web.impl.benchmark import (
    Benchmark,
    BenchmarkConfig,
    Leaderboard,
    LeaderboardRecord,
)
from explainaboard_web.impl.db_utils.dataset_db_utils import DatasetDBUtils
from explainaboard_web.impl.db_utils.system_db_utils import SystemDBUtils
from explainaboard_web.impl.private_dataset import is_private_dataset
from explainaboard_web.impl.utils import abort_with_error_message, decode_base64
from explainaboard_web.models import DatasetMetadata
from explainaboard_web.models.datasets_return import DatasetsReturn
from explainaboard_web.models.system import System
from explainaboard_web.models.system_analyses_return import SystemAnalysesReturn
from explainaboard_web.models.system_create_props import SystemCreateProps
from explainaboard_web.models.system_info import SystemInfo
from explainaboard_web.models.system_outputs_return import SystemOutputsReturn
from explainaboard_web.models.systems_analyses_body import SystemsAnalysesBody
from explainaboard_web.models.systems_return import SystemsReturn
from explainaboard_web.models.task import Task
from explainaboard_web.models.task_category import TaskCategory
from flask import current_app
from pymongo import ASCENDING, DESCENDING

""" /info """


@lru_cache(maxsize=None)
def info_get():
    api_version = None
    with open("explainaboard_web/swagger/swagger.yaml") as f:
        for line in f:
            if line.startswith("  version: "):
                api_version = line[len("version: ") + 1 : -1].strip()
                break
    if not api_version:
        raise RuntimeError("failed to extract API version")
    return {
        "env": os.getenv("FLASK_ENV"),
        "auth_url": current_app.config.get("AUTH_URL"),
        "api_version": api_version,
    }


""" /user """


def user_get():
    user = get_user()
    if not user:
        abort_with_error_message(401, "login required")
    return user.get_user_info()


""" /tasks """


def tasks_get() -> list[TaskCategory]:
    _categories = get_task_categories()
    categories: list[TaskCategory] = []
    for _category in _categories:
        tasks: list[Task] = []
        for _task in _category.tasks:
            supported_formats = get_supported_file_types_for_loader(_task.name)
            supported_metrics = [
                metric.name for metric in get_metric_list_for_processor(_task.name)
            ]
            tasks.append(
                Task(
                    _task.name, _task.description, supported_metrics, supported_formats
                )
            )
        categories.append(TaskCategory(_category.name, _category.description, tasks))
    return categories


""" /datasets """


def datasets_dataset_id_get(dataset_id: str) -> DatasetMetadata:
    dataset = DatasetDBUtils.find_dataset_by_id(dataset_id)
    if dataset is None:
        abort_with_error_message(404, f"dataset id: {dataset_id} not found")
    return dataset


def datasets_get(
    dataset_ids: Optional[str],
    dataset_name: Optional[str],
    task: Optional[str],
    page: int,
    page_size: int,
) -> DatasetsReturn:
    parsed_dataset_ids = dataset_ids.split(",") if dataset_ids else None
    return DatasetDBUtils.find_datasets(
        page, page_size, parsed_dataset_ids, dataset_name, task
    )


""" /benchmarks """


def benchmarkconfigs_get() -> list[BenchmarkConfig]:
    scriptpath = os.path.dirname(__file__)
    config_folder = os.path.join(scriptpath, "./benchmark_configs/")
    # Get all benchmark configs
    benchmark_configs = []
    for file_name in sorted(os.listdir(config_folder)):
        if file_name.endswith(".json"):
            benchmark_configs.append(
                BenchmarkConfig.from_json_file(config_folder + file_name)
            )

    return benchmark_configs


def benchmark_benchmark_id_get(benchmark_id) -> Benchmark:

    scriptpath = os.path.dirname(__file__)

    # Get config
    bm_config = BenchmarkConfig.from_json_file(
        os.path.join(scriptpath, "./benchmark_configs/config_" + benchmark_id + ".json")
    )

    leaderboard = []
    for record in bm_config.record_configs:
        dataset_name = record.dataset_name
        sub_dataset_name = record.sub_dataset_name
        dataset_split = record.dataset_split

        # TODO(Pengfei): it's strange that we must pass these none-value arguments
        systems_return = systems_get(
            system_name=None,
            task=None,
            creator=None,
            shared_users=None,
            page=0,
            page_size=0,
            sort_field="created_at",
            sort_direction="desc",
            dataset=dataset_name,
            subdataset=sub_dataset_name,
            split=dataset_split,
        )
        systems = systems_return.systems
        for system in systems:
            sys_info = system.system_info.to_dict()
            # get metadata from system output info
            sys_metrics = [
                metric_config["name"] for metric_config in sys_info["metric_configs"]
            ]
            task_name = sys_info["task_name"]
            target_language = sys_info["target_language"]
            source_language = sys_info["source_language"]

            common_metrics = list(set(sys_metrics) & set(record.metrics))
            if len(common_metrics) == 0:
                continue
            else:
                leaderboard_metrics = {
                    metric: sys_info["results"]["overall"][metric]["value"]
                    for metric in common_metrics
                }

                # Populate information of leaderboard_record based on:
                # (1) sys_info and (2) benchmark config: self.record_configs
                leaderboard_record = LeaderboardRecord.from_dict(sys_info)
                leaderboard_record.metrics = leaderboard_metrics

                leaderboard_record.metric_weights = record.metric_weights
                leaderboard_record.op_metric = record.op_metric
                # Populate information based on benchmark config:aggregation_configs
                leaderboard_record.dataset_weight = (
                    1.0
                    if dataset_name
                    not in bm_config.aggregation_configs["dataset"]["weights"].keys()
                    else bm_config.aggregation_configs["dataset"]["weights"][
                        dataset_name
                    ]
                )

                leaderboard_record.task_weight = (
                    1.0
                    if task_name
                    not in bm_config.aggregation_configs["task"]["weights"].keys()
                    else bm_config.aggregation_configs["task"]["weights"][task_name]
                )

                leaderboard_record.target_language_weight = (
                    1.0
                    if target_language
                    not in bm_config.aggregation_configs["target_language"][
                        "weights"
                    ].keys()
                    else bm_config.aggregation_configs["target_language"]["weights"][
                        target_language
                    ]
                )

                leaderboard_record.source_language_weight = (
                    1.0
                    if source_language
                    not in bm_config.aggregation_configs["source_language"][
                        "weights"
                    ].keys()
                    else bm_config.aggregation_configs["source_language"]["weights"][
                        source_language
                    ]
                )

                leaderboard.append(leaderboard_record)

    benchmark = bm_config.compose(Leaderboard(leaderboard))
    return benchmark.to_dict()


""" /systems """


def systems_system_id_get(system_id: str) -> System:
    return SystemDBUtils.find_system_by_id(system_id)


def systems_get(
    system_name: Optional[str],
    task: Optional[str],
    dataset: Optional[str],
    subdataset: Optional[str],
    split: Optional[str],
    page: int,
    page_size: int,
    sort_field: str,
    sort_direction: str,
    creator: Optional[str],
    shared_users: Optional[list[str]],
) -> SystemsReturn:
    ids = None
    if not sort_field:
        sort_field = "created_at"
    if not sort_direction:
        sort_direction = "desc"
    if sort_direction not in ["asc", "desc"]:
        abort_with_error_message(400, "sort_direction needs to be one of asc or desc")
    if sort_field != "created_at":
        sort_field = f"system_info.results.overall.{sort_field}.value"

    dir = ASCENDING if sort_direction == "asc" else DESCENDING

    return SystemDBUtils.find_systems(
        ids,
        page,
        page_size,
        system_name,
        task,
        dataset,
        subdataset,
        split,
        [(sort_field, dir)],
        creator,
        shared_users,
    )


def systems_post(body: SystemCreateProps) -> System:
    """
    aborts with error if fails
    TODO: error handling
    """
    if body.metadata.dataset_metadata_id:
        if not body.metadata.dataset_split:
            abort_with_error_message(
                400, "dataset split is required if a dataset is chosen"
            )
        if body.custom_dataset:
            abort_with_error_message(
                400,
                "both datalab dataset and custom dataset are "
                "provided. please only select one.",
            )

    try:
        body.system_output.data = decode_base64(body.system_output.data)
        if body.custom_dataset and body.custom_dataset.data:
            body.custom_dataset.data = decode_base64(body.custom_dataset.data)
        system = SystemDBUtils.create_system(
            body.metadata, body.system_output, body.custom_dataset
        )
        return system
    except binascii.Error as e:
        abort_with_error_message(
            400, f"file should be sent in plain text base64. ({e})"
        )


def systems_system_id_outputs_get(
    system_id: str, output_ids: Optional[str]
) -> SystemOutputsReturn:
    """
    TODO: return special error/warning if some ids cannot be found
    """
    sys = SystemDBUtils.find_system_by_id(system_id)
    user = get_user()
    has_access = user.is_authenticated and (
        sys.creator == user.email or user.email in sys.shared_users
    )
    if sys.is_private and not has_access:
        abort_with_error_message(403, "system access denied", 40302)
    if is_private_dataset(
        DatalabLoaderOption(
            sys.system_info.dataset_name,
            sys.system_info.sub_dataset_name,
            sys.system_info.dataset_split,
        )
    ):
        abort_with_error_message(
            403, f"{sys.system_info.dataset_name} is a private dataset", 40301
        )

    return SystemDBUtils.find_system_outputs(system_id, output_ids, limit=10)


def systems_system_id_delete(system_id: str):
    success = SystemDBUtils.delete_system_by_id(system_id)
    if success:
        return "Success"
    abort_with_error_message(400, f"cannot find system_id: {system_id}")


def systems_analyses_post(body: SystemsAnalysesBody):
    system_ids_str = body.system_ids
    pairwise_performance_gap = body.pairwise_performance_gap
    custom_feature_to_bucket_info = body.feature_to_bucket_info

    single_analyses: dict = {}
    system_ids: list = system_ids_str.split(",")
    system_name = None
    task = None
    dataset_name = None
    subdataset_name = None
    split = None
    creator = None
    shared_users = None
    page = 0
    page_size = len(system_ids)
    sort = None
    systems: list[System] = SystemDBUtils.find_systems(
        system_ids,
        page,
        page_size,
        task,
        system_name,
        dataset_name,
        subdataset_name,
        split,
        sort,
        creator,
        shared_users,
        include_metric_stats=True,
    ).systems
    systems_len = len(systems)
    if systems_len == 0:
        return SystemAnalysesReturn(single_analyses)

    if pairwise_performance_gap and systems_len != 2:
        abort_with_error_message(
            400,
            "pairwise_performance_gap=true"
            + f" only accepts 2 systems, got: {systems_len}",
        )

    for system in systems:
        system_info: SystemInfo = system.system_info
        system_info_dict = system_info.to_dict()
        system_output_info = SysOutputInfo.from_dict(system_info_dict)

        for feature_name, feature in system_output_info.features.items():
            feature = FeatureType.from_dict(feature)  # dict -> Feature

            # user-defined bucket info
            if feature_name in custom_feature_to_bucket_info:
                custom_bucket_info = custom_feature_to_bucket_info[feature_name]
                # Hardcoded as SDK doesn't export this name
                feature.bucket_info.method = (
                    "bucket_attribute_specified_bucket_interval"
                )
                feature.bucket_info.number = custom_bucket_info.number
                setting = [tuple(interval) for interval in custom_bucket_info.setting]
                feature.bucket_info.setting = setting
            system_output_info.features[feature_name] = feature

        metric_configs = [
            getattr(exb_metric, metric_config_dict["cls_name"])(**metric_config_dict)
            for metric_config_dict in system_output_info.metric_configs
        ]

        system_output_info.metric_configs = metric_configs

        processor = get_processor(TaskType(system_output_info.task_name))
        metric_stats = [MetricStats(stat) for stat in system.metric_stats]

        # Get the entire system outputs
        output_ids = None
        system_outputs = SystemDBUtils.find_system_outputs(
            system.system_id, output_ids, limit=0
        ).system_outputs
        # Note we are casting here, as SystemOutput.from_dict() actually just returns a
        # dict
        system_outputs = [cast(dict, x) for x in system_outputs]

        fine_grained_statistics = processor.get_fine_grained_statistics(
            system_output_info,
            system_outputs,
            system.active_features,
            metric_stats,
        )
        performance_over_bucket: dict = fine_grained_statistics.performance_over_bucket
        # TODO This is a HACK. Should add proper to_dict methods in SDK
        for feature, feature_dict in performance_over_bucket.items():
            for bucket_key, bucket_performance in list(feature_dict.items()):
                bucket_performance = dataclasses.asdict(bucket_performance)
                new_bucket_key = [str(number) for number in bucket_key]
                new_bucket_key_str = f"({', '.join(new_bucket_key)})"
                bucket_performance["bucket_name"] = [
                    str(num) for num in bucket_performance["bucket_name"]
                ]
                performance_over_bucket[feature][
                    new_bucket_key_str
                ] = bucket_performance
                performance_over_bucket[feature].pop(bucket_key)

        single_analyses[system.system_id] = performance_over_bucket

    return SystemAnalysesReturn(single_analyses)
