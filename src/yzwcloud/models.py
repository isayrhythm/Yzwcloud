from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


class UpdateTaskRequest(BaseModel):
    name: str


class RunNodeRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class PlotStudioSource(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_kind: str = Field(default="analysis_output", alias="sourceKind")
    task_id: str = Field(default="", alias="taskId")
    task_name: str = Field(default="", alias="taskName")
    node_id: str = Field(default="", alias="nodeId")
    name: str = ""
    status: str = ""
    type: str = ""
    summary: str = ""
    data_path: str = Field(default="", alias="dataPath")
    preview_url: str = Field(default="", alias="previewUrl")
    html_url: str = Field(default="", alias="htmlUrl")
    meta: dict[str, Any] = Field(default_factory=dict)


class PlotStudioReportRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: PlotStudioSource
    plot_type: str | None = Field(default=None, alias="plotType")
    params: dict[str, Any] = Field(default_factory=dict)


class PlotStudioSpecRequest(PlotStudioReportRequest):
    pass


class CreateDiffAnalysisRequest(BaseModel):
    case_condition: str
    control_condition: str
    method: str = "demo_ttest"
    p_value: float = 0.05
    log2fc: float = 1.0


class CreateAnalysisNodeRequest(BaseModel):
    source_node_id: str
    analysis_type: str


class UpdateSampleGroupsRequest(BaseModel):
    assignments: dict[str, str] = Field(default_factory=dict)
    condition_colors: dict[str, str] = Field(default_factory=dict)


class SampleMetadataTextRequest(BaseModel):
    content: str = Field(min_length=1, description="sample metadata in CSV/TSV text")
    filename: str = "sample_metadata.csv"


class ComparisonOptionsResponse(BaseModel):
    conditions: list[str]
    counts: dict[str, int]


class TaskDetail(BaseModel):
    task: TaskState
    graph: Graph


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
