# verificador-cubro
Verificador de Ficheros de corte v1.0

## El motor de reglas como paquete (`verificador_cubro`)

El dashboard (`cubro-dashboard`) verifica el paquete que genera su motor de fichero de corte
ANTES de descargarlo, con estos mismos checks y reglas. Para no copiar el código, instala este
repo como paquete, fijado a un commit:

```
verificador-cubro @ https://github.com/esteban-de-luca/verificador-cubro/archive/<commit>.tar.gz
```

- `pyproject.toml` empaqueta `core/`, `checks/`, `engine.py` y las reglas (`reglas.yaml`,
  `reglas_cnc.yaml`), con solo las dependencias de verificar (ni Streamlit, ni Drive, ni Notion).
  Streamlit Cloud sigue instalando desde `requirements.txt`, que tiene prioridad.
- `verificador_cubro.verificar_archivos(archivos, id_proyecto)` recibe los ficheros en memoria
  (`{nombre: bytes}`) y devuelve el informe como dict JSON con el mismo `estado` que la app
  (`OK` / `ADVERTENCIAS` / `BLOQUEADO`). No escribe en el log ni en Notion.
- **Al cambiar una regla aquí, el dashboard no la ve hasta que actualiza el commit** en su
  `requirements.txt`: así cada versión del dashboard sabe con qué reglas verifica.

## Registro de verificaciones en Google Sheets

Además del registro en Notion, cada verificación se añade como **una fila** a un
Google Sheet de log dedicado (`Log Verificaciones Ficheros de Corte`) que lee
otro proyecto (un dashboard). El guardado lo hace `sheets_writer.py` al terminar
cada verificación, tanto en la vista individual (`app.py`) como en la
verificación en lote (`pages/2_Cola_Global.py`).

### Autenticación

Reutiliza la **misma Service Account** que el repo ya usa para Drive (no se
crean credenciales nuevas). El único requisito añadido es el scope
`https://www.googleapis.com/auth/spreadsheets`, ya incluido en
`config.DRIVE_SCOPES`. La Service Account debe tener **acceso de edición** al
Sheet — lo tiene automáticamente si el Sheet vive en la misma unidad compartida
que las carpetas de Drive.

### Configuración (variables de entorno / Streamlit Secrets)

| Variable             | Por defecto                                  | Descripción                                              |
|----------------------|----------------------------------------------|----------------------------------------------------------|
| `LOG_VERIF_SHEET_ID` | ID del Sheet de log (ver `config.py`)        | ID del Google Sheet donde se registran las verificaciones |
| `LOG_VERIF_TAB`      | `Log`                                        | Nombre de la pestaña destino dentro del Sheet            |

Se pueden definir como variables de entorno o en `.streamlit/secrets.toml` bajo
la sección `[sheets]` (ver `.streamlit/secrets.toml.example`).

> **Nota sobre la pestaña:** si la pestaña configurada en `LOG_VERIF_TAB` no
> existe, el writer cae automáticamente a la **primera hoja** del libro. La
> pestaña actual del Sheet de producción se llama `_Log_Verificacion_Ficheros`;
> ajusta `LOG_VERIF_TAB` (o renombra la pestaña a `Log`) si quieres fijarla
> explícitamente.

### Formato de la fila (contrato con el dashboard)

14 columnas, en este orden, escritas con `valueInputOption="RAW"`:

```
timestamp · id_proyecto · estado · responsable · semana_produccion ·
fecha_analisis · cliente · n_fail · n_warn · n_pass · errores_criticos ·
advertencias · aspectos_relevantes · link_informe
```

- `timestamp`: ISO 8601 en UTC, ordenable como texto (`...isoformat(timespec="seconds")`).
- `estado`: minúsculas — `bloqueado` (n_fail>0) / `advertencias` (n_warn>0) / `aprobado`.
- `n_fail` / `n_warn` / `n_pass`: enteros.
- `errores_criticos` / `advertencias`: lista de checks unida con `\n`.

### Prueba manual rápida

Con las credenciales de la Service Account configuradas (env vars o
`.streamlit/secrets.toml`), añade una fila de prueba al Sheet:

```bash
python -m sheets_writer            # id de proyecto "EU-SMOKE"
python -m sheets_writer EU-12345   # id de proyecto a medida
```
