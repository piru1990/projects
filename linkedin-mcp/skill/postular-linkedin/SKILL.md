---
name: postular-linkedin
description: Postula a empleos de LinkedIn con "Solicitud sencilla" (Easy Apply) desde el Safari de Allan Rosales, con el MCP local linkedin-mcp. Puntúa la búsqueda contra su perfil verificado, reúne las preguntas de cada vacante en pocas llamadas, llena el formulario con respuestas aprobadas y solo envía con un "sí" de Allan para esa vacante, respetando límites diarios para no poner en riesgo la cuenta. Úsalo cuando Allan pida postular, aplicar o revisar empleos de LinkedIn, o comparte un enlace linkedin.com/jobs.
---

# Postular en LinkedIn (Solicitud sencilla)

Objetivo: postular a las vacantes que Allan elija **sin inventar datos**, **sin enviar nada sin su "sí" para esa vacante** y con un ritmo de persona cuidadosa. Ninguna herramienta garantiza que LinkedIn no restrinja la cuenta. Si Allan pregunta, díselo así.

Una vacante normalmente cuesta unas 4 llamadas (`prepare` → preguntas → `fill_all` → "sí" → `submit`), más una por cada paso extra con preguntas. El registro es automático.

## Herramientas

**MCP local `linkedin`** (`~/Documents/linkedin-mcp`, ver su README). Controla el Safari real, con la sesión que Allan inició:

| Tool | Uso |
|---|---|
| `linkedin_status()` | Siempre primero: sesión, JavaScript, pestañas de LinkedIn, `work_tab`, `counters` (vistas, envíos, `next_submit_in_s`, `paused`). |
| `linkedin_triage(tab_id?, page?)` | Puntúa la búsqueda contra `perfil.md` sin abrir vacantes (0 vistas): `encaje`, `motivos`, `banderas`, `modalidad`, `estado`, `tipo`. |
| `linkedin_list_jobs(tab_id?, page?)` | Solo las tarjetas, sin puntaje. |
| `linkedin_get_job(job_id, refresh=False)` | Lee la vacante de la caché de 24 h (sin vista) o la abre (1 vista). Trae `apply_type`, `external_kind`, `account_hint`, `clean_url`. |
| `linkedin_apply_prepare(job_id)` | Abre el formulario y devuelve las preguntas **hasta el primer paso con algo que decidir** (`questionnaire`, `answers_draft`, `to_ask`). Los pasos siguientes llegan con `fill_all`. No llena nada; deja el formulario abierto. |
| `linkedin_apply_fill_all(job_id, answers)` | Llena paso a paso con lo aprobado, verifica y se detiene en la revisión. Nunca envía. |
| `linkedin_apply_submit(job_id, confirm=True)` | Envía. **Solo tras el "sí" de Allan para esa vacante.** Registra solo. |
| `linkedin_apply_upload_resume(file_path)` / `linkedin_apply_select_resume(name\|index)` | Subir (con el ok de Allan) o elegir un CV. |
| `linkedin_apply_close(save_draft=True, not_sent=False)` | Cierra sin enviar. |
| `linkedin_record_manual(job_id)` | Registra una que Allan envió a mano (`ats_continue`). |
| `linkedin_answers_save(entries, confirm)` | Guarda en el banco respuestas que Allan aprobó. |
| `linkedin_inspect(tab_id?)` | Solo lectura de una pestaña `/jobs/` (por defecto la de trabajo). |
| `linkedin_applications(since?)` | Registro local de envíos. |
| `linkedin_resume_after_checkpoint(confirm=True)` | Quita la pausa después de que Allan resolvió una verificación. |

`linkedin_apply_start`, `_read`, `_fill` y `_next` existen para el camino paso a paso, pero no actúan sobre una solicitud abierta con `prepare`: usa `prepare` y `fill_all`.

**Si las tools `mcp__linkedin__*` no están cargadas, o falta alguna** (el MCP arrancó antes de un cambio de código: reinicia la sesión o usa el fallback para esa tool). El fallback solo ejecuta las tools del MCP, con sus mismos candados. Los ejemplos llevan un `<job_id>` de relleno: no los corras tal cual.
```bash
cd ~/Documents/linkedin-mcp && .venv/bin/python cli.py linkedin_status
.venv/bin/python cli.py linkedin_apply_fill_all '{"job_id": "<job_id>", "answers": {...}}' --full
```
Usa `--full` en `fill_all` cuando devuelva `at_review` (y en `draft_detected`): la salida compacta corta `review_text` y lo debes ver completo antes de preguntar si se envía.

**Requisito manual:** Safari → Desarrollo → "Permitir JavaScript desde Apple Events". Si una tool devuelve `js_from_apple_events_disabled`, pídele a Allan que lo active; tú no lo cambies. Al terminar, recuérdale apagarlo: la Mac es compartida.

**Datos de Allan:**
- [perfil.md](../llenar-formulario-postulacion/references/perfil.md): reglas de integridad, experiencia, formación, decisiones y estado de postulaciones.
- `references/respuestas.json`: banco de respuestas (fuente de verdad; `respuestas-linkedin.md` es su vista generada, no la edites).
- `references/triage.json`: reglas del triage.
- CV base: `~/Documents/CV/CV-Allan-Rosales-Tecnologia-ERP.pdf`. Para otros enfoques usa los scripts de `llenar-formulario-postulacion` (`generar_cv.py`, `leer_fuente_cuaderno.py`).

## Flujo

1. **Estado.** `linkedin_status`.
   - Si `counters.paused` no es null: explica qué vio LinkedIn y detente. Allan resuelve la verificación a mano en Safari. Solo cuando él diga que ya está, `linkedin_resume_after_checkpoint(confirm=True)`.
   - Si `logged_in` es false: Allan inicia sesión; tú nunca lo haces.
2. **Triage.** `linkedin_triage` sobre la pestaña de búsqueda que indicó Allan. Cambia de página solo si él lo pide. Si Allan comparte el enlace de una vacante, saca el `job_id` (`/jobs/view/<id>/` o `currentJobId=`) y empieza en `prepare`, sin triage.
   - Muestra una tabla: puesto, empresa, modalidad, tipo, estado, encaje y banderas.
   - Di lo que es provisional: el encaje que sale solo del título (`encaje_provisional`) y el tipo «según tarjeta», que puede cambiar al abrir la vacante.
   - Las banderas son experiencia **sin evidencia** (banca, telco/NOC, programador principal, eléctrico, obra civil, cloud, certificaciones sin verificar). No descartan por sí solas: Allan decide.
   - Omite lo ya solicitado. Allan elige: cada apertura cuenta para el límite diario.
3. **Por cada vacante elegida:**
   1. `linkedin_apply_prepare(job_id)`. Mira `status` y `stopped_at.reason`:
      - `easy_apply`: sigue. Otro tipo: `applied`/`closed` → avísale y pasa a otra; `external` → *Vacantes externas*; `ats_continue` → *Variante ATS*; `unknown` → pídele que la abra en Safari.
      - `reason` = `decision`, `review`, `errors` o `blocked`: sigue con la tabla de preguntas. Los demás casos (`empty_step`, `did_not_advance`, `step_not_settled`, `draft_detected`…): tabla de estados.
   2. **Un mensaje** con la tabla consolidada: pregunta → respuesta propuesta, estado del banco, fuente y el CV que se usará (`resume`). Marca lo que viene prellenado por LinkedIn. Escribe en el texto, junto a la tabla, las preguntas de texto y las filas `confirm`; **después**, en la misma respuesta, el `AskUserQuestion` con las de opción. No llames a `fill_all` hasta tener todas las respuestas. La respuesta de Allan aprueba la tabla: no hace falta otra vuelta. La tabla puede no ser el formulario completo: los pasos siguientes aparecen en `fill_all`.
   3. Arma `answers` con las claves (`key`) del cuestionario: parte de `answers_draft` y agrega lo que Allan respondió. Las filas `confirm` solo entran con su confirmación.
   4. `linkedin_apply_fill_all(job_id, answers)`. Si se detiene antes de la revisión, es un estado de la tabla de abajo (un paso nuevo vuelve como `needs_answers`: otra tabla y otra pregunta).
   5. **Revisión.** Con `at_review`, muestra el resumen (`review_text` completo, sin repetir el teléfono si no hace falta) y pregunta: **"¿Envío la solicitud a <empresa> – <puesto>?"**. Si Allan no quiere enviarla, o hay que parar (límite diario, pausa), pregúntale si guardar el borrador o descartarlo y llama a `linkedin_apply_close(save_draft=...)`: **no dejes el formulario abierto**, porque bloquea la siguiente vacante.
   6. Solo con un "sí" explícito: `linkedin_apply_submit(job_id, confirm=True)`. `follow_company=True` solo si Allan lo pide.
   7. El registro es automático: confirma que la respuesta trae `registro` con los dos `.md`. **No agregues filas a mano.**
   8. Ofrécele guardar en el banco lo reutilizable, con `linkedin_answers_save`, que primero muestra el diff y solo con su ok se repite con `confirm=True`:
      - una fila `confirm` que Allan confirmó pasa a «aprobado <fecha>» con `entries=[{"id": "<entry de la fila>"}]`;
      - una respuesta nueva: `{"question", "patterns": {"es": [...], "en": [...]}, "answer": {"text"|"number"|"yes_no"|"choice"}, "applies": "years"?}`.
      
      Nunca el salario, la fecha de inicio, la modalidad, la reubicación, el patrocinio ni nada `preguntar`: la tool los rechaza.
4. **Al terminar.** Resumen para Allan: envíos de la sesión (empresa, puesto, CV), las que quedaron pendientes o externas, los contadores (`linkedin_status`) y el recordatorio de apagar "Permitir JavaScript desde Apple Events".

## Cómo preguntar

- **2 a 4 opciones reales** (`ask_via: choice`; `choice_multi` para grupos de casillas): un solo `AskUserQuestion` con hasta 4 preguntas por llamada y **sin opciones de relleno**. Nunca una opción tipo "la escribo en Other".
- **Al chat, como texto:** texto libre, **salario**, fechas, una sola opción o más de 4 (lista numerada), y todas las filas `confirm`: muestra el valor sugerido y su `basis` (p. ej. «Jira: 4 años, de dic. 2021 a oct. 2025»). El monto del salario va en el chat: una vez se perdió por la opción "Other".
- Una respuesta de `AskUserQuestion` solo vale si coincide exacto con una opción del campo; si no, repregunta en el chat.
- Respeta `max_length` (p. ej. «Q20,000 negociable» cabe en 20). Los años son enteros.
- Lo que no es `verificado` ni `aprobado` se pregunta siempre, nunca se infiere. Un valor **prellenado** que no esté en el banco también se pregunta.
- Un campo **typeahead** o con **etiqueta repetida** (el `reason` lo dice) no lo llena la tool: Allan lo llena en Safari y tú llamas a `fill_all` con `answers[key]` igual al valor tal como quedó en pantalla (`current`). Así también se acepta un valor prellenado: pasa su `current`.

## Estados en que se detiene

| Estado | Qué hacer |
|---|---|
| `prepared` con `complete: false` o `fill_all` → `needs_answers` (`new_step: true` si es un paso que `prepare` no vio) | Nueva tabla (`questionnaire`/`to_ask` en `prepare`, `questions` en `fill_all`), pregunta, vuelve a llamar a `fill_all`. |
| `form_has_errors` (con `questions`) | LinkedIn marca un campo: pregúntalo y repite. |
| `mismatch`, `fill_failed`, `did_not_advance`, `step_not_settled`, `press_unobserved` | No insistas ni repitas el clic: pídele a Allan que mire Safari. Si pulsó algo a mano, `fill_all` lo detecta (`unplanned_steps`, `answers_not_applied`). |
| `empty_step` | Un paso sin campos (¿falta un CV?). Con el ok de Allan, `fill_all(..., pass_empty_step=True)`. |
| `draft_detected` / `draft_needs_ok` | Hay un borrador guardado. Pregunta si seguir (`continue_draft=True`; muestra todo `review_text`, los pasos anteriores no se vieron) o cerrar con `linkedin_apply_close` (guardar o descartar). |
| `application_in_progress` / `dialog_already_open` | Hay otra solicitud o un formulario abierto: pregunta a Allan y ciérrala con `linkedin_apply_close`. |
| `already_in_log` | Ya figura en el registro local. Solo con la comprobación de Allan de que no se envió, `prepare(..., allow_logged=True)`. |
| `resume.decision: upload_needed` | El CV no está en LinkedIn: con el ok de Allan, `linkedin_apply_upload_resume(file_path=~/Documents/CV/<archivo>)` y `fill_all`. |
| `resume_mismatch`, `resume_unknown`, `resume_unverified` | El CV de la revisión no es el elegido o no se pudo comprobar. Sigue el mensaje: Atrás en Safari hasta el CV y `fill_all` otra vez, o cerrar y preparar de nuevo. |
| `too_soon` (`retry_after_s`) | Dentro del espacio de 180 s tras un envío. Espera y repite **la misma llamada** (`prepare` si es lo que la devolvió; si venía de `fill_all`, `fill_all`). No lo esquives. |
| `daily_apply_limit`, `daily_view_limit` | Se acabaron los envíos o las vistas de hoy: sigue mañana, y no uses `refresh` para saltarlo. Si hay un formulario abierto, ciérralo (ver *Revisión*). |
| `unexpected_submit` / `dialog_vanished` | Algo se envió (o no se sabe) al pulsar Siguiente/Revisar. Quedó registrado y el MCP en pausa: dile a Allan que lo revise en Safari. |
| `submit_unverified` | Un Enviar no se pudo comprobar. No lo repitas: Allan revisa en Safari. Si no se envió, `linkedin_apply_close(not_sent=True)`; si se envió, cerrar lo registra. |
| `review_changed` | La revisión cambió después de que Allan la vio: vuelve a llamar a `fill_all`, muestra el nuevo `review_text` y pide un nuevo "sí". |
| Otro error de `submit` (`form_incomplete`, `company_mismatch`, `not_at_review`, `form_has_errors`…) | No repitas: dile a Allan el mensaje y que mire Safari. |
| `confirmed: false` en `submit` | Comprueba con `linkedin_get_job(job_id, refresh=True)` (1 vista) antes de pensar en repetir. Quedó registrada para no duplicarla. |
| `registro_error` | El envío sí se hizo. Avísale a Allan y corre `cli.py registro-sync` cuando se arregle el archivo. |
| `paused_checkpoint` | Verificación o límite de LinkedIn. Para todo; lo resuelve Allan. |

## Vacantes externas

Según `external_kind` (da la `clean_url`, sin `utm_*`):
- `google_forms` o `microsoft_forms`: usa el skill `llenar-formulario-postulacion`.
- `ats:<nombre>` y `job_board`: mira `account_hint` (`si` suele pedir cuenta). Crear cuentas o iniciar sesión lo hace Allan.
- `company_site` o `unknown`: dásela a Allan.

## Variante ATS (`apply_type: ats_continue`)

El botón «Continuar» hacia el ATS de la empresa (cbc/SmartRecruiters, 06/10/2026) **marcó la vacante como enviada**: se sabe que cuenta como envío y **no se sabe** si abre un formulario o envía directo. Claude nunca lo pulsa ni lo automatiza, y **el MCP no puede frenarlo**: lo pulsa Allan. Por eso, antes de pedírselo:

1. `linkedin_status`: solo si `counters.applications_left > 0` y `counters.next_submit_in_s == 0`. Si no, no le pidas que lo pulse. Dile que «Continuar» cuenta como un envío y que puede enviar de inmediato.
2. Deja la pestaña de trabajo en esa vacante (`prepare` o `get_job(refresh=True)`); `work_tab` de `linkedin_status` dice cuál es. Allan pulsa «Continuar» **en esa pestaña** y te cuenta qué ve (otra pestaña, otro dominio, un diálogo). Un ATS externo lo ve él: tú solo ves las pestañas de linkedin.com.
3. `linkedin_inspect` sin `tab_id` (lee la pestaña de trabajo), **sin recargar** (recargar destruiría un diálogo abierto). Anota si apareció un diálogo con campos, un ATS externo (`job.external_url`) o un «Solicitud enviada» inmediato. `linkedin_status` sirve para los contadores y la pausa.
4. Cuando Allan termine: `linkedin_record_manual(job_id)` comprueba `applied` y escribe las filas «enviada por Allan». Si devuelve `not_applied` pero Allan dice que la envió, haz `linkedin_get_job(job_id, refresh=True)` y repite.
5. Lleva el hallazgo a las Notas del DOM del README y a la memoria `linkedin-mcp`.

## CV

- Por defecto usa el CV base de Tecnología; `prepare` lo propone y `fill_all` lo selecciona (la copia más reciente con ese nombre).
- Si la vacante es claramente de otro enfoque (docencia, comercial, finanzas), propón generar la variante con el skill `llenar-formulario-postulacion` y espera su sí antes de subirla. Para usar otro CV, pásalo en `resume=` a `prepare`.
- Un CV nuevo se sube solo con el ok de Allan. Quedan registrados su nombre, fecha en LinkedIn y SHA-256.

## Ritmo y límites

El MCP los aplica; no intentes rodearlos:
- Máximo 10 envíos y 40 vacantes abiertas al día. No se suben.
- Al menos 3 minutos entre envíos y 8 segundos entre navegaciones, y una pausa fija entre clics del formulario.
- Una sola operación a la vez. Nada se envía en lote.

Ante cualquier verificación, CAPTCHA, "cuenta restringida" o aviso de límite de LinkedIn, el MCP se pausa: no intentes resolverlo ni reintentar.

## Reglas

- **Nunca** llames a `linkedin_apply_submit` sin un "sí" explícito de Allan para **esa** vacante. Una aprobación no se extiende a otras vacantes.
- No inventes experiencia, certificaciones ni cifras. Aplica las reglas de integridad de `perfil.md`. Lo que no está verificado o aprobado, se pregunta.
- No inicies sesión, no escribas mensajes a reclutadores, no envíes invitaciones y no edites el perfil.
- No uses el botón "Enviar mensaje" de la vacante ni contactes al anunciante.
- No postules para probar. Para probar la lectura, usa vacantes que Allan elija: cada apertura cuenta como vista.
- **No delegues nada de `linkedin_*` ni de `cli.py` a subagentes ni a revisores**: abren Safari de verdad y se saltan el contador de vistas. Las revisiones de código corren con `LINKEDIN_MCP_NO_SAFARI=1`.
- Lee solo las pestañas de LinkedIn. Safari lo comparte otra persona.
- No pongas datos personales en URLs.
