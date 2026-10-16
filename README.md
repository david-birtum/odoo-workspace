# odoo-workspace (ows)

CLI para moverse rápido entre las ramas de los distintos proyectos Odoo que
vive en `~/git_repos`. No es un módulo Odoo — es una herramienta de apoyo para
el día a día del equipo, que compara y sincroniza el estado de git de varios
repos contra un manifest declarativo por cliente.

## Layout que asume

```
git_repos/
├── 13/ … 19/                # una carpeta por versión de Odoo
│   ├── odoo/
│   │   ├── <repo-a>/        # cada uno un repo git independiente
│   │   └── <repo-b>/
│   └── workspace/
│       ├── CLIENTE_A.yaml   # manifest: qué rama espera cada repo
│       └── CLIENTE_B.yaml
└── odoo-workspace/          # este repo (el CLI)
```

Cada manifest declara, por repo, la rama que debería estar checked out:

```yaml
project: BESTWAY
version: 19
repositories:
  BESTWAY:
    branch: "19.0"
  addons-pos:
    branch: "19.0-BESTWAY"
```

## Instalación

El binario `ows` es un script Python (`#!/usr/bin/env python3`) ejecutable.
El CLI solo necesita `pyyaml`; la UI web añade `nicegui`. Instálalo en el PATH:

```bash
# CLI (pyyaml en el Python del sistema, o en un venv)
pip install pyyaml

# UI: venv local (Debian no deja usar pip sobre el Python del sistema)
cd ~/git_repos/odoo-workspace
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

ln -s ~/git_repos/odoo-workspace/ows ~/.local/bin/ows   # o el destino que uses
```

`ows ui` reusa `.venv/bin/python` si existe, así no hace falta activar el venv.

`GIT_ROOT` se calcula solo como el padre de este repo (`~/git_repos`); no
necesita configuración.

Apache (u otro servidor) en el puerto 80 no estorba: la UI escucha solo
en `127.0.0.1:8765` (u otro puerto que pases).

## Comandos

### `ows status <version> <workspace>`

Compara, repo por repo, la rama actual contra la esperada en el manifest.
También muestra, sin tocar el repo ni requerir red, la misma información
que usa `ows sync` para decidir si puede actualizarlo solo: si tiene
cambios sin commitear y si tiene commits locales sin pushear (esto último
compara contra el último estado remoto conocido, no hace fetch).

El ícono indica de un vistazo si el repo calificaría para `ows sync`:

| Ícono | Significado |
|-------|-------------|
| ✅ | Rama correcta, limpio, nada por pushear — `sync` no tendría nada que hacer o lo actualizaría sin drama. |
| 🟡 | Rama correcta, pero algo bloquearía el `sync` (cambios sin commitear y/o commits sin pushear). |
| 🔧 | Trabajo en curso: rama de feature/fix recordada para el workspace (o fuera de todos los manifests). Si ya está mergeada en la esperada, se indica `already in <rama>`. |
| ⚠️ | Rama distinta a la esperada por el manifest (y no es trabajo en curso). |

```
$ ows status 19 BESTWAY

✅ BESTWAY
    Branch   : 19.0

⚠️  addons-account
    Current  : IMP_b_custom_codes_balance-...-19.0
    Expected : 19.0

🟡 addons-pos
    Branch   : 19.0-BESTWAY
    Tree     : Uncommitted changes
             modified   addons/sale/models/order.py
             untracked  tmp.txt
```

Si hay cambios sin commitear, debajo de `Tree` se listan archivos con
etiquetas al estilo `git status --porcelain` (`modified`, `added`,
`deleted`, `untracked`, `renamed`, …).

### `ows current <version>`

Recorre todos los manifests de una versión y arma un ranking de qué
workspace coincide más con las ramas que tienes actualmente en disco —
útil para saber "¿en qué cliente estoy parado ahora mismo?" sin tener que
acordarte tú mismo.

```
$ ows current 19

🥇 PRISSA                1/1  (100.0%)
🥈 BESTWAY               6/7  ( 85.7%)
...

Current workspace: PRISSA
```

### `ows switch <version> <workspace> [--manifest]`

Deja cada repo del workspace en su rama de trabajo recordada o, si no hay,
en la rama esperada por el manifest (`git checkout`).

**Memoria de ramas de trabajo.** Antes de mover nada, `switch` guarda las
ramas de trabajo en curso del workspace que dejas (el último al que hiciste
switch o, la primera vez, el mejor del ranking): cualquier repo que esté en
una rama distinta a la del manifest y que no sea la rama de otro manifest
de la versión. Al volver a ese workspace, esas ramas se retoman (🔧
`resumed`) en vez de la del YAML. Si una rama recordada ya no existe en
local, usa la del manifest y la olvida. El estado vive en
`~/.local/state/ows/state.json` (o `$XDG_STATE_HOME/ows/`, o
`OWS_STATE_FILE`); no se versiona.

`--manifest` ignora lo recordado, deja todo en las ramas del YAML y
olvida las ramas de trabajo de ese workspace (útil al terminar una
feature). Como pista local, sin red, se avisa `already merged into <rama>`
cuando la rama de trabajo ya está contenida en `origin/<rama esperada>`.

Misma política de seguridad que `sync`: no toca un repo sucio ni uno
con commits locales sin pushear — **tampoco con `--manifest`**. Esos
repos se quedan en su rama actual y se reportan como `skipped` con el
motivo; para llevarlos a la rama del YAML, primero haz commit/stash o
push y repite el switch. Al final se imprime cuántos repos se saltaron.
**No hace pull** — eso sigue siendo `ows sync`.

Si la rama esperada ya está en local, el checkout es offline. Solo
hace fetch (con el mismo fallback de credenciales que `sync`) cuando
la rama no existe en disco.

```
$ ows switch 19 BESTWAY

✅ BESTWAY                       already-on-branch
✅ addons-l10n_mx                switched — '19.0' → '19.0-BESTWAY'
⏭️  addons-account                 skipped — 2 unpushed commit(s) on 'IMP_...'
⏭️  addons-pos                     skipped — Uncommitted changes in working tree

⚠️  2 repo(s) skipped/failed — see the reasons above.

$ ows switch 19 PRISSA        # más tarde, de vuelta a BESTWAY:
$ ows switch 19 BESTWAY
Saved work branches of PRISSA: ...
🔧 addons-account                 resumed — '19.0' → 'IMP_...' (work in progress)
```

El flujo típico al cambiar de cliente:

```
ows switch 19 BESTWAY
ows sync 19 BESTWAY
```

### `ows ui [port]`

UI web local en `http://127.0.0.1:8765` (o el puerto que indiques).
Incluye los cuatro comandos probados del CLI:

- **Ranking** (`current`) — qué workspace coincide más con tus ramas
- **Status** — tabla por repo con los mismos íconos ✅ 🔧 🟡 ⚠️; columna
  **Working tree** con el detalle de archivos cuando hay cambios locales;
  botones de copiar en **Repo** y **Current**
- **Switch** / **Switch to manifest** / **Sync** — con confirmación
  (Switch retoma ramas de trabajo; Switch to manifest equivale a
  `--manifest`); misma política de skip que
  en terminal (no toca repos sucios ni con unpushed, ni siquiera con
  Switch to manifest). Mientras corre, la
  tabla **Last action** muestra progreso en vivo: repos pendientes (⏳),
  el repo en curso (🔄) con el paso actual (`Fetching origin/…`, `Pulling…`,
  `Checking out…`, etc.) y los ya terminados con su resultado. Si algún
  repo se saltó o falló, el aviso final sale como advertencia con el
  conteo (`N skipped/failed (see Last action)`) en vez de "done"

Si usas HTTPS sin SSH/credential helper, rellena username/token en la
UI antes de Switch/Sync (no se guardan en disco).

```
$ ows ui
OWS UI → http://127.0.0.1:8765  (Ctrl+C to stop)

$ ows ui 8766
```

Requiere `nicegui` (`pip install nicegui`). No hace falta tocar Apache:
son procesos distintos en puertos distintos. Para parar: `Ctrl+C` en la
terminal donde corre `./ows ui`.

### `ows sync <version> <workspace>`

Actualiza automáticamente (`git pull --ff-only`) los repos que:

1. Ya están en la rama esperada por el manifest,
2. no tienen cambios sin commitear, y
3. no tienen commits locales sin pushear.

Todo lo demás se reporta como `skipped` con el motivo — nunca se toca un
repo sucio o adelantado. El fetch/pull de cada repo se hace apuntando
explícitamente a la rama esperada (`git fetch origin +<rama>:...`), así que
funciona incluso si el repo no tiene upstream configurado o su
`remote.origin.fetch` está restringido a otra rama.

```
$ ows sync 19 BESTWAY

✅ addons-pos                     up-to-date
✅ addons-sale                    updated (2 commit(s) pulled)
⏭️  addons-account                 skipped — On branch 'IMP_...', expected '19.0'
```

**Credenciales:** si tus repos son HTTPS y no tienes SSH key / credential
helper configurado, `sync` y `switch` (solo si hay que fetchear una rama
que no está en local) te piden usuario y token **una sola vez por
corrida** (no se guardan a disco) y los reutilizan en el resto de los repos.
Si ya tienes SSH configurado, no pregunta nada — el primer intento siempre
es sin forzar credenciales, y solo cae al prompt propio si git realmente lo
necesita.

## Estructura del código

```
ows              # entrypoint: parseo de argv, usage()
service.py       # collect_* (status, current, sync, switch) — datos, sin print
state.py         # estado local: workspace activo y ramas de trabajo recordadas
commands.py      # status(), current(), switch(), sync() — CLI sobre service
ui.py            # NiceGUI: ows ui en 127.0.0.1:8765
workspace.py     # lectura de manifests YAML
gitutils.py      # wrappers sobre `git` (branch, checkout, fetch, pull, ahead/behind, dirty)
credentials.py   # captura de usuario/token una sola vez para sync/switch, GIT_ASKPASS
utils.py         # funciones de impresión (print_repo_status, print_action_result)
```

## Limitaciones conocidas

- Varios repos del workspace tienen `remote.origin.fetch` fijo a una rama
  distinta de la que realmente usan (config heredada de un clone anterior).
  `sync` y `switch` lo sortean haciendo fetch explícito de la rama esperada, pero un
  `git fetch` manual fuera de `ows` seguirá sin traer esa rama. Corregir esto
  de raíz (y detectar otros repos en la misma situación) queda pendiente para
  un futuro comando de diagnóstico (`ows doctor`, ver CHANGELOG).
- Asume un único remoto llamado `origin` en todos los repos.
- El aviso "already merged" usa el último `origin/<rama>` conocido (no hace
  fetch) y no detecta squash/rebase merges.
- Un `git checkout` manual fuera de `ows` no actualiza el workspace activo;
  la memoria se toma de lo que hay en disco al hacer el siguiente `switch`.

## Changelog

Ver [CHANGELOG.md](CHANGELOG.md).
