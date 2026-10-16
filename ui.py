import asyncio
import queue
from functools import partial
from pathlib import Path

from nicegui import run, ui

from service import (
    collect_status,
    collect_current,
    collect_sync,
    collect_switch,
    status_kind,
)
from workspace import list_versions, list_workspace_names, load_workspace


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

STATUS_ICON = {
    "ok": "✅",
    "wip": "🔧",
    "blocked": "🟡",
    "mismatch": "⚠️",
    "error": "❌",
}

ACTION_ICON = {
    "updated": "✅",
    "up-to-date": "✅",
    "switched": "✅",
    "resumed": "🔧",
    "already-on-branch": "✅",
    "skipped": "⏭️",
    "failed": "❌",
    "pending": "⏳",
    "running": "🔄",
}

STATUS_COLUMNS = [
    {"name": "state", "label": "", "field": "state", "align": "left"},
    {"name": "repo", "label": "Repo", "field": "repo", "align": "left"},
    {"name": "current", "label": "Current", "field": "current", "align": "left"},
    {"name": "expected", "label": "Expected", "field": "expected", "align": "left"},
    {"name": "notes", "label": "Notes", "field": "notes", "align": "left"},
    {"name": "changes", "label": "Working tree", "field": "changes", "align": "left"},
]

_CHANGES_CELL_SLOT = """
<q-td :props="props">
  <div
    v-if="props.value"
    class="text-body2 text-grey-9"
    style="white-space: pre-wrap; max-width: 28rem; font-family: monospace; font-size: 0.85rem;"
  >{{ props.value }}</div>
</q-td>
"""

ACTION_LABEL = {
    "switch": "Switch",
    "switch-manifest": "Switch to manifest",
    "sync": "Sync",
}

RANKING_COLUMNS = [
    {"name": "rank", "label": "", "field": "rank", "align": "left"},
    {"name": "workspace", "label": "Workspace", "field": "workspace", "align": "left"},
    {"name": "score", "label": "Match", "field": "score", "align": "left"},
]

ACTION_COLUMNS = [
    {"name": "state", "label": "", "field": "state", "align": "left"},
    {"name": "repo", "label": "Repo", "field": "repo", "align": "left"},
    {"name": "status", "label": "Status", "field": "status", "align": "left"},
    {"name": "reason", "label": "Reason", "field": "reason", "align": "left"},
]

# Copia en el cliente (mismo gesto de click) y aviso vía emit → Python.
_COPY_JS = """
() => {
    const text = String(props.value ?? '');
    if (!text || text === '—') return;
    const fallback = () => {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
    };
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).catch(fallback);
    } else {
        fallback();
    }
    emit(text);
}
"""


def _notify_copied(_event) -> None:
    ui.notify("Copied", type="positive", timeout=800)


def _attach_copy_slots(table, *columns: str) -> None:
    for column in columns:
        with table.add_slot(f"body-cell-{column}"):
            with table.cell(column):
                with ui.row().classes("items-center no-wrap q-gutter-xs"):
                    # :label=props.value (como en la doc de NiceGUI); v-text en span no renderiza aquí.
                    ui.button().props(
                        ":label=props.value flat dense no-caps ripple=false "
                        "color=transparent text-color=inherit"
                    ).style(
                        "pointer-events: none; min-height: 0; padding: 0; opacity: 1"
                    )
                    ui.button(icon="content_copy").props(
                        "flat dense round size=sm"
                    ).props('v-if="props.value && props.value !== \'—\'"').on(
                        "click",
                        js_handler=_COPY_JS,
                        handler=_notify_copied,
                    ).tooltip("Copy")


def _notes(row: dict) -> str:
    notes = []

    if row.get("error"):
        notes.append(row["error"])

    if row.get("wip"):
        notes.append("Work in progress")

    if row.get("merged_into"):
        notes.append(f"already merged into {row['merged_into']}")

    if row.get("dirty"):
        notes.append("Uncommitted changes")

    if row.get("ahead"):
        notes.append(f"{row['ahead']} unpushed commit(s)")

    return " · ".join(notes)


def _working_tree_cell(row: dict) -> str:
    if not row.get("dirty"):
        return ""

    changes = row.get("tree_changes") or []
    return "\n".join(changes)


def _status_table_row(row: dict) -> dict:
    return {
        "state": STATUS_ICON[status_kind(row)],
        "repo": row["repo"],
        "current": row.get("current") or "—",
        "expected": row.get("expected") or "—",
        "notes": _notes(row),
        "changes": _working_tree_cell(row),
    }


def _action_table_row(row: dict) -> dict:
    return {
        "state": ACTION_ICON.get(row["status"], "•"),
        "repo": row["repo"],
        "status": row["status"],
        "reason": row.get("reason") or "",
    }


def _action_progress_rows(
    repo_names: list[str],
    finished: dict[str, dict],
    current_repo: str | None,
    current_step: str | None,
) -> list[dict]:
    rows = []

    for repo in repo_names:
        if repo in finished:
            rows.append(_action_table_row(finished[repo]))
        elif repo == current_repo:
            rows.append({
                "state": ACTION_ICON["running"],
                "repo": repo,
                "status": "running",
                "reason": current_step or "…",
            })
        else:
            rows.append({
                "state": ACTION_ICON["pending"],
                "repo": repo,
                "status": "pending",
                "reason": "",
            })

    return rows


def _default_version(versions):
    if "19" in versions:
        return "19"

    return versions[-1]


def _default_workspace(git_root: Path, version: str, names):
    ranking = collect_current(git_root, version)["results"]

    if ranking:
        return ranking[0]["workspace"]

    if names:
        return names[0]

    return None


def start_ui(git_root: Path, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    """
    UI web local en ``http://<host>:<port>`` con status, ranking,
    switch y sync (misma lógica que el CLI).
    """

    @ui.page("/")
    def index():
        versions = list_versions(git_root)

        ui.label("OWS").classes("text-h4")
        ui.label("Odoo Workspace Manager").classes("text-grey mb-2")

        if not versions:
            ui.label(f"No workspace manifests found under {git_root}.")
            return

        version_value = _default_version(versions)
        names = list_workspace_names(git_root, version_value)
        workspace_value = _default_workspace(git_root, version_value, names)

        git_username = ui.input("Git username (HTTPS, optional)").classes("w-64")
        git_token = ui.input(
            "Git token (HTTPS, optional)",
            password=True,
            password_toggle_button=True,
        ).classes("w-64")

        with ui.row().classes("items-end w-full q-gutter-md flex-wrap"):
            version_sel = ui.select(
                versions,
                label="Version",
                value=version_value,
            ).classes("w-32")
            workspace_sel = ui.select(
                names,
                label="Workspace",
                value=workspace_value,
            ).classes("w-64")
            ui.button("Refresh", on_click=lambda: refresh_all())

        with ui.row().classes("q-gutter-md mt-2"):
            ui.button("Switch", on_click=lambda: confirm_action("switch")).props("color=primary")
            ui.button(
                "Switch to manifest",
                on_click=lambda: confirm_action("switch-manifest"),
            ).props("color=primary outline")
            ui.button("Sync", on_click=lambda: confirm_action("sync")).props("color=secondary")

        hint = ui.label().classes("mt-2")
        action_hint = ui.label().classes("text-grey")

        with ui.expansion("Workspace ranking", icon="leaderboard").classes("w-full mt-4"):
            ranking_table = ui.table(
                columns=RANKING_COLUMNS,
                rows=[],
                row_key="workspace",
            ).classes("w-full")

        ui.label("Repository status").classes("text-subtitle1 mt-4")
        status_table = ui.table(
            columns=STATUS_COLUMNS,
            rows=[],
            row_key="repo",
        ).classes("w-full")
        _attach_copy_slots(status_table, "repo", "current")
        status_table.add_slot("body-cell-changes", _CHANGES_CELL_SLOT)

        ui.label("Last action").classes("text-subtitle1 mt-4")
        action_table = ui.table(
            columns=ACTION_COLUMNS,
            rows=[],
            row_key="repo",
        ).classes("w-full")
        _attach_copy_slots(action_table, "repo")

        confirm_dialog = ui.dialog()
        pending_action = {"name": None}

        def credentials_provider():
            username = (git_username.value or "").strip()
            token = git_token.value or ""
            return username, token

        def refresh_ranking():
            version = version_sel.value

            if not version:
                ranking_table.rows = []
                ranking_table.update()
                return

            results = collect_current(git_root, version)["results"]
            medals = ["🥇", "🥈", "🥉"]

            ranking_table.rows = [
                {
                    "rank": medals[idx] if idx < 3 else "",
                    "workspace": row["workspace"],
                    "score": f"{row['matches']}/{row['total']} ({row['percentage']:.1f}%)",
                }
                for idx, row in enumerate(results)
            ]
            ranking_table.update()

        def refresh_status():
            version = version_sel.value
            workspace = workspace_sel.value

            if not version or not workspace:
                hint.set_text("Pick a version and a workspace.")
                status_table.rows = []
                status_table.update()
                return

            ranking = collect_current(git_root, version)["results"]
            best = ranking[0]["workspace"] if ranking else None

            if best == workspace:
                hint.set_text(f"Current workspace (best match): {best}")
            elif best:
                hint.set_text(f"Showing {workspace}. Best match on disk: {best}.")
            else:
                hint.set_text(f"Showing {workspace}.")

            payload = collect_status(git_root, version, workspace)
            status_table.rows = [_status_table_row(row) for row in payload["repos"]]
            status_table.update()

        def refresh_all():
            refresh_ranking()
            refresh_status()

        def show_action_results(payload: dict):
            action_table.rows = [
                _action_table_row(row) for row in payload["results"]
            ]
            action_table.update()

            if payload.get("needs_credentials"):
                action_hint.set_text(
                    "Some repos need HTTPS credentials — fill username/token above and retry."
                )
                ui.notify(
                    "Git credentials required for some repos",
                    type="warning",
                )
            else:
                action_name = payload["action"].capitalize()
                skipped = sum(
                    1 for row in payload["results"]
                    if row["status"] in ("skipped", "failed")
                )
                text = f"{action_name} finished for {payload['project']}"

                if skipped:
                    text += f" — {skipped} skipped/failed (see Last action)."
                else:
                    text += "."

                saved = payload.get("saved_branches") or {}

                if saved:
                    branches = ", ".join(f"{repo}: {branch}" for repo, branch in saved.items())
                    text += f" Saved work branches of {payload['left_workspace']} — {branches}."

                action_hint.set_text(text)

                if skipped:
                    ui.notify(
                        f"{action_name}: {skipped} repo(s) skipped/failed — see Last action",
                        type="warning",
                    )
                else:
                    ui.notify(f"{action_name} done", type="positive")

        async def run_confirmed():
            confirm_dialog.close()
            action_name = pending_action["name"]
            action = ACTION_LABEL[action_name]
            version = version_sel.value
            workspace = workspace_sel.value

            if not version or not workspace:
                ui.notify("Pick version and workspace first", type="warning")
                return

            manifest = load_workspace(git_root, version, workspace)
            repo_names = list(manifest.get("repositories", {}).keys())
            total = len(repo_names)

            progress_queue: queue.SimpleQueue = queue.SimpleQueue()
            progress_state = {
                "finished": {},
                "current_repo": None,
                "current_step": None,
            }

            def apply_progress_event(event: dict) -> None:
                event_type = event["type"]

                if event_type == "repo_start":
                    progress_state["current_repo"] = event["repo"]
                    progress_state["current_step"] = event.get("step", "")
                elif event_type == "repo_step":
                    progress_state["current_step"] = event["step"]
                elif event_type == "repo_done":
                    progress_state["finished"][event["repo"]] = event["result"]
                    progress_state["current_repo"] = None
                    progress_state["current_step"] = None

            def refresh_action_progress() -> None:
                done = len(progress_state["finished"])
                action_table.rows = _action_progress_rows(
                    repo_names,
                    progress_state["finished"],
                    progress_state["current_repo"],
                    progress_state["current_step"],
                )
                action_table.update()

                current = progress_state["current_repo"]
                step = progress_state["current_step"]

                if current:
                    action_hint.set_text(
                        f"{action} {done}/{total} done — "
                        f"{current}: {step or '…'}"
                    )
                else:
                    action_hint.set_text(
                        f"{action}… {done}/{total} done"
                    )

            def progress_callback(event: dict) -> None:
                progress_queue.put(event)

            refresh_action_progress()
            await asyncio.sleep(0)

            if action_name == "switch":
                collector = collect_switch
            elif action_name == "switch-manifest":
                collector = partial(collect_switch, manifest=True)
            else:
                collector = collect_sync

            worker = asyncio.create_task(
                run.io_bound(
                    collector,
                    git_root,
                    version,
                    workspace,
                    credentials_provider,
                    progress_callback,
                )
            )

            while not worker.done():
                updated = False
                while not progress_queue.empty():
                    apply_progress_event(progress_queue.get())
                    updated = True
                if updated:
                    refresh_action_progress()
                await asyncio.sleep(0.05)

            while not progress_queue.empty():
                apply_progress_event(progress_queue.get())

            payload = await worker
            refresh_action_progress()

            if payload is None:
                ui.notify(f"{action} cancelled", type="warning")
                return

            show_action_results(payload)
            refresh_all()

        with confirm_dialog, ui.card().classes("w-96"):
            confirm_title = ui.label().classes("text-h6")
            confirm_body = ui.label().classes("text-body2")
            with ui.row().classes("w-full justify-end q-gutter-sm mt-4"):
                ui.button("Cancel", on_click=confirm_dialog.close).props("flat")
                ui.button("Run", on_click=run_confirmed).props("color=primary")

        def confirm_action(action: str):
            version = version_sel.value
            workspace = workspace_sel.value

            if not version or not workspace:
                ui.notify("Pick version and workspace first", type="warning")
                return

            pending_action["name"] = action
            verbs = {
                "switch": "checkout the remembered work branches (or the manifest branches) for",
                "switch-manifest": "checkout the manifest branches, forgetting remembered work branches, for",
                "sync": "pull updates for",
            }
            confirm_title.set_text(f"Run {ACTION_LABEL[action].lower()}?")
            confirm_body.set_text(
                f"This will {verbs[action]} workspace {workspace} (Odoo {version}). "
                "Dirty or unpushed repos are skipped, same as the CLI."
            )
            confirm_dialog.open()

        def on_version_change(event):
            version = event.value
            names = list_workspace_names(git_root, version)
            workspace = _default_workspace(git_root, version, names)
            workspace_sel.set_options(names, value=workspace)
            refresh_all()

        version_sel.on_value_change(on_version_change)
        workspace_sel.on_value_change(lambda _: refresh_all())
        refresh_all()

    print()
    print(f"OWS UI → http://{host}:{port}  (Ctrl+C to stop)")
    print()

    ui.run(
        host=host,
        port=port,
        reload=False,
        show=False,
        title="OWS",
    )
