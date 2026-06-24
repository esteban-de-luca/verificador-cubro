# verificador-cubro
Verificador de Ficheros de corte v1.0

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
