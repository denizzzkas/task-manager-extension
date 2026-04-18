"""Task Planner · Panel."""
from __future__ import annotations

from datetime import datetime, timezone

from imperal_sdk import ui
from imperal_sdk.ui.actions import Call, Send

from app import ext

TASKS = "tasks"

_PRIORITY_ICON = {"high": "AlertTriangle", "medium": "Minus", "low": "ArrowDown"}
_PRIORITY_COLOR = {"high": "red", "medium": "yellow", "low": "blue"}
_STATUS_COLOR = {"new": "gray", "in_progress": "blue", "completed": "green", "cancelled": "red"}


def _is_overdue(deadline: str) -> bool:
    if not deadline:
        return False
    try:
        return datetime.fromisoformat(deadline) < datetime.now(timezone.utc)
    except Exception:
        return False


def _fmt_deadline(deadline: str) -> str:
    if not deadline:
        return ""
    try:
        dt = datetime.fromisoformat(deadline)
        return dt.strftime("%d %b %Y")
    except Exception:
        return deadline


@ext.panel(
    "tasks", slot="left", title="Task Planner", icon="CheckSquare",
    default_width=300, min_width=240, max_width=420,
    refresh="on_event:task.created,task.updated,task.deleted,task.completed",
)
async def panel_tasks(ctx, tab: str = "all", **kwargs):
    """Task Planner sidebar panel."""
    try:
        page = await ctx.store.query(TASKS, where={"owner": ctx.user.id}, order_by="created_at")
        all_tasks = [{**doc.data, "id": doc.id} for doc in page.data]
    except Exception:
        all_tasks = []

    active = [t for t in all_tasks if t.get("status") in ("new", "in_progress")]
    completed = [t for t in all_tasks if t.get("status") == "completed"]
    overdue = [t for t in all_tasks if _is_overdue(t.get("deadline", "")) and t.get("status") not in ("completed", "cancelled")]

    if tab == "active":
        tasks = active
    elif tab == "completed":
        tasks = completed
    elif tab == "overdue":
        tasks = overdue
    else:
        tasks = all_tasks

    stats = ui.Stats([
        ui.Stat("Total", len(all_tasks), icon="List", color="blue"),
        ui.Stat("Open", len(active), icon="Clock", color="yellow"),
        ui.Stat("Done", len(completed), icon="CheckCircle", color="green"),
        ui.Stat("Overdue", len(overdue), icon="AlertTriangle", color="red"),
    ], columns=4)

    tabs = ui.Tabs(tabs=[
        {"label": "All", "content": _task_list(all_tasks)},
        {"label": "Active", "content": _task_list(active)},
        {"label": "Completed", "content": _task_list(completed)},
        {"label": "Overdue", "content": _task_list(overdue)},
    ], default_tab=["all", "active", "completed", "overdue"].index(tab) if tab in ("all", "active", "completed", "overdue") else 0)

    toolbar = ui.Stack([
        ui.Button("+ New Task", variant="primary", size="sm", icon="Plus",
                  on_click=Send("Create a new task")),
    ], direction="h", sticky=True)

    return ui.Stack([toolbar, stats, tabs], direction="v", gap=2)


def _task_list(tasks: list) -> ui.Stack:
    if not tasks:
        return ui.Empty(message="No tasks", icon="CheckSquare")

    items = []
    for t in tasks:
        priority = t.get("priority", "medium")
        deadline = t.get("deadline", "")
        status = t.get("status", "new")
        overdue = _is_overdue(deadline)

        subtitle_parts = []
        if deadline:
            subtitle_parts.append(("⚠ " if overdue else "") + _fmt_deadline(deadline))
        subtitle_parts.append(status.replace("_", " "))

        actions = []
        if status not in ("completed", "cancelled"):
            actions.append({
                "icon": "CheckCircle",
                "label": "Complete",
                "on_click": Call("complete_task", task_id=t.get("id", "")),
            })
        actions.append({
            "icon": "Trash2",
            "label": "Delete",
            "on_click": Call("delete_task", task_id=t.get("id", "")),
            "confirm": f"Delete '{t.get('title', '')}'?",
        })

        items.append(ui.ListItem(
            id=t.get("id", ""),
            title=t.get("title", "Untitled"),
            subtitle=" · ".join(subtitle_parts),
            icon=_PRIORITY_ICON.get(priority, "Minus"),
            badge=ui.Badge(priority, color=_PRIORITY_COLOR.get(priority, "gray")),
            expandable=bool(t.get("description")),
            expanded_content=[ui.Text(t["description"])] if t.get("description") else [],
            actions=actions,
        ))

    return ui.List(items=items, page_size=20)
