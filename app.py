"""Task Planner · Extension setup."""
from pathlib import Path

from imperal_sdk import Extension, ChatExtension
from imperal_sdk.types.health import HealthStatus

SYSTEM_PROMPT = (Path(__file__).parent / "system_prompt.txt").read_text()

ext = Extension("task-planner", version="1.0.0", capabilities=[])

chat = ChatExtension(
    ext=ext,
    tool_name="task_planner",
    description="Manage tasks with deadlines, priorities and reminders. Create, update, complete, delete, search and export tasks.",
    system_prompt=SYSTEM_PROMPT,
    model="claude-haiku-4-5-20251001",
)


@ext.on_install
async def on_install(ctx):
    pass


@ext.on_uninstall
async def on_uninstall(ctx):
    page = await ctx.store.query("tasks", where={"owner": ctx.user.id})
    for doc in page.data:
        await ctx.store.delete("tasks", doc.id)


@ext.health_check
async def health(ctx) -> HealthStatus:
    try:
        await ctx.store.count("tasks")
        return HealthStatus.ok({"status": "healthy"})
    except Exception as e:
        return HealthStatus.degraded(str(e))
