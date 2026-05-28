"""Self-contained HTML report rendering utilities."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from html import escape
from pathlib import Path
from typing import Any

from datamapx.report.errors import ReportWriteError

HTML_PREVIEW_LIMIT = 20


def write_html_report(
    path: Path,
    payload: Mapping[str, Any],
    *,
    error_rows: Sequence[Mapping[str, Any]] | None = None,
    skipped_rows: Sequence[Mapping[str, Any]] | None = None,
) -> Path:
    """Write a browser-readable HTML report."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            build_html_report(
                payload,
                error_rows=error_rows or [],
                skipped_rows=skipped_rows or [],
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        raise ReportWriteError(f"{path}: cannot write HTML report: {exc}") from exc
    return path


def build_html_report(
    payload: Mapping[str, Any],
    *,
    error_rows: Sequence[Mapping[str, Any]] | None = None,
    skipped_rows: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Render a complete HTML document for a report payload."""

    error_rows = list(error_rows or [])
    skipped_rows = list(skipped_rows or [])
    title = f"DataMapX HTML report - {payload.get('project_name', 'unknown project')}"
    summary_items = [
        ("Project", payload.get("project_name")),
        ("Status", payload.get("status")),
        ("Run ID", payload.get("run_id")),
        ("Started at", payload.get("started_at")),
        ("Finished at", payload.get("finished_at")),
        ("Final outcome", _get_nested(payload, "notes", "final_outcome")),
        ("Config path", payload.get("config_path")),
    ]
    notes = payload.get("notes")
    counts = payload.get("counts")
    reports = payload.get("reports")

    parts = [
        "<!doctype html>",
        "<html lang=\"en\">",
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_escape(title)}</title>",
        "<style>",
        "body{font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "margin:0;background:#f7f7f8;color:#202124;line-height:1.5}",
        ".page{max-width:1180px;margin:0 auto;padding:32px 20px 48px}",
        ".hero{background:linear-gradient(135deg,#ffffff 0%,#eef3ff 100%);"
        "border:1px solid #d7ddea;border-radius:16px;padding:24px 28px;"
        "box-shadow:0 8px 30px rgba(32,33,36,.08)}",
        "h1{margin:0 0 8px;font-size:32px}",
        ".subtitle{margin:0;color:#5f6368}",
        "section{margin-top:24px;background:#fff;border:1px solid #e3e6ef;border-radius:14px;"
        "padding:20px 22px;box-shadow:0 2px 12px rgba(32,33,36,.04)}",
        "h2{margin:0 0 14px;font-size:20px}",
        ".meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}",
        ".card{background:#fafbff;border:1px solid #e6eaf5;border-radius:12px;padding:12px 14px}",
        ".label{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#5f6368;margin-bottom:4px}",
        ".value{font-size:14px;word-break:break-word}",
        ".table-wrap{overflow:auto}",
        "table{width:100%;border-collapse:collapse;min-width:100%}",
        "th,td{border-bottom:1px solid #e6e8ef;padding:8px 10px;"
        "vertical-align:top;text-align:left}",
        "th{position:sticky;top:0;background:#f8f9fc;font-size:12px;"
        "text-transform:uppercase;letter-spacing:.04em;color:#5f6368}",
        "tbody tr:hover{background:#f9fbff}",
        ".muted{color:#5f6368}",
        ".preview-note{margin:0 0 12px;color:#5f6368;font-size:14px}",
        ".json{white-space:pre-wrap;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}",
        "</style>",
        "</head>",
        "<body>",
        '<div class="page">',
        '<header class="hero">',
        f"<h1>{_escape(title)}</h1>",
        '<p class="subtitle">Self-contained HTML summary of the latest DataMapX execution.</p>',
        "</header>",
        _render_section("Summary", _render_cards(summary_items)),
        _render_section("Counts", _render_cards(_count_items(counts))),
    ]

    if payload.get("input"):
        parts.append(_render_section("Input", _render_dict_block(payload["input"])))
    if payload.get("references"):
        parts.append(
            _render_section(
                "References",
                _render_table(
                    payload["references"],
                    ["name", "path", "rows_loaded", "key"],
                ),
            )
        )
    if payload.get("inputs"):
        parts.append(
            _render_section(
                "Inputs",
                _render_table(
                    payload["inputs"],
                    ["name", "path", "rows_loaded", "key"],
                ),
            )
        )

    if payload.get("output"):
        parts.append(_render_section("Output", _render_dict_block(payload["output"])))
    if payload.get("outputs"):
        parts.append(
            _render_section(
                "Outputs",
                _render_table(
                    payload["outputs"],
                    ["name", "path", "rows_previewed", "file_written", "columns"],
                ),
            )
        )

    if payload.get("checks") is not None:
        parts.append(
            _render_section(
                "Checks",
                _render_table(
                    payload["checks"],
                    ["name", "rule", "passed", "evaluated_value", "message"],
                ),
            )
        )

    if error_rows:
        parts.append(
            _render_section(
                "Error preview",
                _render_preview(
                    error_rows[:HTML_PREVIEW_LIMIT],
                    count=len(error_rows),
                    columns=[
                        "run_id",
                        "input_name",
                        "output_name",
                        "row_number",
                        "stage",
                        "field",
                        "rule",
                        "message",
                        "row_json",
                    ],
                ),
            )
        )

    if skipped_rows:
        parts.append(
            _render_section(
                "Skipped preview",
                _render_preview(
                    skipped_rows[:HTML_PREVIEW_LIMIT],
                    count=len(skipped_rows),
                    columns=["run_id", "input_name", "row_number", "reason", "row_json"],
                ),
            )
        )

    if reports:
        parts.append(_render_section("Reports", _render_table([reports], list(reports.keys()))))
    if notes:
        parts.append(_render_section("Notes", _render_dict_block(notes)))

    parts.extend(["</div>", "</body>", "</html>"])
    return "\n".join(parts)


def _render_section(title: str, body: str) -> str:
    return f'<section><h2>{_escape(title)}</h2>{body}</section>'


def _render_cards(items: Sequence[tuple[str, Any]]) -> str:
    cards = []
    for label, value in items:
        cards.append(
            "<div class=\"card\">"
            f"<div class=\"label\">{_escape(label)}</div>"
            f"<div class=\"value\">{_format_value(value)}</div>"
            "</div>"
        )
    return f'<div class="meta">{"".join(cards)}</div>' if cards else '<p class="muted">(none)</p>'


def _render_dict_block(values: Mapping[str, Any]) -> str:
    rows = [
        f"<tr><th>{_escape(str(key))}</th><td>{_format_value(value)}</td></tr>"
        for key, value in values.items()
    ]
    return (
        f'<div class="table-wrap"><table>{"".join(rows)}</table></div>'
        if rows
        else '<p class="muted">(none)</p>'
    )


def _render_table(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    if not rows:
        return '<p class="muted">(none)</p>'
    header = "".join(f"<th>{_escape(column)}</th>" for column in columns)
    body_rows = []
    for row in rows:
        body_rows.append(
            "<tr>"
            + "".join(f"<td>{_format_value(row.get(column))}</td>" for column in columns)
            + "</tr>"
        )
    return (
        f'<div class="table-wrap"><table><thead><tr>{header}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody></table></div>'
    )


def _render_preview(
    rows: Sequence[Mapping[str, Any]],
    *,
    count: int,
    columns: Sequence[str],
) -> str:
    note = f'<p class="preview-note">Showing {len(rows)} of {count} rows.</p>'
    return note + _render_table(rows, columns)


def _count_items(counts: Any) -> list[tuple[str, Any]]:
    if not isinstance(counts, Mapping):
        return []
    preferred_order = [
        "input_rows",
        "output_rows",
        "skipped_rows",
        "error_rows",
        "validation_errors",
        "mapping_errors",
        "lookup_missing_errors",
        "transform_errors",
        "input_validation_errors",
        "output_validation_errors",
        "check_failures",
        "check_successes",
    ]
    items = [(key, counts[key]) for key in preferred_order if key in counts]
    for key, value in counts.items():
        if key not in {item[0] for item in items}:
            items.append((key, value))
    return items


def _format_value(value: Any) -> str:
    if value is None:
        return '<span class="muted">(none)</span>'
    if isinstance(value, bool):
        return _escape("true" if value else "false")
    if isinstance(value, (int, float)):
        return _escape(str(value))
    if isinstance(value, (list, dict, tuple)):
        return (
            f'<span class="json">'
            f'{_escape(json.dumps(value, ensure_ascii=False, default=str))}'
            f'</span>'
        )
    return _escape(str(value))


def _escape(value: Any) -> str:
    return escape(str(value), quote=True)


def _get_nested(payload: Mapping[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current
