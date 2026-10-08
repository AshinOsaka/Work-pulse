"""Base document models.

Internal persistence models keep native `ObjectId`s; API schemas expose strings.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Self

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, PlainValidator, WithJsonSchema

from app.utils.time import utcnow


def _validate_object_id(value: Any) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    raise ValueError("Invalid ObjectId")


PyObjectId = Annotated[
    ObjectId,
    PlainValidator(_validate_object_id),
    PlainSerializer(str, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "pattern": "^[0-9a-f]{24}$"}),
]


class MongoModel(BaseModel):
    model_config = ConfigDict(
        validate_by_name=True,
        validate_by_alias=True,
        arbitrary_types_allowed=True,
        extra="ignore",
    )

    id: PyObjectId = Field(default_factory=ObjectId, alias="_id")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def to_document(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> Self:
        return cls.model_validate(document)


class TenantModel(MongoModel):
    """A document owned by exactly one company (tenant)."""

    company_id: PyObjectId
