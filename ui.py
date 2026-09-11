from pathlib import Path

from nicegui import ui

from service import collect_status, collect_current, status_kind
from workspace import list_versions, list_workspace_names


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

STATUS_ICON = {
    "ok": "✅",
    "blocked": "🟡",
    "mismatch": "⚠️",
    "error": "❌",
}

TABLE_COLUMNS = [
    {"name": "state", "label": "", "field": "state", "align": "left"},
    {"name": "repo", "label": "Repo", "field": "repo", "align": "left"},
    {"name": "current", "label": "Current", "field": "current", "align": "left"},
    {"name": "expected", "label": "Expected", "field": "expected", "align": "left"},
    {"name": "notes", "label": "Notes", "field": "notes", "align": "left"},
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


def _table_row(row: dict) -> dict:
    return {
        "state": STATUS_ICON[status_kind(row)],
        "repo": row["repo"],
        "current": row.get("current") or "—",
        "expected": row.get("expected") or "—",
        "notes": _notes(row),
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
    Sirve la UI de solo lectura en ``http://<host>:<port>``.
    ``switch`` / ``sync`` siguen siendo comandos de CLI.
    """

    @ui.page("/")
    def index():
        versions = list_versions(git_root)

        ui.label("OWS").classes("text-h4")
        ui.label(
            "Estado local de los workspaces. Switch y sync siguen en el CLI."
        ).classes("text-grey mb-4")

        if not versions:
            ui.label(f"No workspace manifests found under {git_root}.")
            return

        version_value = _default_version(versions)
        names = list_workspace_names(git_root, version_value)
        workspace_value = _default_workspace(git_root, version_value, names)

        with ui.row().classes("items-end w-full q-gutter-md"):
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
            ui.button("Refresh", on_click=lambda: refresh())

        hint = ui.label().classes("mt-2")
        table = ui.table(
            columns=TABLE_COLUMNS,
            rows=[],
            row_key="repo",
        ).classes("w-full mt-4")

        def refresh():
            version = version_sel.value
            workspace = workspace_sel.value

            if not version or not workspace:
                hint.set_text("Pick a version and a workspace.")
                table.rows = []
                table.update()
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
            table.rows = [_table_row(row) for row in payload["repos"]]
            table.update()

        def on_version_change(event):
            version = event.value
            names = list_workspace_names(git_root, version)
            workspace = _default_workspace(git_root, version, names)
            workspace_sel.set_options(names, value=workspace)
            refresh()

        version_sel.on_value_change(on_version_change)
        workspace_sel.on_value_change(lambda _: refresh())
        refresh()

    print()
    print(f"OWS UI → http://{host}:{port}  (Ctrl+C to stop)")
    print()

    ui.run(
        host=host,
        port=port,
        reload=False,
        show=True,
        title="OWS",
    )
