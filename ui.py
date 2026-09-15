from pathlib import Path

from nicegui import ui

from service import (
    collect_status,
    collect_current,
    collect_sync,
    collect_switch,
    status_kind,
)
from workspace import list_versions, list_workspace_names


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

STATUS_ICON = {
    "ok": "✅",
    "blocked": "🟡",
    "mismatch": "⚠️",
    "error": "❌",
}

ACTION_ICON = {
    "updated": "✅",
    "up-to-date": "✅",
    "switched": "✅",
    "already-on-branch": "✅",
    "skipped": "⏭️",
    "failed": "❌",
}

STATUS_COLUMNS = [
    {"name": "state", "label": "", "field": "state", "align": "left"},
    {"name": "repo", "label": "Repo", "field": "repo", "align": "left"},
    {"name": "current", "label": "Current", "field": "current", "align": "left"},
    {"name": "expected", "label": "Expected", "field": "expected", "align": "left"},
    {"name": "notes", "label": "Notes", "field": "notes", "align": "left"},
]

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


def _notes(row: dict) -> str:
    notes = []

    if row.get("error"):
        notes.append(row["error"])

    if row.get("dirty"):
        notes.append("Uncommitted changes")

    if row.get("ahead"):
        notes.append(f"{row['ahead']} unpushed commit(s)")

    return " · ".join(notes)


def _status_table_row(row: dict) -> dict:
    return {
        "state": STATUS_ICON[status_kind(row)],
        "repo": row["repo"],
        "current": row.get("current") or "—",
        "expected": row.get("expected") or "—",
        "notes": _notes(row),
    }


def _action_table_row(row: dict) -> dict:
    return {
        "state": ACTION_ICON.get(row["status"], "•"),
        "repo": row["repo"],
        "status": row["status"],
        "reason": row.get("reason") or "",
    }


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

        ui.label("Last action").classes("text-subtitle1 mt-4")
        action_table = ui.table(
            columns=ACTION_COLUMNS,
            rows=[],
            row_key="repo",
        ).classes("w-full")

        confirm_dialog = ui.dialog()
        pending_action = {"name": None}

        with confirm_dialog, ui.card().classes("w-96"):
            confirm_title = ui.label().classes("text-h6")
            confirm_body = ui.label().classes("text-body2")
            with ui.row().classes("w-full justify-end q-gutter-sm mt-4"):
                ui.button("Cancel", on_click=confirm_dialog.close).props("flat")
                ui.button("Run", on_click=lambda: run_confirmed()).props("color=primary")

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
                action_hint.set_text(
                    f"{payload['action'].capitalize()} finished for {payload['project']}."
                )
                ui.notify(f"{payload['action'].capitalize()} done", type="positive")

        def run_confirmed():
            confirm_dialog.close()
            action = pending_action["name"]
            version = version_sel.value
            workspace = workspace_sel.value

            if not version or not workspace:
                ui.notify("Pick version and workspace first", type="warning")
                return

            if action == "switch":
                payload = collect_switch(
                    git_root, version, workspace,
                    credentials_provider=credentials_provider,
                )
            else:
                payload = collect_sync(
                    git_root, version, workspace,
                    credentials_provider=credentials_provider,
                )

            show_action_results(payload)
            refresh_all()

        def confirm_action(action: str):
            version = version_sel.value
            workspace = workspace_sel.value

            if not version or not workspace:
                ui.notify("Pick version and workspace first", type="warning")
                return

            pending_action["name"] = action
            verb = "checkout branches for" if action == "switch" else "pull updates for"
            confirm_title.set_text(f"Run {action}?")
            confirm_body.set_text(
                f"This will {verb} workspace {workspace} (Odoo {version}). "
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
