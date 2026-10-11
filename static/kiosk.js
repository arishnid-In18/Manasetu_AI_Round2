/* MANASETU AI — kiosk (person-facing) views. */
(function () {
  'use strict';
  const MS = window.MS;
  const { S, html } = MS;
  const T = (...a) => MS.t(...a);
  const langObj = (code) => S.meta.languages.find((l) => l.code === code) || { native: code };

  // ------------------------------------------------------------ landing
  MS.route(/^\/$/, async () => {
    const note = S.timedOut ? html`<div class="note" role="status">${T('timed_out')}</div>` : html``;
    S.timedOut = false;
    MS.render(MS.kioskShell(html`${note}
      <section class="hero">
        <div class="stack">
          <h1>${T('landing_h1')}</h1>
          <p class="lead">${T('landing_lead')}</p>
          <div class="row"><button class="btn primary" data-act="begin">${T('begin')}</button>
            <button class="btn ghost" data-act="goprivacy">${T('learn_privacy')}</button></div>
        </div>
        <img src="/static/img/hero.png" alt="" width="640" height="420">
      </section>
      <section class="grid g3" aria-label="Features">
        ${[['\u{1F331}', 'f1'], ['\u{1F6E1}\uFE0F', 'f2'], ['\u{1F91D}', 'f3']].map(([ic, k]) => html`
          <div class="card feature"><div class="ico" aria-hidden="true">${ic}</div><h3>${T(k + '_t')}</h3><p class="muted">${T(k + '_d')}</p></div>`)}
      </section>
      `));
  });
  MS.handlers.begin = () => MS.go(S.kiosk.profile ? '/choose' : '/id');

  // ------------------------------------------------------------ privacy (public)
  MS.route(/^\/privacy$/, async () => {
    const c = await MS.api('GET', '/api/public/privacy?lang=' + S.lang);
    MS.render(MS.kioskShell(html`
      <div class="card"><h2>${c.title}</h2><div class="note">${c.pending_review_note}</div>
        ${c.sections.map((s) => html`<div class="consent-sec"><h3>${s.heading}</h3><p>${s.body}</p></div>`)}
        <button class="btn primary" data-act="home">${T('back')}</button></div>`));
  });

  // ------------------------------------------------------------ ID authentication + profile card
  MS.route(/^\/id$/, async () => {
    const p = S.kiosk.profile;
    const prof = S.meta.profile;
    if (p) return renderProfile();
    MS.render(MS.kioskShell(html`
      <div class="card stack" style="max-width:560px;margin:1rem auto">
        <h1 class="center">${T('id_title')}</h1>
        <p class="center muted">${MS.profileStr('id_prompt')}</p>
        <form data-form="idsubmit" novalidate>
          <label for="pid">${MS.profileStr('id_label')}</label>
          <input id="pid" class="big" type="text" inputmode="text" autocomplete="off" autocapitalize="characters" maxlength="24"
                 placeholder="${MS.profileStr('id_placeholder')}" aria-describedby="id-error" autofocus>
          <div id="id-error" role="alert"></div>
          <button class="btn primary" style="width:100%;margin-top:1rem" id="idbtn" type="submit">${T('cont')}</button>
        </form>
        <p class="small muted center">${T('source')}: ${prof.identity_source}</p>
      </div>`));
    const el = MS.$('#pid'); if (el) el.focus();
  });
  MS.handlers.idsubmit = async () => {
    const v = MS.$('#pid').value.trim();
    const btn = MS.$('#idbtn'); const errBox = MS.$('#id-error'); errBox.innerHTML = '';
    if (!v) { errBox.innerHTML = html`<div class="err">${MS.profileStr('id_prompt')}</div>`.__raw; return; }
    btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> ' + MS.esc(T('checking'));
    try {
      const r = await MS.api('POST', '/api/kiosk/lookup', { person_id: v });
      S.kiosk = Object.assign(S.kiosk, { csrf: r.csrf_token, profile: r.profile, language: r.language, sid: null, instrument: null, responses: {}, doneKind: null });
      if (S.meta.languages.some((l) => l.code === r.profile.language)) { S.lang = r.profile.language; localStorage.setItem('ms_lang', S.lang); }
      MS.resetIdle(); MS.refresh();
    } catch (e) {
      btn.disabled = false; btn.textContent = T('cont');
      errBox.innerHTML = html`<div class="err">${e.status === 429 ? e.message : e.message}</div>`.__raw;
    }
  };
  function renderProfile() {
    const p = S.kiosk.profile;
    MS.render(MS.kioskShell(html`
      <div class="card profile" style="max-width:640px;margin:1rem auto;flex-wrap:wrap">
        <img src="${p.photo_url}" alt="Synthetic profile illustration" width="112" height="112">
        <div class="stack" style="flex:1;min-width:240px">
          <div class="pname">${p.display_name}</div>
          <dl class="kv">
            <dt>${MS.profileStr('id_label')}</dt><dd>${p.person_id}</dd>
            <dt>${MS.profileStr('group')}</dt><dd>${p.group_name}</dd>
            <dt>${T('lbl_lang')}</dt><dd>${langObj(p.language).native}</dd>
            <dt>${T('lbl_status')}</dt><dd>${(T('status') || {})[p.check_in_status] || p.check_in_status}</dd>
          </dl>
          <div class="verified">\u2714 ${T('verified')}</div>
          <div class="small muted">${T('source')}: ${p.identity_source}</div>
        </div>
      </div>
      <div class="row" style="justify-content:center;margin-top:1rem">
        <button class="btn primary" data-act="confirmme">${T('this_is_me')}</button>
        <button class="btn grey" data-act="notme">${T('not_me')}</button>
      </div>`));
  }
  MS.handlers.confirmme = () => MS.go('/choose');
  MS.handlers.notme = () => { MS.kioskReset(true); MS.refresh(); };

  // ------------------------------------------------------------ Yes / Not now / No
  MS.route(/^\/choose$/, async () => {
    if (!(await MS.ensureKiosk())) return;
    const p = S.kiosk.profile;
    MS.render(MS.kioskShell(html`
      <div class="stack" style="max-width:720px;margin:0 auto">
        <p class="center muted">${p.display_name} \u00b7 ${p.person_id}</p>
        <h1 class="center">${T('choose_title')}</h1>
        <div class="row" style="justify-content:center"><button class="chip" data-act="readpage" data-what="choose">\u{1F50A} ${T('read_page')}</button>
          ${MS.featureVoice && MS.featureVoice() ? html`<button class="chip" data-act="voicechoose">\u{1F399} ${T('voice_choose')}</button>` : ''}</div>
        <div id="choose-error" role="alert"></div>
        <button class="btn xl primary" data-act="intent" data-d="yes"><span aria-hidden="true" style="font-size:2rem">\u2714</span><span>${T('yes_t')}<br><small style="font-weight:500;opacity:.85">${T('yes_d')}</small></span></button>
        <button class="btn xl blue" data-act="intent" data-d="not_now"><span aria-hidden="true" style="font-size:2rem">\u23F0</span><span>${T('notnow_t')}<br><small style="font-weight:500;opacity:.85">${T('notnow_d')}</small></span></button>
        <button class="btn xl grey" data-act="intent" data-d="no"><span aria-hidden="true" style="font-size:2rem">\u2716</span><span>${T('no_t')}<br><small style="font-weight:500;opacity:.85">${T('no_d')}</small></span></button>
      </div>`));
  });
  MS.handlers.intent = async (el) => {
    const d = el.dataset.d;
    MS.$$('.btn.xl').forEach((b) => (b.disabled = true));
    try {
      const r = await MS.api('POST', '/api/kiosk/intent', { decision: d }, 'kiosk');
      if (d === 'yes') return MS.go('/language');
      MS.kioskReset(true); S.kiosk.doneKind = r.status === 'postponed' ? 'postponed' : 'declined'; MS.go('/done');
    } catch (e) { MS.$$('.btn.xl').forEach((b) => (b.disabled = false)); MS.$('#choose-error').innerHTML = html`<div class="err">${e.message}</div>`.__raw; }
  };

  // ------------------------------------------------------------ language
  MS.route(/^\/language$/, async () => {
    if (!(await MS.ensureKiosk())) return;
    const cur = S.kiosk.language || S.lang;
    MS.render(MS.kioskShell(html`
      <div class="stack" style="max-width:760px;margin:0 auto">
        <h1 class="center">${T('lang_title')}</h1>
        <div class="langgrid" role="radiogroup" aria-label="${T('lang_title')}">
          ${S.meta.languages.map((l) => { const ok = S.meta.instrument.languages.includes(l.code); return html`<button class="langcard" role="radio" aria-checked="${cur === l.code}" data-act="picklang" data-code="${l.code}" ${ok ? '' : 'disabled aria-disabled="true" style="opacity:.5;cursor:not-allowed"'}>${l.native}<small>${ok ? l.name : T('lang_unavailable')}</small></button>`; })}
        </div>
        <p class="center muted">${T('lang_note')}</p>
        <div id="lang-error" role="alert"></div>
        <div class="row" style="justify-content:center"><button class="btn primary" data-act="langcontinue">${T('cont')}</button>
          <button class="btn grey" data-act="tochoose">${T('back')}</button></div>
      </div>`));
  });
  MS.handlers.picklang = (el) => { if (el.disabled) return; S.kiosk.language = el.dataset.code; S.lang = el.dataset.code; localStorage.setItem('ms_lang', S.lang); MS.refresh(); };
  MS.handlers.tochoose = () => MS.go('/choose');
  MS.handlers.langcontinue = async () => {
    try { await MS.api('POST', '/api/kiosk/language', { language: S.kiosk.language || S.lang }, 'kiosk'); S.kiosk.consent = null; MS.go('/consent'); }
    catch (e) { MS.$('#lang-error').innerHTML = html`<div class="err">${e.message}</div>`.__raw; }
  };

  // ------------------------------------------------------------ consent & privacy
  MS.route(/^\/consent$/, async () => {
    if (!(await MS.ensureKiosk())) return;
    S.lang = S.kiosk.language || S.lang;
    const c = await MS.api('GET', '/api/kiosk/consent');
    S.kiosk.consent = c;
    MS.render(MS.kioskShell(html`
      <div class="card">
        <h1>${c.title}</h1>
        <div class="row"><button class="chip" data-act="readpage" data-what="consent">\u{1F50A} ${T('read_page')}</button></div>
        <div class="warn">${T('demo_wording')}: ${c.pending_review_note}</div>
        ${c.sections.map((s) => html`<div class="consent-sec"><h3>${s.heading}</h3><p>${s.body}</p></div>`)}
        <h3 style="margin-top:1rem">${T('ack_prompt')}</h3>
        ${c.acknowledgements.map((a) => html`<label class="ack"><input type="checkbox" data-change="ackchg" value="${a.id}"><span>${a.text}</span></label>`)}
        <div id="consent-error" role="alert"></div>
        <div class="row" style="margin-top:1rem">
          <button class="btn primary" id="consent-go" data-act="consentgo" disabled>${T('cont')}</button>
          <button class="btn ghost" data-act="readagain">${T('read_again')}</button>
          <button class="btn grey" data-act="tochoose">${T('return')}</button>
        </div>
        <p style="margin-top:1rem"><button class="btn blue" data-act="askstaff">${T('ask_staff')}</button></p>
      </div>`));
  });
  MS.handlers.ackchg = () => { MS.$('#consent-go').disabled = !MS.$$('input[data-change="ackchg"]').every((i) => i.checked); };
  MS.handlers.readagain = () => { MS.$$('input[data-change="ackchg"]').forEach((i) => (i.checked = false)); MS.handlers.ackchg(); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  MS.handlers.askstaff = async () => {
    try { await MS.api('POST', '/api/kiosk/consent', { acknowledged: [], staff_assistance: true }, 'kiosk');
      MS.kioskReset(true); S.kiosk.doneKind = 'staff_assist'; MS.go('/done'); }
    catch (e) { MS.$('#consent-error').innerHTML = html`<div class="err">${e.message}</div>`.__raw; }
  };
  MS.handlers.consentgo = async () => {
    const btn = MS.$('#consent-go'); btn.disabled = true;
    try {
      const ids = MS.$$('input[data-change="ackchg"]').filter((i) => i.checked).map((i) => i.value);
      await MS.api('POST', '/api/kiosk/consent', { acknowledged: ids }, 'kiosk');
      const s = await MS.api('POST', '/api/kiosk/session/start', undefined, 'kiosk');
      S.kiosk.sid = s.screening_id; S.kiosk.instrument = s.instrument; S.kiosk.responses = s.responses || {};
      const first = s.instrument.items.findIndex((it) => !S.kiosk.responses[it.id]);
      MS.go('/q/' + (first === -1 ? 1 : first + 1));
    } catch (e) { btn.disabled = false; MS.$('#consent-error').innerHTML = html`<div class="err">${e.message}</div>`.__raw; }
  };

  async function ensureSession() {
    if (S.kiosk.sid && S.kiosk.instrument) return true;
    try {
      const s = await MS.api('POST', '/api/kiosk/session/start', undefined, 'kiosk');
      S.kiosk.sid = s.screening_id; S.kiosk.instrument = s.instrument; S.kiosk.responses = s.responses || {}; return true;
    } catch (e) { MS.go('/consent'); return false; }
  }

  // ------------------------------------------------------------ questionnaire
  MS.route(/^\/q\/(\d+)$/, async (n) => {
    if (!(await MS.ensureKiosk()) || !(await ensureSession())) return;
    const inst = S.kiosk.instrument; const idx = Math.min(Math.max(parseInt(n, 10) - 1, 0), inst.items.length - 1);
    const item = inst.items[idx]; const r = S.kiosk.responses[item.id];
    const done = inst.items.filter((it) => S.kiosk.responses[it.id]).length;
    MS.render(MS.kioskShell(html`
      <div class="card stack">
        <div class="row between"><span class="muted">${T('q_of', { n: idx + 1, t: inst.items.length })}</span>${S.meta.instrument.validated ? '' : html`<span class="demo-banner">${T('demo_notice')}</span>`}</div>
        <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="${inst.items.length}" aria-valuenow="${done}"><i style="width:${(done / inst.items.length) * 100}%"></i></div>
        ${inst.stem ? html`<p class="muted" style="margin:.8rem 0 0">${inst.stem}</p>` : ''}
        <p class="qtext" id="qtext">${item.text}</p>
        <div class="row"><button class="chip" data-act="speak">\u{1F50A} ${T('read_aloud')}</button></div>
        ${MS.voicePanel ? MS.voicePanel() : ''}
        <div class="opts" role="radiogroup" aria-labelledby="qtext">
          ${inst.options.map((o) => html`<button class="opt" role="radio" aria-checked="${!!r && !r.skipped && r.value === o.value}" data-act="answer" data-v="${o.value}"><span class="dot"></span>${o.label}</button>`)}
          <button class="opt opt-skip" role="radio" aria-checked="${!!r && r.skipped}" data-act="skipq">${T('skip')}</button>
        </div>
        <div id="q-error" role="alert"></div>
        <div class="row between">
          <button class="btn ghost" data-act="qprev" data-i="${idx}" ${idx === 0 ? 'disabled' : ''}>\u2190 ${T('prev')}</button>
          <button class="btn primary" data-act="qnext" data-i="${idx}" ${r ? '' : 'disabled'}>${idx === inst.items.length - 1 ? T('review_title') : T('next')} \u2192</button>
        </div>
        <p class="center"><button class="chip" data-act="savelater">${T('save_later')}</button></p>
      </div>`));
    if (MS.voiceAfterRender) MS.voiceAfterRender(idx);
  });
  async function saveAnswer(idx, body) {
    if (MS.voiceOnTouch) MS.voiceOnTouch();
    const inst = S.kiosk.instrument; const item = inst.items[idx];
    try {
      await MS.api('PUT', `/api/kiosk/session/${S.kiosk.sid}/responses`, { question_id: item.id, ...body }, 'kiosk');
      S.kiosk.responses[item.id] = body.skipped ? { value: null, skipped: true } : { value: body.value, skipped: false };
      MS.refresh();
    } catch (e) { MS.$('#q-error').innerHTML = html`<div class="err">${e.message}</div>`.__raw; }
  }
  const curIdx = () => parseInt((location.hash.match(/\/q\/(\d+)/) || [0, 1])[1], 10) - 1;
  MS.handlers.answer = (el) => saveAnswer(curIdx(), { value: parseInt(el.dataset.v, 10), skipped: false });
  MS.handlers.skipq = () => saveAnswer(curIdx(), { value: null, skipped: true });
  MS.handlers.qprev = (el) => MS.go('/q/' + parseInt(el.dataset.i, 10));
  MS.handlers.qnext = (el) => {
    const i = parseInt(el.dataset.i, 10); const last = i === S.kiosk.instrument.items.length - 1;
    MS.go(last ? '/review' : '/q/' + (i + 2));
  };
  MS.handlers.speak = () => {
    if (!('speechSynthesis' in window)) return MS.toast(T('tts_unavailable'));
    const lang = { ta: 'ta-IN', hi: 'hi-IN', en: 'en-IN' }[S.kiosk.language || S.lang] || 'en-IN';
    const voices = window.speechSynthesis.getVoices();
    if (voices.length && !voices.some((v) => v.lang.toLowerCase().startsWith(lang.slice(0, 2)))) return MS.toast(T('tts_unavailable'));
    const inst = S.kiosk.instrument; const item = inst.items[curIdx()];
    const u = new SpeechSynthesisUtterance((inst.stem ? inst.stem + ' ' : '') + item.text + '. ' + inst.options.map((o) => o.label).join(', '));
    u.lang = lang; u.rate = 0.9; window.speechSynthesis.cancel(); window.speechSynthesis.speak(u);
  };
  MS.handlers.savelater = async () => {
    try { await MS.api('POST', `/api/kiosk/session/${S.kiosk.sid}/save-exit`, {}, 'kiosk'); MS.kioskReset(false); S.kiosk.doneKind = 'saved'; MS.go('/done'); }
    catch (e) { MS.$('#q-error').innerHTML = html`<div class="err">${e.message}</div>`.__raw; }
  };

  // ------------------------------------------------------------ review & submit
  MS.route(/^\/review$/, async () => {
    if (!(await MS.ensureKiosk()) || !(await ensureSession())) return;
    // refresh from the server so the review always shows what is actually saved
    const srv = await MS.api('GET', `/api/kiosk/session/${S.kiosk.sid}`);
    S.kiosk.responses = srv.responses;
    const inst = S.kiosk.instrument; const R = S.kiosk.responses;
    const label = (it) => { const r = R[it.id]; if (!r) return null; if (r.skipped) return 'skip'; return (inst.options.find((o) => o.value === r.value) || {}).label; };
    const missing = inst.items.filter((it) => !R[it.id]);
    const skipped = inst.items.filter((it) => R[it.id] && R[it.id].skipped).length;
    MS.render(MS.kioskShell(html`
      <div class="card">
        <h1>${T('review_title')}</h1><p class="muted">${T('review_sub')}</p>
        ${inst.items.map((it, i) => { const l = label(it); return html`
          <div class="review-row"><div><div class="small muted">${T('q_of', { n: i + 1, t: inst.items.length })}</div><div>${it.text}</div></div>
            <div class="row" style="flex:none"><span class="a ${l ? (l === 'skip' ? 'none' : '') : 'none'}">${l === 'skip' ? T('skipped_ans') : l || T('not_answered')}</span>
              <button class="btn sm ghost" data-act="gotoq" data-i="${i + 1}">${T('change')}</button></div></div>`; })}
        ${missing.length ? html`<div class="warn" role="alert">${T('need_all')}</div>` : skipped ? html`<div class="warn">${T('skipped_warn', { n: skipped })}</div>` : html``}
        <div id="sub-error" role="alert"></div>
        <div class="row" style="margin-top:1rem"><button class="btn primary" id="submitbtn" data-act="submit" ${missing.length ? 'disabled' : ''}>${T('submit')}</button>
          <button class="btn grey" data-act="gotoq" data-i="1">${T('prev')}</button></div>
      </div>`));
    if (MS.voiceReview) MS.voiceReview();
  });
  MS.handlers.gotoq = (el) => MS.go('/q/' + el.dataset.i);
  MS.handlers.submit = async () => {
    if (S.kiosk.busy) return; S.kiosk.busy = true;
    const btn = MS.$('#submitbtn'); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> ' + MS.esc(T('submitting'));
    try {
      const out = await MS.api('POST', `/api/kiosk/session/${S.kiosk.sid}/submit`, {}, 'kiosk');
      MS.kioskReset(true); S.kiosk.doneKind = out.status === 'completed' ? 'completed' : 'partial'; MS.go('/done');
    } catch (e) {
      S.kiosk.busy = false; btn.disabled = false; btn.textContent = T('submit');
      MS.$('#sub-error').innerHTML = html`<div class="err">${e.message}</div>`.__raw;
    }
  };

  // ------------------------------------------------------------ completion
  let doneTimer = null;
  MS.route(/^\/done$/, async () => {
    const k = S.kiosk.doneKind || 'completed';
    const msg = { completed: T('done_completed'), partial: T('done_partial'), saved: T('done_saved'),
                  postponed: T('postponed_msg'), declined: T('declined_msg'), staff_assist: T('staff_assist') }[k];
    MS.render(MS.kioskShell(html`
      <div class="card tint center stack" style="max-width:680px;margin:1rem auto;padding:2rem">
        <div style="font-size:3rem" aria-hidden="true">${k === 'completed' ? '\u{1F33F}' : '\u{1F91D}'}</div>
        <h2>${msg}</h2>
        <p class="muted">${T('done_help')}</p>
        <button class="btn primary" data-act="finishdone" style="margin:0 auto">${T('finish')}</button>
      </div>`));
    clearTimeout(doneTimer); doneTimer = setTimeout(() => { if (location.hash === '#/done') { S.kiosk.doneKind = null; MS.go('/'); } }, 30000);
  });
  MS.handlers.finishdone = () => { S.kiosk.doneKind = null; MS.go('/'); };
})();
