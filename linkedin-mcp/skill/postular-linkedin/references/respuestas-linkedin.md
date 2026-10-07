# Banco de respuestas para Solicitud sencilla (LinkedIn)

> **Generado desde `respuestas.json`; no lo edites a mano.** Para cambiar algo, edita el JSON o usa `linkedin_answers_save`, y vuelve a generarlo con `cli.py bank-md`.

Fuente de cada dato: `../llenar-formulario-postulacion/references/perfil.md` (06/10/2026) o una aprobación explícita de Allan en el chat, con su fecha.

Estados:
- **verificado**: está en el perfil y se usa tal cual.
- **aprobado <fecha>**: Allan lo aprobó en el chat ese día; se usa tal cual.
- **confirmar**: se deriva de las fechas; se usa solo después de que Allan lo confirme una vez. Al confirmarlo, cambia a "aprobado <fecha>".
- **preguntar**: nunca se infiere; se pregunta en cada vacante. Las de 2 a 4 opciones van en AskUserQuestion; el texto libre (salario, fechas) va en el chat, nunca por la opción "Other".

## Contacto (LinkedIn suele traerlo lleno)

| Pregunta | Respuesta | Estado |
|---|---|---|
| Email | rosales.allan@gmail.com | verificado |
| Código del país | Guatemala (+502) | verificado |
| Teléfono móvil / Phone | 57030067 | verificado |
| Ciudad / Location (city) | Guatemala | verificado |

## Años de experiencia (número entero)

| Pregunta típica | Respuesta | Base | Estado |
|---|---|---|---|
| Experiencia profesional total | 14 | abr. 2012 – sep. 2026 | verificado ("más de 10" en textos) |
| Gerencia o liderazgo de TI | 1 | Gerente de Tecnología, oct. 2025 – sep. 2026 | confirmar |
| Liderazgo de personas / equipos | 4 | Cementos Progreso 2015–2018 (20 directos) + Intense 2025–2026 | confirmar |
| Gestión de proyectos | 7 | Xerox PM 2019–2021 + cbc 2021–2025 + Intense 2025–2026 | confirmar |
| SAP (integraciones, S/4HANA) | 2 | cbc Integraciones, sep. 2023 – oct. 2025 | confirmar |
| ERP en general (SAP, Odoo, O4Bi) | 3 | cbc 2023–2025 + Intense 2025–2026 | confirmar |
| Odoo | 1 | Intense 2025–2026 | confirmar |
| Jira / Jira Service Management | 4 | cbc dic. 2021 – oct. 2025 | confirmar |
| Power BI / SQL / BI | 3 | Xerox 2019–2021 | confirmar |
| Python | 1 | Intense 2025–2026 | confirmar |
| Microsoft 365 / Intune / Entra ID | 1 | Intense 2025–2026 | confirmar |
| Agile / Scrum / Kanban | 4 | cbc 2021–2025 | confirmar |
| Docencia universitaria | 1 | USAC 2018 | verificado |
| IT Service Management (ITSM) | 5 | cbc JSM dic. 2021 – oct. 2025 + Intense Helpdesk, SLA y soporte 2025–2026 | aprobado 06/10/2026 |

Sin evidencia (respuesta sugerida 0 o "No"; se confirma con Allan, nunca se infiere):
- Banca (cartera, créditos, tarjetas).
- Telco (NOC, redes móviles).
- Desarrollo de software como programador principal (Node.js/React/TypeScript productivo). Usó Node.js en dashboards SLA (Intense 2025–2026), no como programador principal.
- AWS como arquitecto.
- Diseño eléctrico.

## Sí / No frecuentes

| Pregunta | Respuesta | Estado |
|---|---|---|
| ¿Título universitario (licenciatura / bachelor's)? | Sí: Ingeniería Industrial, UVG | verificado |
| ¿Maestría / MBA? | Sí: MBA en Dirección Estratégica, EUNCET / ADEN | verificado |
| ¿Colegiado activo? | Sí | verificado |
| ¿Certificación PMP? | Sí, con la redacción de `perfil.md` (expedición publicada abril 2017, vigencia declarada por Allan) | verificado |
| Nivel de inglés | Avanzado (professional working proficiency) | verificado |
| ¿Disponibilidad para trabajo presencial? | — | preguntar |
| ¿Disponibilidad para trabajo híbrido / remoto? | — | preguntar |
| ¿Dispuesto a reubicarse? | — | preguntar |
| ¿Autorizado para trabajar en Guatemala sin patrocinio? | — | preguntar |
| ¿Requiere patrocinio de visa? | — | preguntar |
| ¿Licencia de conducir / vehículo propio? | Sí: vehículo propio y licencia; puede movilizarse a sucursales | aprobado 06/10/2026 |
| Fecha de inicio / disponibilidad | — | preguntar (el CV PRINCIPAL dice "Disponibilidad inmediata"; confirmarlo) |

## Salario

Salario / expectativa salarial: siempre **preguntar**. Por vacante y moneda, como texto en el chat. Las pretensiones históricas no son universales (Criterios de adaptación, 04/10/2026). Respeta el `max_length` del campo: por ejemplo, "Q20,000 negociable" cabe en 20 caracteres.

## Respuestas aprobadas por Allan

Registro, con fecha, de cada respuesta que Allan aprobó como reutilizable.

| Fecha | Pregunta | Respuesta |
|---|---|---|
| 06/10/2026 | Nivel de inglés con opciones None / Conversational / Professional / Native or bilingual | Professional |
| 06/10/2026 | How many years of work experience do you have with IT Service Management? | 5 |
| 06/10/2026 | ¿Licencia de conducir / vehículo propio? | Sí: vehículo propio y licencia; puede movilizarse a sucursales |
