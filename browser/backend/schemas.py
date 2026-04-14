from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class SessionBase(BaseModel):
    provider: str
    project: str
    model: str | None = None
    conversation_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    turn_count: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    total_chars: int | None = None
    total_words: int | None = None
    estimated_cost: float | None = None
    source_file: str | None = None
    summary_text: str | None = None
    session_type: str | None = None


class SessionCreate(SessionBase):
    id: str


class SessionRead(SessionBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    hidden_at: datetime | None = None
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Segment
# ---------------------------------------------------------------------------

class SegmentBase(BaseModel):
    session_id: str
    segment_index: int | None = None
    role: str | None = None
    timestamp: datetime | None = None
    char_count: int | None = None
    word_count: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw_text: str | None = None
    preview: str | None = None


class SegmentCreate(SegmentBase):
    id: str


class SegmentRead(SegmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    hidden_at: datetime | None = None


# ---------------------------------------------------------------------------
# Tool call
# ---------------------------------------------------------------------------

class ToolCallBase(BaseModel):
    session_id: str
    segment_id: str | None = None
    tool_name: str
    tool_family: str | None = None
    timestamp: datetime | None = None


class ToolCallCreate(ToolCallBase):
    pass


class ToolCallRead(ToolCallBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


# ---------------------------------------------------------------------------
# Session topic
# ---------------------------------------------------------------------------

class SessionTopicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    topic: str
    confidence: float | None = None
    source: str | None = "heuristic"


# ---------------------------------------------------------------------------
# Saved search
# ---------------------------------------------------------------------------

class SavedSearchCreate(BaseModel):
    name: str
    query: str
    filters_json: dict | None = None


class SavedSearchRead(SavedSearchCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Graphify enrichment
# ---------------------------------------------------------------------------

class ConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: str | None = None
    community_id: int | None = None
    degree: int | None = None


class SessionConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    concept_id: str
    relationship_label: str
    edge_type: str | None = None
    confidence: float | None = None


# ---------------------------------------------------------------------------
# Shared value objects
# ---------------------------------------------------------------------------

class SegmentMetrics(BaseModel):
    char_count: int
    word_count: int
    line_count: int
    estimated_tokens: int
    tool_call_count: int


class HiddenCounts(BaseModel):
    segments: int
    conversations: int
    projects: int


# ---------------------------------------------------------------------------
# /api/search — SearchService responses
# ---------------------------------------------------------------------------

class SessionSearchResult(BaseModel):
    session_id: str
    project: str
    date: str | None = None
    model: str | None = None
    cost: float | None = None
    snippet: str
    tool_summary: str
    tools: dict[str, int]
    turn_count: int | None = None
    topics: list[str]
    conversation_id: str | None = None
    rank: float


class SearchStatus(BaseModel):
    mode: Literal["unavailable", "keyword", "embedding", "hybrid"]
    total_sessions: int
    embedded_sessions: int
    has_graph: bool
    concept_count: int


class SearchFilterValues(BaseModel):
    projects: list[str]
    models: list[str]
    tools: list[str]
    topics: list[str]


class RelatedSession(BaseModel):
    session_id: str
    project: str
    date: str | None = None
    model: str | None = None
    summary: str
    shared_concepts: int
    conversation_id: str | None = None


# ---------------------------------------------------------------------------
# /api/segments, /api/projects/{p}/... — SessionService responses
# ---------------------------------------------------------------------------

class SegmentDetail(BaseModel):
    id: str
    source_file: str | None = None
    project_name: str
    segment_index: int
    preview: str
    timestamp: str | None = None
    conversation_id: str | None = None
    entry_number: int | None = None
    metrics: SegmentMetrics
    tool_breakdown: dict[str, int]
    raw_markdown: str


class SegmentListEntry(BaseModel):
    id: str
    source_file: str | None = None
    project_name: str
    segment_index: int
    preview: str
    timestamp: str | None = None
    conversation_id: str | None = None
    entry_number: int | None = None
    metrics: SegmentMetrics
    hidden: bool


class SegmentExport(BaseModel):
    filename: str
    content: str


class ConversationView(BaseModel):
    conversation_id: str
    project_name: str
    segment_count: int
    raw_markdown: str
    metrics: SegmentMetrics


# ---------------------------------------------------------------------------
# /api/providers, /api/projects — ProjectService responses
# ---------------------------------------------------------------------------

class ProviderEntry(BaseModel):
    id: str
    name: str
    projects: int
    segments: int


class ProjectStats(BaseModel):
    total_conversations: int
    total_words: int
    total_chars: int
    estimated_tokens: int
    total_tool_calls: int
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    request_sizes: list[int]
    conversation_timeline: list[str]
    tool_breakdown: dict[str, int]


class ProjectEntry(BaseModel):
    name: str
    display_name: str
    total_requests: int
    total_files: int
    hidden: bool
    stats: ProjectStats


# ---------------------------------------------------------------------------
# /api/stats — StatsService response
# ---------------------------------------------------------------------------

class MonthlyStat(BaseModel):
    tokens: int
    requests: int


class GlobalStats(BaseModel):
    total_projects: int
    total_segments: int
    total_chars: int
    total_words: int
    total_tool_calls: int
    estimated_tokens: int
    monthly: dict[str, MonthlyStat]
    hidden: HiddenCounts


# ---------------------------------------------------------------------------
# /api/hide/*, /api/restore/*, /api/hidden — visibility routes
# ---------------------------------------------------------------------------

class VisibilityResponse(BaseModel):
    ok: bool = True
    hidden: HiddenCounts


class HiddenSegment(BaseModel):
    id: str
    preview: str
    project_name: str
    conversation_id: str | None = None
    hidden_at: str | None = None


class HiddenConversation(BaseModel):
    key: str
    hidden_at: str | None = None


class HiddenProject(BaseModel):
    name: str
    hidden_at: str | None = None


class HiddenStateDetail(BaseModel):
    segments: list[HiddenSegment]
    conversations: list[HiddenConversation]
    projects: list[HiddenProject]


# ---------------------------------------------------------------------------
# /api/dashboard/* — DashboardService responses
# ---------------------------------------------------------------------------

class DashboardDeltas(BaseModel):
    sessions: int
    tokens: int
    cost: float
    avg_cost: float
    projects: int


class DashboardSummary(BaseModel):
    total_sessions: int
    total_tokens: int
    total_cost: float
    avg_cost_per_session: float
    project_count: int
    deltas: DashboardDeltas


class CostOverTimePeriod(BaseModel):
    period: str
    stacks: dict[str, float]


class ProjectBreakdown(BaseModel):
    project: str
    total_cost: float
    session_count: int
    avg_cost_per_session: float


class ToolUsage(BaseModel):
    tool_name: str
    call_count: int
    session_count: int
    family: str


class ModelBreakdown(BaseModel):
    model: str
    total_sessions: int
    total_cost: float
    avg_tokens_per_session: int


class SessionTypeDistribution(BaseModel):
    session_type: str
    count: int
    percentage: float
    avg_cost: float


class HeatmapDay(BaseModel):
    date: str
    sessions: int
    cost: float


class AnomalyRow(BaseModel):
    session_id: str
    project: str
    date: str | None = None
    turns: int | None = None
    tokens: int
    cost: float
    conversation_id: str | None = None
    flag: str


# ---------------------------------------------------------------------------
# /api/dashboard/graph — DashboardService.get_graph + GraphService
# ---------------------------------------------------------------------------

class GraphNode(BaseModel):
    id: str
    name: str
    type: str | None = None
    community_id: int | None = None
    degree: int
    session_count: int


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: int


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class GraphProgress(BaseModel):
    done: int
    total: int
    current: str | None = None
    ok: int
    failed: int
    model: str


class GraphStatus(BaseModel):
    status: str
    has_data: bool
    progress: GraphProgress | None = None


class GraphGenerateResponse(BaseModel):
    status: Literal["generating"]


class GraphImportResponse(BaseModel):
    ok: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# /api/summary/* — SummaryService responses
# ---------------------------------------------------------------------------

class SummaryProgress(BaseModel):
    phase: str
    done: int
    total: int
    level: int


class SummaryStatus(BaseModel):
    status: Literal["none", "pending", "ready"]
    title: str | None = None
    summary: str = ""
    progress: SummaryProgress | None = None


class SummaryDeleteResponse(BaseModel):
    ok: bool = True


# /api/summary/titles returns a plain dict[str, str] — no wrapper model needed.
