# linkedin-mcp

Postula a empleos de LinkedIn con **Solicitud sencilla** (Easy Apply) desde el **Safari** de Allan, con la sesión que él inició. Habla con Safari por AppleScript (`do JavaScript`), igual que `safari-mcp`, del que copia una capa mínima (`safari_bridge.py`) para no depender del OneDrive de FAPCO.

El skill que lo usa es `~/.claude/skills/postular-linkedin`.

> **Límite honesto.** Las condiciones de uso de LinkedIn prohíben los bots y la automatización; ninguna herramienta garantiza que la cuenta no se restrinja. Este MCP baja el riesgo comportándose como una persona cuidadosa, no ocultando la automatización:
> - Usa el Safari real con la sesión de Allan.
> - Pocas acciones al día y una cosa a la vez.
> - Cada envío espera el "sí" de Allan.
> - Se detiene ante cualquier verificación.
>
> No incluye sigilo, cambio de user-agent, retrasos aleatorios para parecer humano, resolución de CAPTCHA, proxies ni scraping masivo.

## Qué hace y qué no

- **Sí:** lee la búsqueda de empleos que Allan abrió, la puntúa contra su perfil, abre vacantes una por una, recorre y llena el formulario de Solicitud sencilla, sube un CV aprobado y envía solo con `confirm=True`.
- **No (no existen tools para esto):** iniciar sesión, enviar mensajes, mandar invitaciones, editar el perfil, ver perfiles ajenos, buscar o recorrer páginas en masa, ejecutar JavaScript arbitrario.
- Solo actúa en pestañas `linkedin.com` y solo navega a URLs que construye él mismo (`https://www.linkedin.com/jobs/view/<id>/`).

## Flujo corto de una vacante

| # | Llamada | Qué pasa |
|---|---|---|
| 1 | `linkedin_triage` | Puntúa la lista sin abrir vacantes (0 vistas). Allan elige. |
| 2 | `linkedin_apply_prepare(job_id)` | Abre el formulario, avanza solo por los pasos que no piden nada y devuelve el cuestionario con las propuestas del banco. No llena nada. 1 vista. |
| 3 | (chat) | Se muestra una tabla y se pregunta lo que falta: las opciones en AskUserQuestion, el texto libre (salario, fechas) en el chat. |
| 4 | `linkedin_apply_fill_all(job_id, answers)` | Llena paso a paso, verifica cada valor y se detiene en la revisión. |
| 5 | (chat) | Allan ve el resumen y dice "sí" para **esa** vacante. |
| 6 | `linkedin_apply_submit(job_id, confirm=True)` | Envía y registra en los tres archivos. |

## Tools

| Tool | Qué hace |
|---|---|
| `linkedin_status()` | Safari, pestañas de LinkedIn, sesión, JS, contadores del día y pausa. Si la página muestra una verificación, activa la pausa. |
| `linkedin_list_jobs(tab_id?, page?)` | Tarjetas de la búsqueda: `job_id`, puesto, empresa, ubicación, `posted`, `insight`, `applied`, `saved`, `viewed`, `easy_apply`, `verified`… `page` (número o `"next"`) cambia de página. |
| `linkedin_triage(tab_id?, page?)` | Lee la lista y puntúa cada tarjeta contra `perfil.md` con las reglas de `references/triage.json`: `encaje` (alto/medio/bajo), `motivos`, `banderas` de experiencia sin evidencia (banca, telco/NOC, programador principal, eléctrico, cloud, obra civil, certificaciones sin verificar), `modalidad`, `estado` y `tipo`. No abre vacantes. El encaje es provisional si sale solo del título; el tipo es «según tarjeta» hasta abrir la vacante. |
| `linkedin_get_job(job_id, refresh=False)` | Lee la vacante de la **caché** (24 h, `from_cache: true`, sin navegar ni gastar vista) o, con `refresh=True` o si no hay caché, la abre en la **pestaña de trabajo** del MCP. Devuelve descripción, `apply_type` (`easy_apply`/`external`/`ats_continue`/`applied`/`closed`), `external_url`, `ats`/`apply_url`, `external_kind` (`google_forms`, `microsoft_forms`, `ats:<nombre>`, `job_board`, `company_site`), `account_hint` y `clean_url` sin `utm_*`. Abrir la página cuenta como vista. |
| `linkedin_apply_prepare(job_id, resume?, allow_logged=False)` | Abre el formulario y reúne las preguntas en una llamada, sin llenar nada. Deja el formulario abierto. Ver «prepare y fill_all». |
| `linkedin_apply_fill_all(job_id, answers, resume?, continue_draft=False, pass_empty_step=False)` | Llena lo aprobado paso a paso hasta la revisión. Nunca envía. Ver «prepare y fill_all». |
| `linkedin_apply_start(job_id)` | Camino paso a paso: abre el formulario (solo `easy_apply`) y devuelve el primer paso. No actúa si ya hay una solicitud abierta. |
| `linkedin_apply_read()` | Paso actual: `fields[]` (`label`, `type`, `required`, `value`, `options`, `max_length`, `error`, `resumes[]`), `step`/`steps`, `buttons`, `button_kinds`, `is_review`, `follow_company`, `review_text`. |
| `linkedin_apply_fill(answers)` | Camino paso a paso: llena por etiqueta (exacta, prefijo o fragmento único, sin tildes ni mayúsculas) y verifica (`all_ok`). No sirve sobre una solicitud abierta con `prepare`. |
| `linkedin_apply_select_resume(name?, index?)` | Elige un CV ya guardado en LinkedIn. |
| `linkedin_apply_upload_resume(file_path)` | Sube un PDF/DOC/DOCX < 2 MB sin diálogo de macOS, solo con un archivo que Allan aprobó. Devuelve el SHA-256 y lo anota en `resumes.json`. Da por hecha la subida solo si aparece una entrada **nueva** con ese nombre. |
| `linkedin_apply_next()` | Camino paso a paso: Siguiente/Revisar una vez. Nunca envía ni pulsa «Continuar». Si el formulario desaparece, lo registra como posible envío y pausa. |
| `linkedin_apply_submit(job_id, confirm, follow_company=False)` | Envía y registra; ver los candados abajo. |
| `linkedin_apply_close(save_draft=True, not_sent=False)` | Cierra sin enviar («Guardar» o «Descartar»). Si hay un clic en Enviar sin comprobar, solo cierra con `not_sent=True`, después de que Allan lo verificó en Safari. Cierra también un formulario que nada rastrea. |
| `linkedin_inspect(tab_id?)` | Solo lectura de una pestaña `/jobs/` (URL, vacante, formulario abierto): no navega, no hace clic y no cuenta vistas. Sirve para sondear el «Continuar» de los ATS. |
| `linkedin_record_manual(job_id, via="ats_continue", notes="")` | Registra una postulación que Allan envió a mano, si LinkedIn la muestra como enviada. Ver «Registro». |
| `linkedin_answers_save(entries, confirm=False)` | Guarda en el banco, como `aprobado <hoy>`, respuestas que Allan aprobó como reutilizables. Sin `confirm=True` solo devuelve el diff. Rechaza lo que cambie o tape una entrada `verificado` o `preguntar`. |
| `linkedin_applications(since?)` | Registro local de envíos. |
| `linkedin_resume_after_checkpoint(confirm)` | Quita la pausa si ninguna pestaña sigue mostrando la verificación. |

### `prepare` y `fill_all`

- **`prepare`**
  - Abre el formulario y avanza con Siguiente solo mientras el paso esté completo y no pida nada: todo `prefilled_ok` o un opcional vacío, y el CV elegido ya seleccionado. Nunca llena ni pulsa Descartar.
  - Devuelve el `questionnaire` (una fila por campo, con su `key`, la propuesta, el estado del banco, la fuente y `ask_via`: `choice`, `choice_multi` o `chat`), `answers_draft` y `to_ask`.
  - Si el formulario abre en un paso posterior o con «Atrás» en la primera página, es un **borrador guardado**: se detiene (`draft_detected`).
  - Se niega si hay otra solicitud abierta, si hay un formulario ya abierto en la pestaña, si la vacante figura en el registro local (`allow_logged=True` solo después de que Allan compruebe que no se envió), si no queda cupo de envíos hoy o si está dentro de los 180 s posteriores a un envío (`too_soon`, con `retry_after_s`): en esos casos no abre nada.
- **`fill_all`**
  - Cada respuesta va por su `key` (`<job_id>:<paso>|<etiqueta>|<n>`), así una respuesta nunca cae en otra vacante ni en otro paso. Las opciones deben calzar exacto.
  - En cada paso lee el formulario ya dibujado, llena, vuelve a leer y a planear, y solo entonces pulsa Siguiente. El JavaScript del clic comprueba que los campos sean exactamente los planeados.
  - En un paso que `prepare` no vio solo llena el contacto verificado; lo demás se pregunta (`needs_answers`, `new_step`).
  - Se detiene ante: una pregunta sin respuesta, un valor prellenado que nadie revisó, un typeahead o una etiqueta repetida (los llena Allan en Safari), un error o `mismatch`, errores de LinkedIn (vuelven como preguntas), un clic que no cambia nada, una verificación o la revisión (`at_review`).
  - En la revisión comprueba el CV, que ningún paso se haya pasado a mano y que cada respuesta sea la que quedó en el formulario.
  - Un borrador solo se continúa con `continue_draft=True`; un paso sin campos, con `pass_empty_step=True`. Ambos los decide Allan.
- **Clics que pueden enviar.** Siguiente y Enviar quedan marcados como pendientes hasta ver su resultado. Si después aparece la confirmación de LinkedIn o el formulario desaparece, queda registrado (confirmado o no) y el MCP se pausa. Un Enviar sin comprobar no se repite.

**Candados de `linkedin_apply_submit`:**
- `confirm=True`, que se pasa solo tras el "sí" de Allan para esa vacante.
- El mismo `job_id` que la solicitud abierta, que la pestaña y que el diálogo (la empresa debe coincidir).
- Una solicitud preparada con `prepare` debe haber llegado a la revisión con `fill_all`, y la revisión no puede haber cambiado desde entonces (firma y hash del texto).
- Estar en la pantalla de revisión, sin errores y sin campos obligatorios vacíos.
- El CV de la revisión es el elegido (y, en un borrador, la copia más reciente conocida).
- Cupo diario y espaciado mínimo.
- Desmarca «Seguir a <empresa>» salvo que se pida lo contrario, y comprueba que ese ajuste no cambió nada más.
- Si LinkedIn responde al clic con errores y el formulario sigue abierto, no se envió: devuelve `form_has_errors` y no registra nada.
- Si no ve la confirmación, igual registra el envío (para no duplicarlo) con `confirmed: false`.

## Ritmo, pausa y registro (`guard.py`)

| Variable | Por defecto | Rango permitido |
|---|---|---|
| `LINKEDIN_MCP_MAX_APPLY_PER_DAY` | 10 | 1–15 |
| `LINKEDIN_MCP_MIN_SECONDS_BETWEEN_SUBMITS` | 180 | 60–3600 |
| `LINKEDIN_MCP_MAX_JOB_VIEWS_PER_DAY` | 40 | 1–60 |
| `LINKEDIN_MCP_MIN_SECONDS_BETWEEN_NAVIGATIONS` | 8 | 3–120 |
| `LINKEDIN_MCP_MIN_SECONDS_BETWEEN_DIALOG_ACTIONS` | 3 | 2–30 |
| `LINKEDIN_MCP_STATE_DIR` | `~/.cache/linkedin-mcp` | — |

Los valores fuera de rango se recortan. **Allan fijó 10 envíos, 180 s, 40 vistas y 8 s, y no se suben**: los rangos son solo el piso y el techo duros del código, no una invitación a cambiarlos (el registro del MCP no define ninguna variable). La espera entre clics del formulario es fija, no aleatoria. Pulsar Siguiente puede terminar enviando (cbc, 06/10/2026), así que `prepare`/`fill_all` tampoco recorren un formulario si hoy ya no queda cupo de envíos, ni pulsan Siguiente dentro de los 180 s posteriores a un envío.

**Pausa por verificación.** En cada operación, `page_state` revisa:
- la URL: `/checkpoint/`, `/authwall`, `/login`, `/uas/`;
- los iframes de CAPTCHA;
- los encabezados, alertas y diálogos (excepto el propio formulario): "verificación de seguridad", "security check", "cuenta restringida", "límite de solicitudes", "application limit"…

Si encuentra algo, guarda una pausa persistente y todas las tools de acción devuelven `paused_checkpoint`.

**Estado.** En `state.json` (contadores por día local, última navegación, clic y envío, pausa, pestaña de trabajo, solicitud abierta y clic pendiente), `applications.jsonl`, `resumes.json` y `jobs/<job_id>.json` (caché). Un `fcntl.flock` impide dos operaciones a la vez, también entre el MCP y `cli.py`; dentro del mismo proceso es reentrante.

## Registro de cada envío

Es automático. Al enviar, `linkedin_apply_submit` (y los envíos inesperados y `linkedin_record_manual`) escribe en los tres sitios:

| Archivo | Contenido |
|---|---|
| `~/.cache/linkedin-mcp/applications.jsonl` | Una línea por envío: respuestas (pregunta → valor), CV con su SHA-256 y de dónde sale, `apply_type`, `ats` o URL externa, `review_text` sin la lista de CV, `confirmed`, `via`. |
| `~/Documents/CV/Postulaciones-LinkedIn.md` | Una fila por envío (tabla de 8 columnas). |
| `perfil.md` → «Estado de postulaciones» | Una fila por envío (tabla de 3 columnas). |

- Las filas solo se **insertan** al final de la tabla, nunca se reescriben. Una fila se omite si ya hay otra con el mismo `job_id` a la misma hora, así que correrlo dos veces no duplica y un reenvío posterior sí queda registrado.
- El texto del estado depende de cómo se envió: con el «sí» de Allan, enviada por Allan a mano, o sin su «sí» (un Siguiente que terminó enviando).
- El hash del CV sale del registro de CV subidos (`resumes.json`: nombre + fecha en LinkedIn); si no está, del archivo local, marcado «no comprobado contra LinkedIn».
- Si falla algún `.md`, el envío no se deshace: la respuesta trae `registro_error`. `cli.py registro-sync` agrega lo que falte.
- `linkedin_record_manual` abre la vacante (0 vistas si la pestaña ya está en ella) y registra solo si LinkedIn la muestra como solicitada; rechaza vacantes que ya estén en el registro local o en los `.md`. Cuenta para el cupo del día pero no lo bloquea un cupo lleno.

## Datos del skill

| Archivo (en `~/.claude/skills/postular-linkedin/references/`) | Para qué |
|---|---|
| `respuestas.json` | Banco de respuestas: patrones es/en, respuesta por tipo, estado (`verificado`, `aprobado <fecha>`, `confirmar`, `preguntar`), fuente y fecha. Es la fuente de verdad. |
| `respuestas-linkedin.md` | Vista legible, **generada** con `cli.py bank-md`; no se edita a mano. |
| `triage.json` | Reglas del triage. Cada criterio cita evidencia de las secciones Experiencia, Docencia o Formación de `perfil.md`. |

`answers.py` propone respuestas por etiqueta y nunca rellena las entradas `confirmar` ni `preguntar`, aunque LinkedIn traiga el campo prellenado: un salario viejo prellenado se pregunta igual. Los años se traducen a rangos de opción y una etiqueta con un tema («… con SAP») solo casa con una entrada que lo nombre.

Rutas y variables de entorno (se leen al llamar, los tests las apuntan a copias): `LINKEDIN_MCP_SKILL_DIR`, `LINKEDIN_MCP_PERFIL`, `LINKEDIN_MCP_CV_DIR`, `LINKEDIN_MCP_POSTULACIONES`. `LINKEDIN_MCP_NO_SAFARI=1` hace que `safari_bridge.osa` rechace toda llamada: los tests lo usan siempre.

## Fallback desde Bash (`cli.py`)

Si las tools `mcp__linkedin__*` no están cargadas (o para probar JS nuevo, porque `server.py` lee `linkedin.js` una sola vez al arrancar y `cli.py` lo lee en cada ejecución):

```bash
cd ~/Documents/linkedin-mcp
.venv/bin/python cli.py tools                              # lista de tools
.venv/bin/python cli.py linkedin_status
.venv/bin/python cli.py linkedin_get_job '{"job_id": "<job_id>"}'
.venv/bin/python cli.py linkedin_apply_prepare '{"job_id": "<job_id>"}' --full
.venv/bin/python cli.py bank-md --dry-run                  # respuestas.json → respuestas-linkedin.md
.venv/bin/python cli.py registro-sync --dry-run            # filas que faltan en los dos .md
```

- Solo ejecuta las tools registradas (`linkedin_*`), por el mismo camino y con la misma validación que el MCP: el candado, la pausa, el filtro de linkedin.com y cada `confirm=True` valen igual. Las funciones internas (`_js`…) no se alcanzan.
- La salida es compacta (textos cortados, listas de opciones y de CV recortadas) pero no oculta ninguna clave; `--full` imprime todo (úsalo con `at_review` para ver el `review_text` completo). Los ejemplos llevan `<job_id>` de relleno: no los corras tal cual, cada `prepare` gasta una vista y abre un formulario.
- Si el MCP arrancó antes de un cambio de código y le falta alguna tool, `cli.py` la ejecuta con el código actual.
- `--dry-run` solo vale para `bank-md` y `registro-sync`; con una tool, la tool se ejecuta de verdad.

## Sondeo de `ats_continue` (solo lectura)

No se sabe si «Continuar» abre un formulario o envía de inmediato; **cuenta como un envío y el MCP no puede frenarlo**, porque lo pulsa Allan. El MCP no lo pulsa nunca. La próxima vez que aparezca:

1. `linkedin_status`: solo si `counters.applications_left > 0` y `next_submit_in_s == 0`; si no, no se le pide que lo pulse.
2. Dejar la pestaña de trabajo en esa vacante (`linkedin_apply_prepare` o `linkedin_get_job(refresh=True)`; `work_tab` dice cuál es), **antes** de que Allan pulse nada. Allan pulsa «Continuar» **en esa pestaña** y dice qué ve. Un ATS externo lo ve él: el MCP solo ve pestañas de linkedin.com.
3. `linkedin_inspect` sin `tab_id` (lee la pestaña de trabajo), **sin recargar** (recargar destruiría un diálogo abierto): anotar si apareció un diálogo con campos, un ATS externo (`job.external_url`) o un «Solicitud enviada» inmediato.
4. Cuando Allan termine, `linkedin_record_manual(job_id)`: lee la vacante, comprueba `applied` y registra (y marca la caché como enviada). Si dice `not_applied` pero Allan la envió, `linkedin_get_job(job_id, refresh=True)` y repetir.
5. Documentar el hallazgo aquí (Notas del DOM) y en la memoria.

## Notas del DOM (06/10/2026, interfaz nueva `/jobs/search-results/`)

LinkedIn usa clases ofuscadas que cambian; el JS se apoya en lo estable.

**Lista de empleos**
- Cada tarjeta es `[role=button][componentkey="job-card-component-ref-<jobId>"]`.
- El título está en `aria-label="Descartar empleo «…»"` del botón de descartar. Empresa y ubicación son los `<p>` que siguen al título.
- Marcas en líneas propias: "Solicitados", "Guardado", "Visto", "Solicitud sencilla", "Evaluando solicitudes…".
- La fecha visible está en un `<span>` que no tiene `aria-hidden`; hay una copia oculta.
- Paginación: `[data-testid^="pagination-indicator-"]` y `pagination-controls-next-button-visible`.

**Vacante** (`/jobs/view/<id>/`)
- `document.title` = "Puesto | Empresa | LinkedIn".
- La descripción está en `[componentkey="JobDetails_AboutTheJob_<id>"] [data-testid=expandable-text-box]`.
  Se dibuja después del título y del botón de postular: `get_job` espera hasta 6 s más por ella antes de guardar la vacante en la caché.
- Botón `aria-label="Solicitud sencilla"`, o `a[aria-label="Solicitar en el sitio web de la empresa"]` con `href` a `linkedin.com/safety/go/?url=<externa>`. Al abrir la Solicitud sencilla, la URL pasa a `/jobs/view/<id>/?companyName=…&trackingId=…&applicantTrackingSystemName=LinkedIn`.
- **Variante ATS, `apply_type: "ats_continue"`.** Ejemplo: cbc vía SmartRecruiters, 4398844859, 06/10/2026.
  - La tarjeta de la lista dice "Solicitud sencilla", pero la vacante muestra un único `<a>Continuar</a>` debajo de los chips de modalidad, sin aria-label ni ícono.
  - Su `href` apunta a la misma vacante: `/jobs/view/<id>/?companyName=cbc&trackingId=…&applicantTrackingSystemName=SmartRecruiters`.
  - Después de que Allan lo pulsó, la vacante quedó en "Solicitud enviada · justo ahora", con "Ir al sitio web de la empresa" (`target=_blank`, `safety/go` → `jobs.smartrecruiters.com/…`).
  - **Pulsarlo cuenta como envío:** el MCP nunca lo pulsa. `linkedin_apply_start` devuelve `ats` y `apply_url` y lo deja a Allan.
  - Para reconocerlo se exige texto exacto "Continuar"/"Continue", host `www.linkedin.com`, ruta `/jobs/view/<mismo id>` y que sea el único enlace así fuera de diálogos, tarjetas y las secciones AboutTheJob/AboutTheCompany. Así no lo confunde con los enlaces de Premium ni con las vacantes recomendadas.
- Ya solicitado: el texto "Estado de la solicitud · Solicitud enviada". Si la solicitud pasó a un ATS, el enlace "Ir al sitio web de la empresa" (lo identifica por su texto visible) da la `external_url`.

**Formulario**
- `dialog[data-testid=dialog]` con un `h2` "Aplicar a <empresa>" y el texto "N/M páginas". Hay variantes de una sola página que muestran directamente "Enviar solicitud".
- Campos: `label[for]` + `select`/`input`.
- Las radios de una pregunta comparten `name`, su `aria-label` es la pregunta y el texto de cada opción está en el `<p>` hermano.
- En el paso del CV, las radios llevan como `aria-label` el nombre del archivo.
- Errores en `<p>` dentro de `[componentkey^="easyApplyFieldFocus"]` ("Este campo es obligatorio", "Información incorrecta").
- Límite de caracteres en `[data-testid=text-input-helper-text]` ("0 de 20 caracteres").
- **Subir CV:** "Cargar currículum" crea un `input[type=file]` en `<body>` y llama a `click()`. El JS intercepta ese `click()` para que no salga el diálogo nativo y entrega el archivo con `DataTransfer`.
- **Cerrar:** el botón X (`aria-label="Descartar"`) abre "¿Quieres guardar esta solicitud?" con los botones "Descartar" y "Guardar".
- **Atrás es «Volver»** (07/10/2026, TPP eMarketing): los pasos 2 en adelante muestran `Volver` y `Siguiente`/`Revisar`; la primera página no tiene botón de retroceso, y así se reconoce un borrador guardado aunque no haya contador de pasos.
- **Botones, por etiqueta** (`button_kind`): `Siguiente`/`Revisar` avanzan; `Enviar solicitud` envía; `Continuar` **nunca** se trata como Siguiente (en cbc/SmartRecruiters envió la solicitud); `Listo` cierra la confirmación.
- **El formulario se dibuja por partes:** primero el contenedor y después los campos, y a veces un spinner deja los campos viejos con el botón Siguiente oculto. Por eso se leen dos veces seguidas hasta que coinciden, y el JS del clic comprueba que los campos sean los planeados.
- **LinkedIn recuerda respuestas anteriores:** campos como el salario pueden llegar prellenados con un valor viejo; se preguntan igual.
- **El texto de revisión** no incluye los valores de los `input` de una página con campos; se arma desde el DOM, con «Currículum: <elegido> (<fecha>)» en lugar de la lista de ~60 CV.
- **La lista de CV** repite nombres (`resume.pdf` ×7, `CV-Allan Rosales.pdf` ×3…): la más reciente va primero, y se distingue por la fecha en LinkedIn.
- **Seguir a la empresa:** casilla "Sigue a <empresa> para enterarte…" en la revisión.

Si LinkedIn cambia la interfaz, vuelve a sondear con una sonda de solo lectura y ajusta `linkedin.js`.

## Instalación

```bash
cd ~/Documents/linkedin-mcp
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install --only-binary=:all: -r requirements.txt
.venv/bin/python -m pytest -q tests/
```

`cryptography<49` y `--only-binary=:all:` van por la misma razón que en `safari-mcp`: en esta Mac Intel con macOS 13 no hay binario de las versiones nuevas.

### Registro en Claude

Va en el ámbito usuario de Claude Code (`~/.claude.json`), que es lo que lee la pestaña Code. `claude` no está en el PATH; desde una sesión de Code se usa el CLI que trae la app:

```bash
"$CLAUDE_CODE_EXECPATH" mcp add linkedin -s user -- /Users/admin/Documents/linkedin-mcp/.venv/bin/python /Users/admin/Documents/linkedin-mcp/server.py
```

Las tools `mcp__linkedin__*` aparecen en la siguiente sesión que se abra o reanude. El servidor corre bajo el CLI, así que hereda su permiso de Automatización sobre Safari.

**No uses `claude_desktop_config.json` con la app abierta.** Claude.app guarda ese archivo desde la copia que tiene en memoria cada vez que cambia una preferencia (`main.log`: "Config file written"), así que borra lo que se agregó por fuera. El 06/10/2026 esto borró `linkedin` y `safari` tres veces. Si hace falta registrarlos ahí (para el chat de la app), está `registrar-mcp.sh`: se corre en Terminal con Claude.app cerrada (Cmd+Q). Se niega a correr si ya están en `~/.claude.json`, para no duplicarlos.

### Requisitos de macOS y Safari

- **Automatización:** permitir que Claude controle Safari (Ajustes → Privacidad y seguridad → Automatización).
- **Safari → Desarrollo → "Permitir JavaScript desde Apple Events":** Allan lo activa a mano y lo apaga al terminar, porque la Mac es compartida. Sin él, las tools devuelven `js_from_apple_events_disabled`.

## Pruebas

```bash
cd ~/Documents/linkedin-mcp
.venv/bin/python -m pytest -q tests/
.venv/bin/python cli.py linkedin_status      # prueba rápida con Safari
```

Los tests nunca tocan Safari (`LINKEDIN_MCP_NO_SAFARI=1`), ni el estado real (`~/.cache/linkedin-mcp`), ni los `.md` de registro: usan carpetas y copias temporales. El test JXA (`tests/test_linkedin_js.py`) compila y prueba `linkedin.js` con `osascript`, sin navegador.
