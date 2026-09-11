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
| ⚠️ | Rama distinta a la esperada por el manifest. |

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
```

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

### `ows switch <version> <workspace>`

Deja cada repo del manifest en la rama esperada (`git checkout`).
Misma política de seguridad que `sync`: no toca un repo sucio ni uno
con commits locales sin pushear. **No hace pull** — eso sigue siendo
`ows sync`.

Si la rama esperada ya está en local, el checkout es offline. Solo
hace fetch (con el mismo fallback de credenciales que `sync`) cuando
la rama no existe en disco.

```
$ ows switch 19 BESTWAY

✅ BESTWAY                       already-on-branch
✅ addons-l10n_mx                switched — '19.0' → '19.0-BESTWAY'
⏭️  addons-account                 skipped — 2 unpushed commit(s) on 'IMP_...'
⏭️  addons-pos                     skipped — Uncommitted changes in working tree
```

El flujo típico al cambiar de cliente:

```
ows switch 19 BESTWAY
ows sync 19 BESTWAY
```

### `ows ui [port]`

Sirve una UI web **de solo lectura** en `http://127.0.0.1:8765` (o el
puerto que indiques). Muestra el mismo `status` / `current` que el CLI.
`switch` y `sync` siguen siendo comandos de terminal — el siguiente
paso es cablearlos con confirmación.

```
$ ows ui
OWS UI → http://127.0.0.1:8765  (Ctrl+C to stop)

$ ows ui 8766
```

Requiere `nicegui` (`pip install nicegui`). No hace falta tocar Apache:
son procesos distintos en puertos distintos.

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
service.py       # collect_status / collect_current — datos, sin print
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

## Changelog

Ver [CHANGELOG.md](CHANGELOG.md).
