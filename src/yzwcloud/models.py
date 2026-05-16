from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class NodeStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class TaskStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DataObject(BaseModel):
    type: str
    data: str
    meta: dict[str, Any] = Field(default_factory=dict)


class NodeDefinition(BaseModel):
    id: str
    name: str
    description: str
    input_types: list[str] = Field(default_factory=list)
    output_type: str
    default_params: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class GraphNode(BaseModel):
    id: str
    name: str
    description: str
    status: NodeStatus
    input_types: list[str] = Field(default_factory=list)
    output_type: str
    default_params: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    output: DataObject | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class Graph(BaseModel):
    task_id: str
    nodes: list[GraphNode]
    edges: list[dict[str, str]]
    updated_at: datetime


class TaskState(BaseModel):
    task_id: str
    name: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    current_node: str | None = None


class CreateTaskRequest(BaseModel):
    name: str = "生信分析任务"


class RunNodeRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class CreateDiffAnalysisRequest(BaseModel):
    case_condition: str
    control_condition: str
    method: str = "demo_ttest"
    p_value: float = 0.05
    log2fc: float = 1.0


class CreateAnalysisNodeRequest(BaseModel):
    source_node_id: str
    analysis_type: str


class ComparisonOptionsResponse(BaseModel):
    conditions: list[str]
    counts: dict[str, int]


class TaskDetail(BaseModel):
    task: TaskState
    graph: Graph


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
