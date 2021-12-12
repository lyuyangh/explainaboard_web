from __future__ import annotations
from datetime import datetime
from typing import Iterable, Optional, Union

from explainaboard_web.models.system_analysis import SystemAnalysis
from explainaboard_web.models.system_output_props import SystemOutputProps
from explainaboard_web.models.system_create_props import SystemCreateProps
from explainaboard_web.models.system import System
from explainaboard_web.models.systems_return import SystemsReturn
from explainaboard_web.impl.db_models.db_model import DBModel, MetadataDBModel
from explainaboard import Source, get_loader, get_processor


class SystemModel(MetadataDBModel, System):
    _collection_name = "dev_system_metadata"

    @classmethod
    def create(cls, metadata: SystemCreateProps, system_output: SystemOutputProps) -> SystemModel:
        """
        create a system
          1. validate and initialize a SystemModel
          2. load system_output data
          3. generate analysis report from system_output
          -- DB --
          5. write to system_metadata (metadata + analysis)
          6. write to system_outputs
        TODO: 
          1. use session (transaction) to make sure all operations are atomic
          2. validate if dataset exists
        """
        system = cls.from_dict(metadata.to_dict())
        system_output_data = get_loader(metadata.task, Source.in_memory,
                                        system_output.file_type, system_output.data).load()
        report = get_processor(
            metadata.task, {**metadata.to_dict(), "task_name": metadata.task}, system_output_data).process()
        system.analysis = SystemAnalysis.from_dict(report.to_dict())

        # DB operations
        system_id = system.insert()
        SystemOutputModel(system_id, system_output_data).insert()

        system.system_id = system_id
        return system

    @classmethod
    def from_dict(cls, dikt) -> SystemModel:
        document = {**dikt}
        if dikt.get("_id"):
            document[f"system_id"] = str(dikt["_id"])
        system = super().from_dict(document)
        return system

    @classmethod
    def find_one_by_id(cls, id: str) -> Union[SystemModel, None]:
        """
        find one system that matches the id and return it.
        """
        document = super().find_one_by_id(id)
        if not document:
            return None
        return cls.from_dict(document)

    def insert(self) -> str:
        """
        insert system into DB. creates a new record (ignores system_id if provided). Use
        update instead if an existing document needs to be updated.
        Returns:
            inserted document ID
        """
        self.created_at = self.last_modified = datetime.utcnow()  # update timestamps
        document = self.to_dict()
        document.pop("system_id")
        return str(self.insert_one(document).inserted_id)

    @classmethod
    def find(cls, page: int, page_size: int, system_name: Optional[str], task: Optional[str]) -> SystemsReturn:
        """find multiple systems that matches the filters"""
        filter = {}
        if system_name:
            filter["model_name"] = system_name
        if task:
            filter["task"] = task
        cursor, total = super().find(filter, [], page * page_size,
                                     page_size)
        return SystemsReturn([cls.from_dict(doc) for doc in cursor], total)


class SystemOutputModel(DBModel):
    _database_name = "system_outputs"

    def __init__(self, system_id: str, data: Iterable[dict]) -> None:
        super().__init__()
        SystemOutputModel._collection_name = system_id
        self._data = data

    def insert(self, drop_old_data=True):
        """
        insert all data into DB
        Parameters:
            - drop_old_data: drops the collection if it already exists
        """
        if drop_old_data:
            self.drop()
        self.insert_many(self._data, False)
