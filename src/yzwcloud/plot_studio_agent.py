from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from yzwcloud.config import PROJECT_ROOT
from yzwcloud.plot_studio_presets import list_plot_presets


DEFAULT_MODEL = "deepseek-v4-flash"

PLOT_STUDIO_AGENT_SYSTEM_PROMPT = """You are Plot Studio Param Agent.
Your only job is to convert a user's natural-language chart editing request into a JSON parameter patch.

Rules:
- Return JSON only.
- Use exactly this shape: {"param_patch": {...}, "applied": ["..."], "message": "..."}.
- param_patch keys must come from the provided parameter schema only.
- Do not invent data columns, chart types, or unsupported parameters.
- Preserve current params unless the user explicitly asks to change them.
- Values must match the schema type and select options.
- Use edit_history to understand follow-up requests like "make it bigger" or "change it back".
- Use plot_context only to understand the current chart/data; never alter data or chart type unless a matching parameter exists.
- If the user asks to rename groups, conditions, categories, or legend labels, use category_label_map when available. This is display-only and must not change data columns.
- If the request cannot be represented by the schema, return {"param_patch": {}, "applied": [], "message": "..."}.
"""


def create_plot_studio_agent_edit(
    plot_type: str,
    params: dict[str, Any],
    prompt: str,
    parameter_schema: Any = None,
    output_template: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    schema = _schema_from_payload(parameter_schema)
    preset = _preset_for_plot_type(plot_type) if not schema else None
    if not schema and not preset:
        return _response({}, [], f"Unknown Plot Studio chart type: {plot_type}")

    if not schema:
        schema = _parameter_schema(preset or {})
    llm_result = _edit_with_deepseek(
        plot_type=plot_type,
        params=params,
        prompt=prompt,
        schema=schema,
        output_template=output_template or {},
        context=context or {},
    )
    if llm_result.get("llm_status") == "missing_api_key":
        return _response(
            {},
            [],
            "请先配置 DEEPSEEK_API_KEY，然后重启后端再使用 PS Agent。",
        ) | _llm_meta(llm_result)
    if llm_result.get("llm_status") != "ok":
        return _response(
            {},
            [],
            f"DeepSeek 调用失败：{llm_result.get('llm_error') or 'unknown error'}",
        ) | _llm_meta(llm_result)

    current_params = dict(params or {})
    llm_result["param_patch"] = {
        key: value
        for key, value in (llm_result.get("param_patch") or {}).items()
        if current_params.get(key) != value
    }
    return llm_result


def _response(param_patch: dict[str, Any], applied: list[str], message: str) -> dict[str, Any]:
    return {
        "param_patch": param_patch,
        "applied": applied,
        "message": message,
    }


def _llm_meta(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in result.items()
        if key in {"llm_status", "llm_error", "model"}
    }


def _edit_with_deepseek(
    plot_type: str,
    params: dict[str, Any],
    prompt: str,
    schema: dict[str, dict[str, Any]],
    output_template: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    api_key = _env_value("DEEPSEEK_API_KEY")
    if not api_key:
        return {"llm_status": "missing_api_key"}

    base_url = _env_value("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = _env_value("DEEPSEEK_PLOT_STUDIO_MODEL", _env_value("DEEPSEEK_ROUTER_MODEL", DEFAULT_MODEL))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": PLOT_STUDIO_AGENT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "Return a JSON param_patch for this Plot Studio edit request.",
                        "contract": {
                            "input_meaning": {
                                "user_request": "Natural-language request from the user.",
                                "parameter_schema": "Only these parameters may be edited; each item explains id, label, type, default, bounds, options, and help.",
                                "current_params": "Current chart parameters before this user request.",
                                "plot_context": "Current Plot Studio source, data columns, selected chart, and edit history.",
                            },
                            "output_rules": [
                                "Return JSON only.",
                                "Only include changed parameters in param_patch.",
                                "Every param_patch key must exist in parameter_schema.",
                                "For select parameters, use one of the provided options exactly.",
                            ],
                        },
                        "plot_type": plot_type,
                        "current_params": params or {},
                        "parameter_schema": _schema_for_prompt(schema),
                        "plot_context": _compact_context(context or {}),
                        "output_template": output_template or {"param_patch": {}, "applied": [], "message": ""},
                        "user_request": prompt,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 1200,
        "temperature": 0.0,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = json.loads(response.read().decode("utf-8"))
        content = raw["choices"][0]["message"].get("content") or ""
        parsed = json.loads(content)
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
        return {"llm_status": "fallback", "llm_error": str(exc), "model": model}

    sanitized = _sanitize_llm_response(parsed, schema)
    return sanitized | {"llm_status": "ok", "model": model}


def _schema_for_prompt(schema: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    compact_schema = []
    for parameter_id, parameter in schema.items():
        compact_schema.append(
            {
                "id": parameter_id,
                "label": parameter.get("label") or parameter_id,
                "type": parameter.get("type") or "text",
                "default": parameter.get("default"),
                "min": parameter.get("min"),
                "max": parameter.get("max"),
                "options": parameter.get("options") or [],
                "help": parameter.get("help") or parameter.get("help_text") or "",
            }
        )
    return compact_schema


def _compact_context(context: dict[str, Any]) -> dict[str, Any]:
    table_summary = dict(context.get("tableSummary") or context.get("table_summary") or {})
    source = dict(context.get("source") or {})
    column_summaries = table_summary.get("column_summaries") or {}
    category_values = {
        column: (summary.get("unique_preview") or [])[:25]
        for column, summary in column_summaries.items()
        if isinstance(summary, dict) and summary.get("kind") == "categorical"
    }
    return {
        "source": {
            "name": source.get("name"),
            "type": source.get("type"),
            "summary": source.get("summary"),
            "nodeId": source.get("nodeId") or source.get("node_id"),
        },
        "table_summary": {
            "columns": (table_summary.get("columns") or [])[:80],
            "numeric_columns": (table_summary.get("numeric_columns") or [])[:80],
            "categorical_columns": (table_summary.get("categorical_columns") or [])[:80],
            "category_values": category_values,
            "scanned_rows": table_summary.get("scanned_rows"),
            "column_count": table_summary.get("column_count"),
            "signals": table_summary.get("signals"),
        },
        "selected_plot": context.get("selectedPlot") or context.get("selected_plot") or {},
        "edit_history": (context.get("editHistory") or context.get("edit_history") or [])[-8:],
    }


def _sanitize_llm_response(parsed: dict[str, Any], schema: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        return _response({}, [], "LLM did not return a JSON object.")
    raw_patch = parsed.get("param_patch") or parsed.get("params") or parsed.get("patch") or {}
    if not isinstance(raw_patch, dict):
        raw_patch = {}
    patch: dict[str, Any] = {}
    dropped: list[str] = []
    for key, value in raw_patch.items():
        parameter_id = str(key)
        if parameter_id not in schema:
            dropped.append(parameter_id)
            continue
        normalized = _normalize_value(schema[parameter_id], value)
        if normalized is not None:
            patch[parameter_id] = normalized
    applied = parsed.get("applied")
    if not isinstance(applied, list):
        applied = [f"{key}={value}" for key, value in patch.items()]
    applied = [str(item) for item in applied]
    message = str(parsed.get("message") or f"Applied {len(patch)} Plot Studio parameter edit(s).")
    if dropped:
        message = f"{message} Dropped unsupported parameter(s): {', '.join(dropped)}."
    return _response(patch, applied, message)


def _env_value(name: str, default: str = "") -> str:
    if name in os.environ:
        return os.environ[name]
    env_path = Path(PROJECT_ROOT) / ".env"
    if not env_path.exists():
        return default
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return default


def _preset_for_plot_type(plot_type: str) -> dict[str, Any] | None:
    normalized = str(plot_type or "").strip()
    return next((preset for preset in list_plot_presets() if preset.get("id") == normalized), None)


def _parameter_schema(preset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    schema: dict[str, dict[str, Any]] = {}
    for group in preset.get("parameter_groups") or []:
        for parameter in group.get("parameters") or []:
            parameter_id = str(parameter.get("id") or "")
            if parameter_id:
                schema[parameter_id] = dict(parameter)
    for parameter_id, default_value in (preset.get("default_params") or {}).items():
        schema.setdefault(
            str(parameter_id),
            {
                "id": str(parameter_id),
                "type": _infer_parameter_type(default_value),
                "default": default_value,
            },
        )
    return schema


def _schema_from_payload(parameter_schema: Any) -> dict[str, dict[str, Any]]:
    if not parameter_schema:
        return {}
    if isinstance(parameter_schema, dict):
        if "parameter_groups" in parameter_schema:
            return _parameter_schema(parameter_schema)
        if "parameters" in parameter_schema:
            return _parameter_schema({"parameter_groups": [parameter_schema]})
        return {
            str(parameter_id): dict(parameter)
            for parameter_id, parameter in parameter_schema.items()
            if isinstance(parameter, dict)
        }
    if isinstance(parameter_schema, list):
        return _parameter_schema({"parameter_groups": parameter_schema})
    return {}


def _infer_parameter_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "text"


def _normalize_value(parameter: dict[str, Any], value: Any) -> Any:
    parameter_type = parameter.get("type")
    if parameter_type == "boolean":
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"false", "off", "no", "0", "hide", "hidden", "disable", "disabled"}:
                return False
            if normalized in {"true", "on", "yes", "1", "show", "enable", "enabled"}:
                return True
        return bool(value)
    if parameter_type == "number":
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return parameter.get("default")
        if parameter.get("min") is not None:
            numeric = max(float(parameter["min"]), numeric)
        if parameter.get("max") is not None:
            numeric = min(float(parameter["max"]), numeric)
        return int(numeric) if numeric.is_integer() else numeric
    if parameter_type == "select":
        options = parameter.get("options") or []
        if value in options:
            return value
        normalized_value = str(value).strip().lower()
        for option in options:
            if str(option).strip().lower() == normalized_value:
                return option
        return None
    if parameter_type == "json":
        return value if isinstance(value, (dict, list)) else None
    return value
