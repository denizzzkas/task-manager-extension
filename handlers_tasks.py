"""Task Planner · CRUD handlers."""
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult
from app import chat

TASKS = "tasks"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_overdue(deadline: str) -> bool:
    if not deadline:
        return False
    try:
        return datetime.fromisoformat(deadline) < datetime.now(timezone.utc)
    except Exception:
        return False


# ── Models ────────────────────────────────────────────────────────────────────

class CreateTaskParams(BaseModel):
    title: str = Field(description="Task title")
    description: str = Field(default="", description="Task description")
    priority: str = Field(default="medium", description="low / medium / high")
    deadline: str = Field(default="", description="ISO datetime, e.g. 2026-05-01T10:00:00")


class GetTasksParams(BaseModel):
    status: str = Field(default="", description="new / in_progress / completed / cancelled")
    priority: str = Field(default="", description="low / medium / high")
    overdue_only: bool = Field(default=False, description="Only overdue tasks")


class UpdateTaskParams(BaseModel):
    task_id: str = Field(description="Task ID")
    title: str = Field(default="")
    description: str = Field(default="")
    status: str = Field(default="")
    priority: str = Field(default="")
    deadline: str = Field(default="")
    reminder_enabled: bool = Field(default=False)


class TaskIdParams(BaseModel):
    task_id: str = Field(description="Task ID")


class SearchTasksParams(BaseModel):
    query: str = Field(description="Search query")


class ExportTasksParams(BaseModel):
    format: str = Field(default="json", description="json or csv")


# ── Handlers ──────────────────────────────────────────────────────────────────

@chat.function("create_task", action_type="write", event="task.created",
               description="Create a new task with title, description, priority and deadline.")
async def fn_create_task(ctx, params: CreateTaskParams) -> ActionResult:
    """Create a new task."""
    if not params.title.strip():
        return ActionResult.error("Title is required.")
    priority = params.priority if params.priority in ("low", "medium", "high") else "medium"
    now = _now()
    doc = await ctx.store.create(TASKS, {
        "owner": ctx.user.id,
        "title": params.title.strip(),
        "description": params.description,
        "status": "new",
        "priority": priority,
        "deadline": params.deadline,
        "reminder_enabled": False,
        "reminder_sent": False,
        "created_at": now,
        "updated_at": now,
    })
    return ActionResult.success(
        data={"task_id": doc.id, "title": params.title},
        summary=f"Task created: {params.title}",
    )


@chat.function("get_tasks", action_type="read",
               description="Get task list with optional filters by status, priority or overdue.")
async def fn_get_tasks(ctx, params: GetTasksParams) -> ActionResult:
    """Get tasks with optional filters."""
    where = {"owner": ctx.user.id}
    if params.status:
        where["status"] = params.status
    if params.priority:
        where["priority"] = params.priority
    page = await ctx.store.query(TASKS, where=where, order_by="created_at")
    tasks = [{**doc.data, "id": doc.id} for doc in page.data]
    if params.overdue_only:
        tasks = [t for t in tasks if _is_overdue(t.get("deadline", "")) and t.get("status") not in ("completed", "cancelled")]
    return ActionResult.success(
        data={"tasks": tasks, "total": len(tasks)},
        summary=f"Found {len(tasks)} task(s)",
    )


@chat.function("update_task", action_type="write", event="task.updated",
               description="Update task fields: title, description, status, priority, deadline.")
async def fn_update_task(ctx, params: UpdateTaskParams) -> ActionResult:
    """Update a task."""
    doc = await ctx.store.get(TASKS, params.task_id)
    if not doc or doc.data.get("owner") != ctx.user.id:
        return ActionResult.error("Task not found.")
    updates = {"updated_at": _now()}
    for field in ("title", "description", "status", "priority", "deadline"):
        val = getattr(params, field)
        if val:
            updates[field] = val
    if params.reminder_enabled:
        updates["reminder_enabled"] = True
    await ctx.store.update(TASKS, params.task_id, updates)
    return ActionResult.success(
        data={"task_id": params.task_id},
        summary=f"Task updated: {doc.data.get('title')}",
    )


@chat.function("delete_task", action_type="destructive", event="task.deleted",
               description="Delete a task permanently.")
async def fn_delete_task(ctx, params: TaskIdParams) -> ActionResult:
    """Delete a task."""
    doc = await ctx.store.get(TASKS, params.task_id)
    if not doc or doc.data.get("owner") != ctx.user.id:
        return ActionResult.error("Task not found.")
    await ctx.store.delete(TASKS, params.task_id)
    return ActionResult.success(
        data={"task_id": params.task_id},
        summary=f"Task deleted: {doc.data.get('title')}",
    )


@chat.function("complete_task", action_type="write", event="task.completed",
               description="Mark a task as completed.")
async def fn_complete_task(ctx, params: TaskIdParams) -> ActionResult:
    """Mark task as completed."""
    doc = await ctx.store.get(TASKS, params.task_id)
    if not doc or doc.data.get("owner") != ctx.user.id:
        return ActionResult.error("Task not found.")
    await ctx.store.update(TASKS, params.task_id, {"status": "completed", "updated_at": _now()})
    return ActionResult.success(
        data={"task_id": params.task_id},
        summary=f"Completed: {doc.data.get('title')}",
    )


@chat.function("search_tasks", action_type="read",
               description="Search tasks by title or description.")
async def fn_search_tasks(ctx, params: SearchTasksParams) -> ActionResult:
    """Search tasks by text."""
    page = await ctx.store.query(TASKS, where={"owner": ctx.user.id})
    q = params.query.lower()
    results = [
        {**doc.data, "id": doc.id} for doc in page.data
        if q in doc.data.get("title", "").lower() or q in doc.data.get("description", "").lower()
    ]
    return ActionResult.success(
        data={"results": results, "total": len(results), "query": params.query},
        summary=f"Found {len(results)} task(s) for '{params.query}'",
    )


@chat.function("export_tasks", action_type="read",
               description="Export all tasks as JSON or CSV.")
async def fn_export_tasks(ctx, params: ExportTasksParams) -> ActionResult:
    """Export tasks as JSON or CSV."""
    page = await ctx.store.query(TASKS, where={"owner": ctx.user.id})
    tasks = [{**doc.data, "id": doc.id} for doc in page.data]
    if params.format == "csv":
        headers = "id,title,status,priority,deadline,created_at"
        rows = [headers] + [
            f"{t.get('id','')},{t.get('title','')},{t.get('status','')},{t.get('priority','')},{t.get('deadline','')},{t.get('created_at','')}"
            for t in tasks
        ]
        content = "\n".join(rows)
    else:
        import json
        content = json.dumps(tasks, ensure_ascii=False, indent=2)
    return ActionResult.success(
        data={"content": content, "format": params.format, "total": len(tasks)},
        summary=f"Exported {len(tasks)} task(s) as {params.format.upper()}",
    )
