Usa el skill postular-linkedin solo como referencia: en esta sesión NO se postula a nada. El objetivo es mejorar el MCP linkedin-mcp, el skill y sus herramientas para que las próximas sesiones de postulación tengan menos pasos manuales, sin quitar ninguna salvaguarda.

CONTEXTO
- MCP: ~/Documents/linkedin-mcp (server.py, linkedin.js, guard.py, safari_bridge.py, tests/, README.md con "Notas del DOM"). Está registrado en el ámbito usuario (~/.claude.json). server.py lee linkedin.js una sola vez al arrancar, así que para probar el JS nuevo hay que reiniciar la sesión o usar el fallback desde Bash.
- Skill: ~/.claude/skills/postular-linkedin (SKILL.md y references/respuestas-linkedin.md). Datos verificados: ~/.claude/skills/llenar-formulario-postulacion/references/perfil.md.
- Registro de envíos: ~/Documents/CV/Postulaciones-LinkedIn.md, "Estado de postulaciones" en perfil.md y ~/.cache/linkedin-mcp/applications.jsonl.
- Memorias: linkedin-mcp y safari-mcp-formularios.

PROBLEMAS DE LA SESIÓN DEL 06/10/2026
1. Cada vacante pidió muchas idas y vueltas: una llamada por paso para leer, otra para avanzar, luego preguntar, llenar y avanzar de nuevo.
2. Las respuestas salen a mano de un banco en markdown.
3. Después de cada envío escribí a mano dos archivos de registro. applications.jsonl no guarda las respuestas, y review_text se corta a los 6000 caracteres porque lo llena la lista de ~60 CV.
4. El fallback desde Bash necesitó un runner improvisado en el scratchpad (li.py) para compactar la salida.
5. Una expectativa salarial se perdió porque se pidió con la opción "Other" de AskUserQuestion.
6. Variante ATS: en cbc (4398844859, SmartRecruiters), el enlace "Continuar" marcó la vacante como "Solicitud enviada". Hoy el MCP la reconoce como apply_type "ats_continue" y nunca la pulsa. No sabemos si "Continuar" abre un formulario o envía directo.
7. Las URL externas no indican si son un formulario, un ATS o una bolsa de empleo que pide cuenta.
8. El triage de la lista lo hice a mano.
9. Volver a leer una vacante gasta otra vista del cupo diario.

TAREAS (propón un plan corto y espera mi ok antes de implementar)
A. MCP
  1. Banco estructurado: pasa respuestas-linkedin.md a un archivo de datos (p. ej. references/respuestas.json) que siga siendo legible, o genera el .md desde el .json.
     - Cada entrada lleva: patrones de pregunta (es/en), respuesta por tipo de campo, estado (verificado / aprobado <fecha> / confirmar / preguntar), fuente y fecha.
     - Un módulo puro, answers.py, propone respuestas por etiqueta y nunca rellena las que están en "confirmar" o "preguntar". Lleva tests.
  2. linkedin_apply_prepare(job_id): abre la vacante y la Solicitud sencilla, recorre los pasos sin llenar nada y devuelve un solo cuestionario consolidado con las respuestas propuestas por answers.py y lo que falta preguntar.
  3. linkedin_apply_fill_all(answers): llena el paso, exige all_ok, avanza y repite hasta la revisión. Se detiene ante una pregunta nueva, un error o un mismatch. Nunca envía.
  4. Registro automático: en el envío, applications.jsonl guarda las respuestas (etiqueta → valor), el CV elegido y su SHA-256 si existe en ~/Documents/CV, y el ats o la URL externa. modalRead deja la lista de CV fuera de review_text. Un script o tool agrega, de forma idempotente por job_id, la fila en Postulaciones-LinkedIn.md y en perfil.md, y permite filas "enviada por Allan" (ats_continue).
  5. Caché de vacantes por job_id en el directorio de estado (TTL de 24 h), para releer sin gastar vistas. linkedin_get_job(job_id, refresh=False) y una navegación solo cuando haga falta actuar.
  6. linkedin_triage(tab_id?): lee la lista y puntúa cada vacante contra perfil.md de forma determinista. Marca lo que pide experiencia sin evidencia (banca, telco/NOC, programador principal, diseño eléctrico) y no abre vacantes.
  7. external_kind en linkedin_get_job: google_forms / microsoft_forms / ats:<nombre> (smartrecruiters, viterbit, workday, taleo, greenhouse, lever, deel…) / job_board (unmejorempleo, trabajosdiarios, computrabajo…), con un indicio de si pide cuenta y la URL sin utm_*.
  8. cli.py en el repo: el runner del fallback (`cli.py <tool> '<json>'`) con salida compacta. Documéntalo en el README y en el skill.
  9. Tests: mantén tests/test_linkedin_js.py (JXA) y agrega tests de answers.py, del caché, del registro y de external_kind. Corre `.venv/bin/python -m pytest -q tests/`.
B. Skill postular-linkedin: reescribe el flujo con las tools nuevas.
  - Una tabla consolidada por vacante.
  - Las preguntas de opción se agrupan en un solo AskUserQuestion; las de texto libre (salario, fechas) se piden en el chat.
  - El registro es automático y la sesión termina con un resumen.
C. Variante ats_continue: no la automatices. Documenta en el skill cómo sondear en solo lectura la próxima vez que aparezca, después de que yo pulse "Continuar".
D. Al final: actualiza el README, el SKILL.md y las memorias. Reinicia o pídeme reiniciar y verifica con ToolSearch que las tools nuevas carguen.

LÍMITES (no cambian)
- linkedin_apply_submit solo con confirm=True después de mi "sí" para ESA vacante. Nada lo envía en lote.
- Topes: 10 envíos y 40 vistas al día, 180 s entre envíos y 8 s entre navegaciones. No se suben.
- Sin sigilo, sin user-agent falso, sin retrasos aleatorios "humanos", sin CAPTCHA, sin proxies y sin scraping masivo.
- Ante una verificación o un aviso de límite, el MCP se pausa y lo resuelvo yo.
- No iniciar sesión, no enviar mensajes, no editar mi perfil y no contactar reclutadores.
- Solo pestañas de linkedin.com, y nunca una tool que ejecute JavaScript arbitrario.
- No inventar datos: lo que no esté verificado o aprobado se pregunta.
- No postules para probar. Para probar la lectura, usa vacantes que yo elija, sabiendo que cada apertura cuenta como vista.
- La carpeta no es un repo git: propón `git init` local antes de cambiar código, para tener diffs. Muéstrame cada diff antes de dejarlo.
