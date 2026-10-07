function (ACTION, ARG) {
  // Page-side half of linkedin-mcp. Python runs `(<this file>)(action, arg)` through Safari's
  // "do JavaScript" and gets a JSON string back. Selectors lean on roles, aria-labels, visible
  // text (es/en) and LinkedIn's semantic componentkeys, never on the obfuscated class names.
  // DOM notes (2026-10-06, new /jobs/search-results/ UI) live in README.md.
  var APPLY_RE = /^(solicitud sencilla|easy apply)$/;
  var EXTERNAL_RE = /(sitio web de la empresa|company website)/;
  var CONTINUE_RE = /^(continuar|continue)$/;
  // "Continuar" is NOT next: on cbc/SmartRecruiters (06/10/2026) it sent the application. Only these advance.
  var NEXT_RE = /^(siguiente|next|revisar|review)$/;
  var SUBMIT_RE = /^(enviar solicitud|submit application|enviar|submit)$/;
  var DONE_RE = /^(listo|done)$/;
  var BACK_RE = /^(atras|volver|regresar|back|anterior|previous)$/;
  var SUCCESS_RE = /(se envio tu solicitud|tu solicitud se ha enviado|solicitud enviada|your application was sent|application sent|application submitted)/;
  var SAVE_PROMPT_RE = /(guardar esta solicitud|save this application)/;
  var ERROR_RE = /(obligatorio|incorrect|requerid|required|invalid|invalido|valido|introduce un|ingresa un|enter a |selecciona una opcion|select an option|debe ser|must be)/;
  var RESUME_RE = /\.(pdf|docx?|odt|txt)$/;

  function all(root, sel) { return root ? Array.prototype.slice.call(root.querySelectorAll(sel)) : []; }
  function clean(s) {
    return String(s == null ? '' : s).replace(/[   \t]/g, ' ')
      .replace(/ +/g, ' ').replace(/\s*\n\s*/g, '\n').trim();
  }
  function norm(s) {
    return String(s == null ? '' : s).normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/[   \t\r\n]/g, ' ').replace(/^[\s•·*-]+/, '')
      .replace(/[\s*]+$/, '').replace(/\s+/g, ' ').trim().toLowerCase();
  }
  function text(el) { return el ? clean(el.innerText || el.textContent) : ''; }
  function visible(el) { return !!(el && el.getClientRects().length); }
  function label(el) { return clean((el.innerText || '').trim() || el.getAttribute('aria-label') || ''); }
  // exact > prefix > substring, on normalized text
  function pick(list, want, labelOf) {
    var w = norm(want);
    var hits = list.filter(function (x) { return norm(labelOf(x)) === w; });
    if (hits.length) return hits;
    hits = list.filter(function (x) { return norm(labelOf(x)).indexOf(w) === 0; });
    if (hits.length) return hits;
    return list.filter(function (x) { return w && norm(labelOf(x)).indexOf(w) >= 0; });
  }
  // submit > continue > next: a label is never "next" if it could send the application.
  function buttonKind(s) {
    var n = norm(s);
    if (SUBMIT_RE.test(n)) return 'submit';
    if (CONTINUE_RE.test(n)) return 'continue';
    if (NEXT_RE.test(n)) return 'next';
    if (DONE_RE.test(n)) return 'done';
    if (BACK_RE.test(n)) return 'back';
    return 'other';
  }
  function setText(el, v) {
    v = String(v == null ? '' : v);
    try { el.focus(); } catch (e) {}
    var ok = false;
    try { el.select(); ok = v ? document.execCommand('insertText', false, v) : document.execCommand('delete'); } catch (e) {}
    if (!ok || el.value !== v) {
      var proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }
    el.dispatchEvent(new Event('change', { bubbles: true }));
    try { el.blur(); } catch (e) {}
  }
  function setSelect(el, opt) {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(el, opt.value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  // ---------- page ----------
  function dialogs() { return all(document, 'dialog,[role=dialog],[role=alertdialog]').filter(visible); }
  function pageState() {
    var heads = all(document, 'main h1, main h2, dialog h1, dialog h2, dialog h3, [role=alertdialog] h2')
      .filter(visible).map(text).filter(Boolean).slice(0, 20);
    var alerts = all(document, '[role=alert], [data-testid=toasts-title] ~ *')
      .filter(visible).map(text).filter(Boolean).slice(0, 10);
    // Other dialogs (limit notices, verification prompts) count; the application form itself
    // does not, so a screening question can't trip the checkpoint detector.
    var app = appDialog();
    dialogs().forEach(function (d) { if (d !== app) alerts.push(text(d).slice(0, 300)); });
    var captcha = all(document, 'iframe').some(function (f) { return /captcha|challenge|arkose|funcaptcha/i.test(f.src || ''); });
    return {
      url: location.href, title: document.title, ready: document.readyState,
      logged_in: !!document.querySelector('[data-testid=primary-nav], nav a[href*="/feed/"], #global-nav'),
      visible: document.visibilityState === 'visible',
      headings: heads, alerts: alerts, captcha_frame: captcha
    };
  }

  // ---------- job list ----------
  var FLAG_RES = [
    ['applied', /^(solicitados?|applied)$/],
    ['saved', /^(guardado|saved)$/],
    ['viewed', /^(visto|viewed)$/],
    ['easy_apply', /^(solicitud sencilla|easy apply)$/],
    ['actively_reviewing', /^(evaluando solicitudes de forma activa|actively reviewing applicants)$/],
    ['early_applicant', /^(adelantate a solicitar el empleo|be an early applicant)$/]
  ];
  function listJobs() {
    var cards = all(document, '[componentkey^="job-card-component-ref-"]').filter(function (c) {
      return c.getAttribute('role') === 'button' || !c.parentElement.closest('[componentkey^="job-card-component-ref-"]');
    });
    var seen = {};
    var jobs = [];
    cards.forEach(function (c) {
      var id = c.getAttribute('componentkey').replace('job-card-component-ref-', '');
      if (seen[id]) return;
      seen[id] = 1;
      var dismiss = c.querySelector('[aria-label^="Descartar empleo"], [aria-label^="Dismiss"]');
      var m = dismiss && /[«"“](.+)[»"”]/.exec(dismiss.getAttribute('aria-label') || '');
      var lines = text(c).split('\n').filter(function (l) { return l && l !== '·'; });
      var title = m ? m[1] : (lines[0] || '');
      var nt = norm(title);
      // Some cards wrap the title in a <p> too; company and location are the next ones.
      var ps = all(c, 'p').map(text).filter(function (t) { return t && t !== '·' && !(nt && norm(t).indexOf(nt) >= 0); });
      var job = { job_id: id, title: clean(title), company: ps[0] || '', location: ps[1] || '',
                  verified: /empleo verificado|verified job/i.test(text(c)), posted: '', insight: '' };
      FLAG_RES.forEach(function (f) { job[f[0]] = false; });
      lines.forEach(function (l) {
        var n = norm(l);
        FLAG_RES.forEach(function (f) { if (f[1].test(n)) job[f[0]] = true; });
        if (/(contacto|antiguo|alumno|connection|alumni|employee)/i.test(l) && !job.insight) job.insight = l;
      });
      // The card repeats the date in an aria-hidden span; read the visible one.
      var posted = all(c, 'span').filter(function (s) {
        return !s.closest('[aria-hidden=true]') && /^(publicado|posted|vuelto a publicar|reposted)\b/i.test(text(s));
      })[0];
      if (posted) job.posted = text(posted).replace(/^(publicado|posted|vuelto a publicar|reposted)\s+/i, '');
      jobs.push(job);
    });
    var pages = all(document, '[data-testid^="pagination-indicator-"]');
    var current = pages.filter(function (b) { return b.getAttribute('aria-current') === 'true'; })[0];
    var total = (/((?:m[aá]s de|over)\s+)?\d[\d.,]*\+?(?=\s+(resultados|results))/i.exec(text(document.querySelector('main') || document.body)) || [])[0] || '';
    return {
      url: location.href, count: jobs.length, jobs: jobs, total_results: total,
      page: current ? parseInt(text(current), 10) : null,
      pages: pages.map(function (b) { return parseInt(text(b), 10); }),
      has_next: !!document.querySelector('[data-testid="pagination-controls-next-button-visible"]')
    };
  }
  function gotoPage(n) {
    var b = n === 'next'
      ? document.querySelector('[data-testid="pagination-controls-next-button-visible"]')
      : all(document, '[data-testid^="pagination-indicator-"]').filter(function (x) { return text(x) === String(n); })[0];
    if (!b) return { status: 'page_not_found', page: n };
    b.click();
    return { status: 'clicked', page: n };
  }

  // ---------- job detail ----------
  // ATS-backed jobs (cbc via SmartRecruiters, 06/10/2026) show <a>Continuar</a> instead of "Solicitud
  // sencilla", linking back to this same job with ?applicantTrackingSystemName=<ATS>. After Allan pressed it,
  // the job read "Solicitud enviada" with a link to the ATS, so it counts as a submit and is never clicked here.
  function continueLink(main, id) {
    var hits = all(main, 'a').filter(visible).filter(function (a) {
      return CONTINUE_RE.test(norm(a.getAttribute('aria-label') || a.innerText)) &&
        a.hostname === 'www.linkedin.com' && a.pathname.replace(/\/$/, '') === '/jobs/view/' + id &&
        !a.closest('dialog, [role=dialog], [componentkey^="job-card-component-ref-"], ' +
                   '[componentkey^="JobDetails_AboutTheJob"], [componentkey^="JobDetails_AboutTheCompany"]');
    });
    return hits.length === 1 ? hits[0] : null;
  }
  function jobDetail() {
    var id = (/\/jobs\/view\/(\d+)/.exec(location.pathname) || [])[1] || '';
    var main = document.querySelector('main') || document.body;
    var about = document.querySelector('[componentkey="JobDetails_AboutTheJob_' + id + '"]') ||
                document.querySelector('[componentkey^="JobDetails_AboutTheJob"]');
    var aboutBox = about && (about.querySelector('[data-testid=expandable-text-box]') || about);
    var company = document.querySelector('[componentkey^="JobDetails_AboutTheCompany"]');
    var head = text(main).split('\n').filter(Boolean);
    var docTitle = document.title.split(' | ');  // "Tech Lead | TPP eMarketing | LinkedIn"
    var btns = all(main, 'button, a').filter(visible);
    var easy = btns.filter(function (b) { return APPLY_RE.test(norm(b.getAttribute('aria-label') || b.innerText)); })[0];
    // aria-label on the apply button; visible text on "Ir al sitio web de la empresa" after an ATS hand-off.
    var ext = btns.filter(function (b) { return EXTERNAL_RE.test(norm(b.getAttribute('aria-label') || b.innerText)); })[0];
    var extUrl = '';
    if (ext && ext.href) {
      // Unwrap only LinkedIn's own redirect (safety/go); Python's external.unwrap handles the rest.
      try {
        var eu = new URL(ext.href);
        var own = /(^|\.)linkedin\.com$/.test(eu.hostname) && /^\/safety\/go\/?$/.test(eu.pathname);
        extUrl = (own && eu.searchParams.get('url')) || ext.href;
      } catch (e) { extUrl = ext.href; }
    }
    var cont = easy || ext ? null : continueLink(main, id);
    var ats = '', applyUrl = '';
    if (cont) {
      try {
        var cu = new URL(cont.href);
        ats = cu.searchParams.get('applicantTrackingSystemName') || '';
        cu.searchParams.delete('trackingId');
        applyUrl = cu.href;
      } catch (e) { applyUrl = cont.href; }
    }
    var mainText = norm(text(main));
    var applied = /(estado de la solicitud solicitud enviada|application status application submitted|solicitud enviada hace|applied \d|applied on)/.test(mainText.replace(/\n/g, ' '));
    var closed = /(ya no se aceptan solicitudes|no longer accepting applications)/.test(mainText);
    var appliedLine = '';
    head.forEach(function (l, i) { if (!appliedLine && /^(solicitud enviada|application submitted)$/i.test(l)) appliedLine = l + (head[i + 1] ? ' ' + head[i + 1] : ''); });
    var desc = aboutBox ? text(aboutBox).replace(/\s*…\s*(más|more)\s*$/i, '') : '';
    return {
      job_id: id, url: location.href,
      company: docTitle.length >= 3 ? clean(docTitle[docTitle.length - 2]) : head[0] || '',
      title: docTitle.length >= 3 ? clean(docTitle.slice(0, -2).join(' | ')) : head[1] || '', meta: head[2] || '',
      chips: head.slice(3, 9).filter(function (l) { return /^(presencial|hibrido|híbrido|en remoto|remoto|remote|hybrid|on-site|jornada completa|media jornada|full-time|part-time|contrato|contract|temporal|temporary|practicas|internship)$/i.test(l); }),
      apply_type: applied ? 'applied' : closed ? 'closed' : easy ? 'easy_apply' : ext ? 'external' : cont ? 'ats_continue' : 'unknown',
      applied_status: appliedLine, external_url: extUrl, ats: ats, apply_url: applyUrl,
      description: desc, company_about: company ? text(company).slice(0, 1500) : ''
    };
  }
  function openEasyApply() {
    var main = document.querySelector('main') || document.body;
    var b = all(main, 'button, a').filter(visible).filter(function (x) {
      return APPLY_RE.test(norm(x.getAttribute('aria-label') || x.innerText));
    })[0];
    if (!b) return { status: 'no_easy_apply_button' };
    b.click();
    return { status: 'clicked' };
  }

  // ---------- Easy Apply dialog ----------
  function appDialog() {
    return dialogs().filter(function (d) {
      var h = d.querySelector('h2');
      return /^(aplicar a|solicitar a|apply to)\b/.test(norm(text(h))) && !SAVE_PROMPT_RE.test(norm(text(d)));
    })[0] || null;
  }
  function savePrompt() { return dialogs().filter(function (d) { return SAVE_PROMPT_RE.test(norm(text(d))); })[0] || null; }
  // The confirmation, not the form: a dialog that still has questions or the form's own buttons is the
  // application itself, even if a screening question quotes "solicitud enviada".
  function successDialog() {
    return dialogs().filter(function (d) {
      if (!SUCCESS_RE.test(norm(text(d)))) return false;
      var asks = all(d, 'input, select, textarea').some(function (el) {
        return visible(el) && el.type !== 'hidden' && el.type !== 'checkbox';
      });
      var formButtons = all(d, 'button').filter(visible).some(function (b) {
        var k = buttonKind(b.innerText);
        return k === 'next' || k === 'submit' || k === 'continue';
      });
      return !asks && !formButtons;
    })[0] || null;
  }
  function container(el) {
    return el.closest('[componentkey^="easyApplyFieldFocus"]') || el.closest('fieldset') || el.parentElement.parentElement;
  }
  function questionText(el, c) {
    var lab = el.labels && el.labels[0] && text(el.labels[0]);
    if (lab) return lab;
    if (el.type === 'radio' || el.type === 'checkbox') {
      var fs = el.closest('fieldset');
      var lg = fs && fs.querySelector('legend');
      if (lg && text(lg)) return text(lg);
    }
    var aria = clean(el.getAttribute('aria-label'));
    if (aria) return aria;
    var p = c && c.parentElement && c.parentElement.firstElementChild;
    return p && p !== c ? text(p) : '';
  }
  function optionText(inp) {
    var lab = inp.labels && inp.labels[0] && text(inp.labels[0]);
    if (lab) return lab;
    var sib = inp.parentElement && inp.parentElement.nextElementSibling;
    if (sib && text(sib)) return text(sib);
    return clean(inp.getAttribute('aria-label') || inp.value);
  }
  function errorsIn(c, q) {
    var qn = norm(q);
    return all(c, 'p, span, div[role=alert]').filter(function (e) {
      return e.children.length === 0 && visible(e) && ERROR_RE.test(norm(text(e))) && norm(text(e)) !== qn;
    }).map(text);
  }
  function fields(d) {
    var out = [], groups = {};
    all(d, 'input, select, textarea').forEach(function (el) {
      if (el.type === 'hidden' || el.type === 'file' || el.disabled && el.type !== 'radio') return;
      var c = container(el);
      if (el.type === 'radio' || el.type === 'checkbox') {
        var key = el.name || (el.closest('fieldset') ? 'fs' + out.length : el.id);
        var g = groups[key];
        if (!g) {
          var q = questionText(el, c);
          g = groups[key] = { label: q, type: el.type, name: key, required: false, options: [], value: el.type === 'radio' ? null : [], _els: [], _arias: [], _c: c };
          out.push(g);
        }
        var o = optionText(el);
        g._arias.push(clean(el.getAttribute('aria-label')));
        g.options.push(o);
        g._els.push(el);
        if (el.required || el.getAttribute('aria-required') === 'true') g.required = true;
        if (el.checked) { if (el.type === 'radio') g.value = o; else g.value.push(o); }
        return;
      }
      var lbl = questionText(el, c);
      var f = { label: lbl, type: el.tagName === 'SELECT' ? 'select' : el.tagName === 'TEXTAREA' ? 'textarea'
                : (el.getAttribute('role') === 'combobox' || el.getAttribute('aria-autocomplete') === 'list') ? 'typeahead' : (el.type || 'text'),
                required: !!(el.required || el.getAttribute('aria-required') === 'true' || /\*\s*$/.test(lbl)),
                value: el.tagName === 'SELECT' ? (el.selectedIndex >= 0 ? clean(el.options[el.selectedIndex].text) : '') : el.value,
                _els: [el], _c: c };
      if (el.tagName === 'SELECT') f.options = all(el, 'option').map(function (o) { return clean(o.text); }).filter(Boolean);
      var help = c && c.querySelector('[data-testid=text-input-helper-text]');
      var mx = help && /(?:de|of)\s+(\d+)\s+(?:caracteres|characters)/i.exec(text(help));
      if (mx) f.max_length = parseInt(mx[1], 10);
      else if (el.maxLength > 0) f.max_length = el.maxLength;
      out.push(f);
    });
    out.forEach(function (f) {
      f.label = clean(f.label).replace(/\s*\*$/, '');
      if (/\*\s*$/.test(text(f._c && f._c.querySelector('p, legend, label')) || '')) f.required = true;
      var errs = errorsIn(f._c || d, f.label);
      if (f._els.some(function (e) { return e.getAttribute('aria-invalid') === 'true'; }) && !errs.length) errs.push('invalid');
      if (errs.length) f.error = errs.join(' | ');
      // A radio group whose options are file names is the resume picker.
      // Its radios carry the file name as aria-label (the question is "Currículum*" above the list).
      if (f.type === 'radio' && f._arias.length && f._arias.every(function (a) { return RESUME_RE.test(norm(a)); })) {
        f.type = 'resume';
        f.label = 'Currículum';
        var dates = f._els.map(function (e) {
          // Climb until the ancestor holds this radio only; its text is "PDF / name / d/m/yyyy".
          for (var x = e.parentElement, k = 0; x && k < 6; x = x.parentElement, k++) {
            if (x.querySelectorAll('input[type=radio]').length > 1) break;
            var m = /(\d{1,2}\/\d{1,2}\/\d{4})/.exec(text(x));
            if (m) return m[1];
          }
          return '';
        });
        f.resumes = f._arias.map(function (o, i) { return { index: i, name: o, date: dates[i], selected: f._els[i].checked }; });
        f.value = (f.resumes.filter(function (r) { return r.selected; })[0] || {}).name || null;
        delete f.options;
      }
    });
    return out;
  }
  function publicField(f) {
    var o = {};
    Object.keys(f).forEach(function (k) { if (k.charAt(0) !== '_') o[k] = f[k]; });
    return o;
  }
  // review_text without the ~60-entry resume list: "Currículum: <selected> (<date>)" instead, and the
  // values of any fields still on screen (one-page forms show inputs, whose values innerText lacks).
  // Only rows of the resume picker collapse ("PDF" / file name / d/m/yyyy right under the resume heading);
  // a cover letter or an answer that ends in .pdf stays as it is.
  var RESUME_HEAD_RE = /^(resume|curriculum|curriculum vitae|cv)$|selecciona o carga un curriculum|select or upload a resume|upload a resume/;
  var DATE_RE = /^\d{1,2}\/\d{1,2}\/\d{4}$/;
  function compactReview(t, fs) {
    var lines = String(t || '').split('\n'), out = [], seen = [], at = -1, done = false;
    function entryAt(i) {  // {name, date, next} for a picker row starting at line i, or null
      var n = norm(lines[i] || ''), j = i;
      if (/^(pdf|docx?|odt|txt)$/.test(n) && RESUME_RE.test(norm(lines[i + 1] || ''))) j = i + 1;
      else if (!(RESUME_RE.test(n) && DATE_RE.test(clean(lines[i + 1] || '')))) return null;
      var date = DATE_RE.test(clean(lines[j + 1] || '')) ? clean(lines[j + 1]) : '';
      return { name: clean(lines[j]), date: date, next: j + (date ? 2 : 1) };
    }
    function underResumeHeading(i) {
      for (var k = i - 1; k >= 0 && k >= i - 4; k--) if (RESUME_HEAD_RE.test(norm(lines[k]))) return true;
      return false;
    }
    for (var i = 0; i < lines.length;) {
      var e = !done && entryAt(i);
      if (e && (at >= 0 || underResumeHeading(i))) {
        seen.push({ name: e.name, date: e.date });
        if (at < 0) { at = out.length; out.push(''); }
        i = e.next;
        continue;
      }
      if (at >= 0) done = true;  // one run only
      out.push(lines[i]);
      i++;
    }
    var res = (fs || []).filter(function (f) { return f.type === 'resume'; })[0];
    if (at >= 0 || res) {
      var sel = res ? (res.resumes || []).filter(function (r) { return r.selected; })[0] : (seen.length === 1 ? seen[0] : null);
      var line = 'Currículum: ' + (sel ? sel.name + (sel.date ? ' (' + sel.date + ')' : '') : '(no se pudo leer cuál está elegido)') +
                 (seen.length > 1 ? ' [lista de ' + seen.length + ' CV omitida]' : '');
      if (at >= 0) out[at] = line; else out.push(line);
    }
    var vals = (fs || []).filter(function (f) { return f.type !== 'resume'; }).map(function (f) {
      var v = Array.isArray(f.value) ? f.value.join(', ') : (f.value == null ? '' : String(f.value));
      return f.label + ': ' + (v || '(vacío)');
    });
    var s = out.join('\n');
    if (vals.length) s += '\n\nValores en el formulario:\n' + vals.join('\n');
    return s;
  }
  // "Sigue a <empresa> …": a lone checkbox outside the screening questions. "Follow-up calls" is a question.
  function followBox(d) {
    return all(d, 'input[type=checkbox]').filter(function (c) {
      return !c.closest('[componentkey^="easyApplyFieldFocus"]') &&
        /^(seguir a |sigue a |follow )/.test(norm(optionText(c)) || norm(questionText(c, container(c))));
    })[0] || null;
  }
  function modalRead() {
    var success = successDialog();
    var d = appDialog();
    var res = { open: !!d, save_prompt: !!savePrompt(), success: !!success,
                success_text: success ? text(success).slice(0, 300) : '' };
    if (!d) return res;
    var t = text(d);
    var step = /(\d+)\s*\/\s*(\d+)\s*(paginas|páginas|pages?)/i.exec(t);
    var fs = fields(d);
    var buttons = all(d, 'button').filter(visible).map(label).filter(Boolean);
    var follow = followBox(d);
    res.dialog_title = text(d.querySelector('h2'));
    res.company = res.dialog_title.replace(/^(aplicar a|solicitar a|apply to)\s+/i, '');
    res.step = step ? parseInt(step[1], 10) : null;
    res.steps = step ? parseInt(step[2], 10) : null;
    res.section = text(d.querySelector('h3')) || '';
    res.fields = fs.filter(function (f) { return !(follow && f._els.length === 1 && f._els[0] === follow); }).map(publicField);
    res.button_kinds = buttons.map(buttonKind);
    res.buttons = buttons;
    res.is_review = buttons.some(function (b) { return buttonKind(b) === 'submit'; });
    res.errors = fs.filter(function (f) { return f.error; }).map(function (f) { return f.label + ': ' + f.error; });
    if (follow) res.follow_company = { label: optionText(follow), checked: follow.checked };
    if (res.is_review) res.review_text = compactReview(t, res.fields).slice(0, 6000);
    return res;
  }
  function findField(fs, key) {
    var hits = pick(fs, key, function (f) { return f.label; });
    return hits;
  }
  function modalFill(answers) {
    var d = appDialog();
    if (!d) return { status: 'no_dialog' };
    var fs = fields(d).filter(function (f) { return f.type !== 'resume'; });
    var results = {};
    Object.keys(answers).forEach(function (key) {
      var want = answers[key];
      var hits = findField(fs, key);
      if (!hits.length) { results[key] = { status: 'not_found' }; return; }
      if (hits.length > 1) { results[key] = { status: 'ambiguous', matches: hits.map(function (h) { return h.label; }) }; return; }
      var f = hits[0], el = f._els[0];
      try {
        if (f.type === 'select') {
          var opts = all(el, 'option').filter(function (o) { return clean(o.text); });
          var o = pick(opts, want, function (x) { return x.text; })[0] || opts.filter(function (x) { return x.value === String(want); })[0];
          if (!o) { results[key] = { status: 'bad_option', options: opts.map(function (x) { return clean(x.text); }) }; return; }
          setSelect(el, o);
        } else if (f.type === 'radio') {
          var i = f.options.map(norm).indexOf(norm(want));
          if (i < 0) { var ph = pick(f.options, want, function (x) { return x; }); i = ph.length === 1 ? f.options.indexOf(ph[0]) : -1; }
          if (i < 0) { results[key] = { status: 'bad_option', options: f.options }; return; }
          if (!f._els[i].checked) f._els[i].click();
        } else if (f.type === 'checkbox') {
          var wants = (Array.isArray(want) ? want : (typeof want === 'boolean' ? (want ? f.options.slice(0, 1) : []) : [want])).map(norm);
          var bad = wants.filter(function (w) { return f.options.map(norm).indexOf(w) < 0; });
          if (bad.length) { results[key] = { status: 'bad_option', options: f.options, missing: bad }; return; }
          f._els.forEach(function (e, j) { var on = wants.indexOf(norm(f.options[j])) >= 0; if (e.checked !== on) e.click(); });
        } else {
          var v = String(want == null ? '' : want);
          if (f.max_length && v.length > f.max_length) { results[key] = { status: 'too_long', max_length: f.max_length, length: v.length }; return; }
          setText(el, v);
          if (f.type === 'typeahead') { results[key] = { status: 'typed_needs_pick', label: f.label }; return; }
        }
        results[key] = { status: 'set', label: f.label };
      } catch (e) {
        results[key] = { status: 'error', message: String(e) };
      }
    });
    return { status: 'filled', results: results };
  }
  function typeaheadPick(arg) {
    var opts = all(document, '[role=listbox] [role=option], [role=option]').filter(visible);
    if (!opts.length) return { status: 'no_options' };
    var o = arg && arg.option ? pick(opts, arg.option, text)[0] : opts[0];
    if (!o) return { status: 'bad_option', options: opts.map(text).slice(0, 10) };
    o.click();
    return { status: 'picked', option: text(o) };
  }
  // Only "Listo"/"Done" (closing the confirmation). Anything else, above all a submit or "Continuar",
  // is refused before the page is even looked at.
  function modalClick(want) {
    if (buttonKind(want) !== 'done') return { status: 'label_not_allowed', label: String(want) };
    var d = successDialog() || appDialog();
    if (!d) return { status: 'no_dialog' };
    var b = all(d, 'button').filter(visible).filter(function (x) { return norm(label(x)) === norm(want); })[0];
    if (!b) return { status: 'button_not_found', buttons: all(d, 'button').filter(visible).map(label) };
    if (b.disabled || b.getAttribute('aria-disabled') === 'true') return { status: 'button_disabled', label: label(b) };
    b.click();
    return { status: 'clicked', label: label(b) };
  }
  // arg.expect: [[label, type, value], ...] of the step as planned. If the fields on screen differ (a question
  // appeared, a value changed), nothing is clicked: the caller reads and plans the step again.
  function clickNext(arg) {
    var d = appDialog();
    if (!d) return { status: 'no_dialog' };
    if (arg && arg.expect) {
      var follow = followBox(d);
      var now = fields(d).filter(function (f) { return !(follow && f._els.length === 1 && f._els[0] === follow); })
        .map(function (f) { return JSON.stringify([f.label, f.type, f.value === undefined ? null : f.value]); });
      var want = arg.expect.map(function (e) { return JSON.stringify([e[0], e[1], e[2] === undefined ? null : e[2]]); });
      if (now.join('\n') !== want.join('\n')) return { status: 'step_changed' };
    }
    var b = all(d, 'button').filter(visible).filter(function (x) { return buttonKind(x.innerText) === 'next'; })[0];
    if (!b) return { status: 'no_next_button', buttons: all(d, 'button').filter(visible).map(label) };
    if (b.disabled || b.getAttribute('aria-disabled') === 'true') return { status: 'next_disabled', label: label(b) };
    b.click();
    return { status: 'clicked', label: label(b) };
  }
  function clickSubmit() {
    var d = appDialog();
    if (!d) return { status: 'no_dialog' };
    var b = all(d, 'button').filter(visible).filter(function (x) { return buttonKind(x.innerText) === 'submit'; })[0];
    if (!b) return { status: 'no_submit_button' };
    if (b.disabled || b.getAttribute('aria-disabled') === 'true') return { status: 'button_disabled' };
    b.click();
    return { status: 'clicked', label: label(b) };
  }
  function setFollow(on) {
    var d = appDialog();
    if (!d) return { status: 'no_dialog' };
    var c = followBox(d);
    if (!c) return { status: 'no_follow_checkbox' };
    if (c.checked !== !!on) c.click();
    return { status: 'ok', checked: c.checked };
  }
  function selectResume(arg) {
    var d = appDialog();
    if (!d) return { status: 'no_dialog' };
    var f = fields(d).filter(function (x) { return x.type === 'resume'; })[0];
    if (!f) return { status: 'no_resume_step' };
    var idx = typeof arg.index === 'number' ? arg.index
      : f.resumes.map(function (r) { return norm(r.name); }).indexOf(norm(arg.name));  // first match = most recent
    if (idx < 0 || idx >= f._els.length) return { status: 'resume_not_found', resumes: f.resumes };
    if (!f._els[idx].checked) f._els[idx].click();
    return { status: 'selected', index: idx, name: f.resumes[idx].name, date: f.resumes[idx].date };
  }

  // ---------- resume upload (no native dialog) ----------
  // "Cargar currículum" builds an <input type=file>, appends it to <body> and calls click().
  // Intercept that click, keep the input, then hand it the file through DataTransfer.
  function uploadBegin() {
    var d = appDialog();
    if (!d) return { status: 'no_dialog' };
    var b = all(d, 'button').filter(visible).filter(function (x) { return /^(cargar curriculum|upload resume|cargar|upload)$/.test(norm(x.innerText)); })[0];
    if (!b) return { status: 'no_upload_button' };
    var captured = null;
    var origClick = HTMLInputElement.prototype.click, origShow = HTMLInputElement.prototype.showPicker;
    HTMLInputElement.prototype.click = function () { if (this.type === 'file') { captured = this; return; } return origClick.apply(this, arguments); };
    if (origShow) HTMLInputElement.prototype.showPicker = function () { if (this.type === 'file') { captured = this; return; } return origShow.apply(this, arguments); };
    try { b.click(); } finally {
      HTMLInputElement.prototype.click = origClick;
      if (origShow) HTMLInputElement.prototype.showPicker = origShow;
    }
    if (!captured) return { status: 'no_file_input' };
    window.__liUploadInput = captured;
    window.__liB64 = '';
    return { status: 'ready', accept: captured.accept };
  }
  function fileChunk(arg) {
    if (arg.reset) window.__liB64 = '';
    window.__liB64 = (window.__liB64 || '') + arg.data;
    return { status: 'ok', length: window.__liB64.length };
  }
  function fileCommit(arg) {
    var inp = window.__liUploadInput;
    if (!inp) return { status: 'no_file_input' };
    var bin = atob(window.__liB64 || ''), bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    var dt = new DataTransfer();
    dt.items.add(new File([bytes], arg.name, { type: arg.mime, lastModified: Date.now() }));
    inp.files = dt.files;
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));
    window.__liB64 = '';
    return { status: 'committed', files: inp.files.length };
  }

  function closeModal(arg) {
    var prompt = savePrompt();
    if (!prompt) {
      var d = appDialog() || successDialog();
      if (!d) return { status: 'no_dialog' };
      var x = d.querySelector('button[aria-label="Descartar"], button[aria-label="Dismiss"], button[aria-label="Cerrar"], button[aria-label="Close"]');
      if (!x) return { status: 'no_close_button' };
      x.click();
      return { status: 'close_clicked' };
    }
    var want = arg && arg.save ? /^(guardar|save)$/ : /^(descartar|discard)$/;
    var b = all(prompt, 'button').filter(function (x) { return want.test(norm(x.innerText)); })[0];
    if (!b) return { status: 'prompt_button_not_found' };
    b.click();
    return { status: arg && arg.save ? 'saved' : 'discarded' };
  }

  try {
    var r;
    switch (ACTION) {
      case 'page_state': r = pageState(); break;
      case 'list_jobs': r = listJobs(); break;
      case 'goto_page': r = gotoPage(ARG); break;
      case 'job_detail': r = jobDetail(); break;
      case 'open_easy_apply': r = openEasyApply(); break;
      case 'modal_read': r = modalRead(); break;
      case 'modal_fill': r = modalFill(ARG || {}); break;
      case 'typeahead_pick': r = typeaheadPick(ARG); break;
      case 'modal_click': r = modalClick(ARG); break;
      case 'click_next': r = clickNext(ARG); break;
      case 'click_submit': r = clickSubmit(); break;
      case 'set_follow': r = setFollow(ARG); break;
      case 'select_resume': r = selectResume(ARG || {}); break;
      case 'upload_begin': r = uploadBegin(); break;
      case 'file_chunk': r = fileChunk(ARG); break;
      case 'file_commit': r = fileCommit(ARG); break;
      case 'close_modal': r = closeModal(ARG); break;
      // pure helpers (no page access), exposed for the JXA tests
      case 'button_kind': r = { kind: buttonKind(ARG) }; break;
      case 'compact_review': r = { text: compactReview((ARG || {}).text, (ARG || {}).fields) }; break;
      default: r = { status: 'js_error', message: 'unknown action ' + ACTION };
    }
    return JSON.stringify(r);
  } catch (e) {
    return JSON.stringify({ status: 'js_error', message: String(e && e.stack || e) });
  }
}
