from __future__ import annotations
from datetime import datetime
from typing import Union, List
from explainaboard.models.datasets_return import DatasetsReturn
from explainaboard.impl.db_models.dataset_metadata_model import DatasetMetaDataModel
from explainaboard.impl.db_models.db_model import MetadataDBModel
from explainaboard.models.task_metadata import TaskMetadata


class TaskMetadataModel(MetadataDBModel, TaskMetadata):
    collection_name = "task_metadata"

    def __init__(self) -> None:
        super().__init__()

    @classmethod
    def from_dict(cls, dikt) -> TaskMetadata:
        document = {**dikt}
        if dikt.get("_id"):
            document[f"{cls.collection_name}_id"] = str(dikt["_id"])
        task_metadata = super().from_dict(document)
        return task_metadata

    @classmethod
    def find_one_by_id(cls, id: str) -> Union[TaskMetadataModel, None]:
        document = super().find_one_by_id(id)
        if not document:
            return None
        return cls.from_dict(document)

    def insert(self) -> str:
        """
        Insert object into database
        Returns:
            inserted document ID
        TODO
        """
        raise NotImplementedError

    def find_related_datasets(self, page: int, page_size: int) -> DatasetsReturn:
        return DatasetMetaDataModel.find(page, page_size, task=self.task_name)
