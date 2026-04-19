"""Task Planner · Tests.

Covers: CRUD handlers, skeleton refresh/alert, deadline_check schedule, panel render.
"""
from datetime import datetime, timedelta, timezone

import pytest
from imperal_sdk.testing import MockContext

from handlers_tasks import (
    CreateTaskParams, ExportTasksParams, GetTasksParams,
    SearchTasksParams, TaskIdParams, UpdateTaskParams,
    fn_complete_task, fn_create_task, fn_delete_task,
    fn_export_tasks, fn_get_tasks, fn_search_tasks, fn_update_task,
)
from skeleton import deadline_check, skeleton_alert_tasks, skeleton_refresh_tasks


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_ctx(user_id: str = "test_user"):
    return MockContext(user_id=user_id)


# ── create_task ───────────────────────────────────────────────────────────────

class TestCreateTask:
    async def test_basic(self):
        ctx = make_ctx()
        r = await fn_create_task(ctx, CreateTaskParams(title="Buy milk"))
        assert r.status == "success"
        assert r.data["title"] == "Buy milk"
        assert "task_id" in r.data

    async def test_empty_title_fails(self):
        ctx = make_ctx()
        r = await fn_create_task(ctx, CreateTaskParams(title="   "))
        assert r.status == "error"

    async def test_invalid_priority_defaults_to_medium(self):
        ctx = make_ctx()
        r = await fn_create_task(ctx, CreateTaskParams(title="T", priority="urgent"))
        doc = await ctx.store.get("tasks", r.data["task_id"])
        assert doc.data["priority"] == "medium"

    async def test_sets_owner_and_status(self):
        ctx = make_ctx()
        r = await fn_create_task(ctx, CreateTaskParams(title="T"))
        doc = await ctx.store.get("tasks", r.data["task_id"])
        assert doc.data["owner"] == "test_user"
        assert doc.data["status"] == "new"
        assert doc.data["reminder_enabled"] is False
        assert doc.data["reminder_sent"] is False

    async def test_task_id_is_doc_id(self):
        """task_id in result must equal doc.id (store internal key)."""
        ctx = make_ctx()
        r = await fn_create_task(ctx, CreateTaskParams(title="T"))
        fetched = await ctx.store.get("tasks", r.data["task_id"])
        assert fetched is not None


# ── get_tasks ─────────────────────────────────────────────────────────────────

class TestGetTasks:
    async def test_all(self):
        ctx = make_ctx()
        await fn_create_task(ctx, CreateTaskParams(title="T1"))
        await fn_create_task(ctx, CreateTaskParams(title="T2"))
        r = await fn_get_tasks(ctx, GetTasksParams())
        assert r.data["total"] == 2

    async def test_filter_by_status(self):
        ctx = make_ctx()
        r1 = await fn_create_task(ctx, CreateTaskParams(title="T1"))
        await fn_complete_task(ctx, TaskIdParams(task_id=r1.data["task_id"]))
        await fn_create_task(ctx, CreateTaskParams(title="T2"))
        r = await fn_get_tasks(ctx, GetTasksParams(status="completed"))
        assert r.data["total"] == 1
        assert r.data["tasks"][0]["title"] == "T1"

    async def test_filter_by_priority(self):
        ctx = make_ctx()
        await fn_create_task(ctx, CreateTaskParams(title="H", priority="high"))
        await fn_create_task(ctx, CreateTaskParams(title="L", priority="low"))
        r = await fn_get_tasks(ctx, GetTasksParams(priority="high"))
        assert r.data["total"] == 1

    async def test_overdue_only(self):
        ctx = make_ctx()
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        await fn_create_task(ctx, CreateTaskParams(title="Past", deadline=past))
        await fn_create_task(ctx, CreateTaskParams(title="Future", deadline=future))
        r = await fn_get_tasks(ctx, GetTasksParams(overdue_only=True))
        assert r.data["total"] == 1
        assert r.data["tasks"][0]["title"] == "Past"

    async def test_overdue_excludes_completed(self):
        ctx = make_ctx()
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        r1 = await fn_create_task(ctx, CreateTaskParams(title="Done", deadline=past))
        await fn_complete_task(ctx, TaskIdParams(task_id=r1.data["task_id"]))
        r = await fn_get_tasks(ctx, GetTasksParams(overdue_only=True))
        assert r.data["total"] == 0

    async def test_tasks_include_id(self):
        """Returned task dicts must include 'id' (doc.id) for panel actions."""
        ctx = make_ctx()
        cr = await fn_create_task(ctx, CreateTaskParams(title="T"))
        r = await fn_get_tasks(ctx, GetTasksParams())
        assert r.data["tasks"][0]["id"] == cr.data["task_id"]


# ── update_task ───────────────────────────────────────────────────────────────

class TestUpdateTask:
    async def test_update_title(self):
        ctx = make_ctx()
        cr = await fn_create_task(ctx, CreateTaskParams(title="Old"))
        await fn_update_task(ctx, UpdateTaskParams(task_id=cr.data["task_id"], title="New"))
        doc = await ctx.store.get("tasks", cr.data["task_id"])
        assert doc.data["title"] == "New"

    async def test_enable_reminder(self):
        ctx = make_ctx()
        cr = await fn_create_task(ctx, CreateTaskParams(title="T"))
        await fn_update_task(ctx, UpdateTaskParams(
            task_id=cr.data["task_id"], reminder_enabled=True
        ))
        doc = await ctx.store.get("tasks", cr.data["task_id"])
        assert doc.data["reminder_enabled"] is True

    async def test_not_found(self):
        ctx = make_ctx()
        r = await fn_update_task(ctx, UpdateTaskParams(task_id="ghost"))
        assert r.status == "error"

    async def test_other_user_cannot_update(self):
        ctx = make_ctx()
        cr = await fn_create_task(ctx, CreateTaskParams(title="T"))
        ctx2 = make_ctx(user_id="attacker")
        ctx2.store = ctx.store
        r = await fn_update_task(ctx2, UpdateTaskParams(task_id=cr.data["task_id"], title="X"))
        assert r.status == "error"


# ── delete_task ───────────────────────────────────────────────────────────────

class TestDeleteTask:
    async def test_delete(self):
        ctx = make_ctx()
        cr = await fn_create_task(ctx, CreateTaskParams(title="T"))
        r = await fn_delete_task(ctx, TaskIdParams(task_id=cr.data["task_id"]))
        assert r.status == "success"
        assert await ctx.store.get("tasks", cr.data["task_id"]) is None

    async def test_not_found(self):
        ctx = make_ctx()
        r = await fn_delete_task(ctx, TaskIdParams(task_id="ghost"))
        assert r.status == "error"

    async def test_other_user_cannot_delete(self):
        ctx = make_ctx()
        cr = await fn_create_task(ctx, CreateTaskParams(title="T"))
        ctx2 = make_ctx(user_id="attacker")
        ctx2.store = ctx.store
        r = await fn_delete_task(ctx2, TaskIdParams(task_id=cr.data["task_id"]))
        assert r.status == "error"


# ── complete_task ─────────────────────────────────────────────────────────────

class TestCompleteTask:
    async def test_completes(self):
        ctx = make_ctx()
        cr = await fn_create_task(ctx, CreateTaskParams(title="T"))
        r = await fn_complete_task(ctx, TaskIdParams(task_id=cr.data["task_id"]))
        assert r.status == "success"
        doc = await ctx.store.get("tasks", cr.data["task_id"])
        assert doc.data["status"] == "completed"

    async def test_not_found(self):
        ctx = make_ctx()
        r = await fn_complete_task(ctx, TaskIdParams(task_id="ghost"))
        assert r.status == "error"


# ── search_tasks ──────────────────────────────────────────────────────────────

class TestSearchTasks:
    async def test_by_title(self):
        ctx = make_ctx()
        await fn_create_task(ctx, CreateTaskParams(title="Buy groceries"))
        await fn_create_task(ctx, CreateTaskParams(title="Write report"))
        r = await fn_search_tasks(ctx, SearchTasksParams(query="grocer"))
        assert r.data["total"] == 1

    async def test_by_description(self):
        ctx = make_ctx()
        await fn_create_task(ctx, CreateTaskParams(title="T", description="urgent meeting"))
        r = await fn_search_tasks(ctx, SearchTasksParams(query="meeting"))
        assert r.data["total"] == 1

    async def test_case_insensitive(self):
        ctx = make_ctx()
        await fn_create_task(ctx, CreateTaskParams(title="Buy Milk"))
        r = await fn_search_tasks(ctx, SearchTasksParams(query="milk"))
        assert r.data["total"] == 1

    async def test_no_results(self):
        ctx = make_ctx()
        await fn_create_task(ctx, CreateTaskParams(title="T"))
        r = await fn_search_tasks(ctx, SearchTasksParams(query="zzz"))
        assert r.data["total"] == 0

    async def test_results_include_id(self):
        ctx = make_ctx()
        cr = await fn_create_task(ctx, CreateTaskParams(title="Task"))
        r = await fn_search_tasks(ctx, SearchTasksParams(query="task"))
        assert r.data["results"][0]["id"] == cr.data["task_id"]


# ── export_tasks ──────────────────────────────────────────────────────────────

class TestExportTasks:
    async def test_json(self):
        import json
        ctx = make_ctx()
        await fn_create_task(ctx, CreateTaskParams(title="T1"))
        r = await fn_export_tasks(ctx, ExportTasksParams(format="json"))
        assert r.status == "success"
        data = json.loads(r.data["content"])
        assert len(data) == 1
        assert data[0]["title"] == "T1"
        assert "id" in data[0]

    async def test_csv(self):
        ctx = make_ctx()
        await fn_create_task(ctx, CreateTaskParams(title="T1"))
        r = await fn_export_tasks(ctx, ExportTasksParams(format="csv"))
        lines = r.data["content"].split("\n")
        assert lines[0] == "id,title,status,priority,deadline,created_at"
        assert "T1" in lines[1]

    async def test_empty(self):
        ctx = make_ctx()
        r = await fn_export_tasks(ctx, ExportTasksParams())
        assert r.data["total"] == 0


# ── skeleton_refresh_tasks ────────────────────────────────────────────────────

class TestSkeletonRefresh:
    async def test_empty(self):
        ctx = make_ctx()
        r = await skeleton_refresh_tasks(ctx)
        assert r["response"] == {"total": 0, "active": 0, "completed": 0, "overdue": 0}

    async def test_counts(self):
        ctx = make_ctx()
        await fn_create_task(ctx, CreateTaskParams(title="T1"))
        cr2 = await fn_create_task(ctx, CreateTaskParams(title="T2"))
        await fn_complete_task(ctx, TaskIdParams(task_id=cr2.data["task_id"]))
        r = await skeleton_refresh_tasks(ctx)
        s = r["response"]
        assert s["total"] == 2
        assert s["active"] == 1
        assert s["completed"] == 1

    async def test_overdue_count(self):
        ctx = make_ctx()
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        await fn_create_task(ctx, CreateTaskParams(title="T", deadline=past))
        r = await skeleton_refresh_tasks(ctx)
        assert r["response"]["overdue"] == 1

    async def test_updates_skeleton(self):
        ctx = make_ctx()
        await fn_create_task(ctx, CreateTaskParams(title="T"))
        await skeleton_refresh_tasks(ctx)
        data = await ctx.skeleton.get("task_stats")
        assert data is not None and data["total"] == 1


# ── skeleton_alert_tasks ──────────────────────────────────────────────────────

class TestSkeletonAlert:
    async def test_alert_on_increase(self):
        ctx = make_ctx()
        await skeleton_alert_tasks(ctx, old={"overdue": 1}, new={"overdue": 3})
        assert len(ctx.notify.sent) == 1
        assert "2 task(s)" in ctx.notify.sent[0]["message"]

    async def test_no_alert_same(self):
        ctx = make_ctx()
        await skeleton_alert_tasks(ctx, old={"overdue": 2}, new={"overdue": 2})
        assert len(ctx.notify.sent) == 0

    async def test_no_alert_decrease(self):
        ctx = make_ctx()
        await skeleton_alert_tasks(ctx, old={"overdue": 3}, new={"overdue": 1})
        assert len(ctx.notify.sent) == 0

    async def test_no_data(self):
        ctx = make_ctx()
        r = await skeleton_alert_tasks(ctx)
        assert r["response"] == "No changes."


# ── deadline_check ────────────────────────────────────────────────────────────

class TestDeadlineCheck:
    async def test_sends_reminder(self):
        ctx = make_ctx()
        soon = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        cr = await fn_create_task(ctx, CreateTaskParams(title="Meeting", deadline=soon))
        await ctx.store.update("tasks", cr.data["task_id"], {"reminder_enabled": True})
        await deadline_check(ctx)
        assert len(ctx.notify.sent) == 1
        assert "Meeting" in ctx.notify.sent[0]["message"]

    async def test_no_reminder_if_disabled(self):
        ctx = make_ctx()
        soon = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        await fn_create_task(ctx, CreateTaskParams(title="T", deadline=soon))
        await deadline_check(ctx)
        assert len(ctx.notify.sent) == 0

    async def test_no_reminder_if_already_sent(self):
        ctx = make_ctx()
        soon = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        cr = await fn_create_task(ctx, CreateTaskParams(title="T", deadline=soon))
        await ctx.store.update("tasks", cr.data["task_id"], {
            "reminder_enabled": True, "reminder_sent": True
        })
        await deadline_check(ctx)
        assert len(ctx.notify.sent) == 0

    async def test_no_reminder_for_completed(self):
        ctx = make_ctx()
        soon = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        cr = await fn_create_task(ctx, CreateTaskParams(title="Done", deadline=soon))
        await fn_complete_task(ctx, TaskIdParams(task_id=cr.data["task_id"]))
        await ctx.store.update("tasks", cr.data["task_id"], {"reminder_enabled": True})
        await deadline_check(ctx)
        assert len(ctx.notify.sent) == 0

    async def test_sets_reminder_sent_flag(self):
        ctx = make_ctx()
        soon = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        cr = await fn_create_task(ctx, CreateTaskParams(title="T", deadline=soon))
        await ctx.store.update("tasks", cr.data["task_id"], {"reminder_enabled": True})
        await deadline_check(ctx)
        doc = await ctx.store.get("tasks", cr.data["task_id"])
        assert doc.data["reminder_sent"] is True

    async def test_no_reminder_far_future(self):
        ctx = make_ctx()
        far = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        cr = await fn_create_task(ctx, CreateTaskParams(title="T", deadline=far))
        await ctx.store.update("tasks", cr.data["task_id"], {"reminder_enabled": True})
        await deadline_check(ctx)
        assert len(ctx.notify.sent) == 0

    async def test_empty_uid_returns_early(self):
        ctx = make_ctx(user_id="")
        await deadline_check(ctx)
        assert len(ctx.notify.sent) == 0


# ── panel render ──────────────────────────────────────────────────────────────

class TestPanel:
    async def test_renders(self):
        from imperal_sdk.ui.base import UINode
        from panels import panel_tasks
        ctx = make_ctx()
        await fn_create_task(ctx, CreateTaskParams(title="Task 1", priority="high"))
        result = await panel_tasks(ctx)
        assert isinstance(result, UINode)
        assert result.type == "Stack"

    async def test_empty_renders(self):
        from imperal_sdk.ui.base import UINode
        from panels import panel_tasks
        ctx = make_ctx()
        result = await panel_tasks(ctx)
        assert isinstance(result, UINode)

    async def test_active_tab(self):
        from imperal_sdk.ui.base import UINode
        from panels import panel_tasks
        ctx = make_ctx()
        cr = await fn_create_task(ctx, CreateTaskParams(title="Done"))
        await fn_complete_task(ctx, TaskIdParams(task_id=cr.data["task_id"]))
        await fn_create_task(ctx, CreateTaskParams(title="Active"))
        result = await panel_tasks(ctx, tab="active")
        assert isinstance(result, UINode)
