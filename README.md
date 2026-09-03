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

El binario `ows` es un script Python (`#!/usr/bin/env python3`) ejecutable,
con dependencia única de `pyyaml`. Instálalo en el PATH:

```bash
pip install pyyaml
ln -s ~/git_repos/odoo-workspace/ows ~/.local/bin/ows   # o el destino que uses
```

`GIT_ROOT` se calcula solo como el padre de este repo (`~/git_repos`); no
necesita configuración.

## Comandos

### `ows status <version> <workspace>`

Compara, repo por repo, la rama actual contra la esperada en el manifest.
También muestra si el repo tiene commits locales sin pushear (no requiere red:
compara contra el último estado remoto conocido).

```
$ ows status 19 BESTWAY

✅ BESTWAY
    Branch   : 19.0

⚠️  addons-account
    Current  : IMP_b_custom_codes_balance-...-19.0
    Expected : 19.0
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
helper configurado, `sync` te pide usuario y token **una sola vez por
corrida** (no se guardan a disco) y los reutiliza en el resto de los repos.
Si ya tienes SSH configurado, no pregunta nada — el primer intento siempre
es sin forzar credenciales, y solo cae al prompt propio si git realmente lo
necesita.

## Estructura del código

```
ows              # entrypoint: parseo de argv, usage()
commands.py      # status(), current(), sync() — la lógica de cada comando
workspace.py     # lectura de manifests YAML
gitutils.py      # wrappers sobre `git` (branch, fetch, pull, ahead/behind, dirty)
credentials.py   # captura de usuario/token una sola vez para sync, GIT_ASKPASS
utils.py         # funciones de impresión (print_repo_status, print_sync_result)
```

## Limitaciones conocidas

- Varios repos del workspace tienen `remote.origin.fetch` fijo a una rama
  distinta de la que realmente usan (config heredada de un clone anterior).
  `sync` lo sortea haciendo fetch explícito de la rama esperada, pero un
  `git fetch` manual fuera de `ows` seguirá sin traer esa rama. Corregir esto
  de raíz (y detectar otros repos en la misma situación) queda pendiente para
  un futuro comando de diagnóstico (`ows doctor`, ver CHANGELOG).
- Asume un único remoto llamado `origin` en todos los repos.

## Changelog

Ver [CHANGELOG.md](CHANGELOG.md).
