"""Task Planner · Skeleton + schedule."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app import ext

log = logging.getLogger("task-planner")
TASKS = "tasks"


@ext.tool("skeleton_refresh_tasks", scopes=[], description="Background refresh: task statistics.")
async def skeleton_refresh_tasks(ctx, **kwargs) -> dict:
    """Refresh task statistics for skeleton cache."""
    try:
        uid = ctx.user.id if hasattr(ctx, "user") and ctx.user else ""
        page = await ctx.store.query(TASKS, where={"owner": uid})
        tasks = [doc.data for doc in page.data]
        now = datetime.now(timezone.utc)

        def overdue(t):
            d = t.get("deadline", "")
            if not d:
                return False
            try:
                return datetime.fromisoformat(d) < now
            except Exception:
                return False

        active = [t for t in tasks if t.get("status") in ("new", "in_progress")]
        stats = {
            "total": len(tasks),
            "active": len(active),
            "completed": sum(1 for t in tasks if t.get("status") == "completed"),
            "overdue": sum(1 for t in active if overdue(t)),
        }
        await ctx.skeleton.update("task_stats", stats)
        return {"response": stats}
    except Exception as e:
        log.error("Skeleton refresh failed: %s", e)
        return {"response": {"total": 0, "active": 0, "completed": 0, "overdue": 0}}


@ext.tool("skeleton_alert_tasks", scopes=[], description="Alert on task changes.")
async def skeleton_alert_tasks(ctx, old: dict = None, new: dict = None, **kwargs) -> dict:
    """Notify if overdue count increased."""
    if not old or not new:
        return {"response": "No changes."}
    old_overdue = old.get("overdue", 0)
    new_overdue = new.get("overdue", 0)
    if isinstance(new_overdue, int) and new_overdue > old_overdue:
        diff = new_overdue - old_overdue
        await ctx.notify(f"{diff} task(s) are now overdue.")
    return {"response": "Checked."}


@ext.schedule("deadline_check", cron="0 * * * *")
async def deadline_check(ctx) -> None:
    """Hourly: send reminders for tasks due within 24 hours."""
    try:
        uid = ctx.user.id if hasattr(ctx, "user") and ctx.user else ""
        if not uid:
            return
        page = await ctx.store.query(TASKS, where={"owner": uid})
        now = datetime.now(timezone.utc)
        soon = now + timedelta(hours=24)
        for doc in page.data:
            t = doc.data
            deadline = t.get("deadline", "")
            if (not deadline
                    or t.get("status") in ("completed", "cancelled")
                    or not t.get("reminder_enabled")
                    or t.get("reminder_sent")):
                continue
            try:
                dt = datetime.fromisoformat(deadline)
            except Exception:
                continue
            if now < dt <= soon:
                await ctx.notify(f"Task '{t.get('title')}' is due in less than 24 hours.")
                await ctx.store.update(TASKS, doc.id, {"reminder_sent": True})
    except Exception as e:
        log.error("Deadline check failed: %s", e)
