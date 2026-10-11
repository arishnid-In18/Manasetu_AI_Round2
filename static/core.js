/* MANASETU AI — frontend core. No inline scripts (CSP); all dynamic text is escaped by html``. */
(function () {
  'use strict';
  const MS = (window.MS = {});
  const lsGet = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } };
  const S = (MS.S = {
    meta: null, lang: localStorage.getItem('ms_lang') || 'en', a11y: lsGet('ms_a11y', { size: 'md', hc: false }),
    kiosk: { csrf: null, profile: null, language: null, sid: null, instrument: null, responses: {}, doneKind: null, consent: null, busy: false },
    staff: { user: null, csrf: null }, ui: { pop: null }, notif: { urgent: 0, items: [] }, timedOut: false,
  });

  // ---------------------------------------------------------------- safe templating
  const raw = (MS.raw = (s) => ({ __raw: String(s) }));
  const esc = (MS.esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));
  const val = (v) => (v && v.__raw !== undefined ? v.__raw : Array.isArray(v) ? v.map(val).join('') : esc(v));
  MS.html = (strs, ...vals) => raw(strs.reduce((a, s, i) => a + s + (i < vals.length ? val(vals[i]) : ''), ''));
  const html = MS.html;
  MS.$ = (s, el = document) => el.querySelector(s);
  MS.$$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  // ---------------------------------------------------------------- i18n helpers
  MS.t = (key, vars = {}) => {
    const pack = window.I18N[S.lang] || window.I18N.en;
    let s = pack[key] ?? window.I18N.en[key] ?? key;
    if (typeof s !== 'string') return s;
    return s.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? '');
  };
  MS.tp = (key) => { const p = window.I18N[S.lang] || window.I18N.en; return p[key] || window.I18N.en[key]; };
  MS.profileStr = (k) => {
    const strs = S.meta.profile.strings; return (strs[S.lang] && strs[S.lang][k]) || strs.en[k];
  };
  MS.fmtDate = (iso) => {
    if (!iso) return '\u2014';
    const d = new Date(iso.length <= 10 ? iso + 'T00:00:00' : iso);
    return isNaN(d) ? iso : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  };
  MS.fmtDateTime = (iso) => {
    if (!iso) return '\u2014';
    const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z');
    return isNaN(d) ? iso : d.toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  };
  const PRIO = {
    'Urgent Human Review': ['b-urgent', 'Urgent Human Review'], 'Human Follow-Up Recommended': ['b-follow', 'Human Follow-Up Recommended'],
    'Monitor': ['b-monitor', 'Monitor'], 'Routine Monitoring': ['b-routine', 'Routine Monitoring'],
  };
  MS.priorityBadge = (p) => { const [c, l] = PRIO[p] || ['b-none', 'Not yet assessed']; return html`<span class="badge ${c}"><i class="dotp"></i>${l}</span>`; };

  // ---------------------------------------------------------------- API
  MS.api = async (method, url, body, kind) => {
    const headers = {}; const opts = { method, headers, credentials: 'same-origin' };
    if (body !== undefined) { headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    const csrf = kind === 'kiosk' ? S.kiosk.csrf : kind === 'staff' ? S.staff.csrf : null;
    if (csrf) headers['X-CSRF-Token'] = csrf;
    let res; try { res = await fetch(url, opts); } catch (e) { const er = new Error('Network error. Is the server running?'); er.status = 0; throw er; }
    let data = null; try { data = await res.json(); } catch (e) { /* empty */ }
    if (!res.ok) {
      let msg = 'Request failed';
      if (data && typeof data.detail === 'string') msg = data.detail;
      else if (data && Array.isArray(data.detail)) msg = data.detail.map((d) => d.msg).join('; ');
      const er = new Error(msg); er.status = res.status; throw er;
    }
    return data;
  };

  // ---------------------------------------------------------------- events (delegated)
  const handlers = (MS.handlers = {});
  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-act]'); if (!el) { closePopoverIfOutside(e); return; }
    const fn = handlers[el.dataset.act]; if (fn) { e.preventDefault(); fn(el, e); }
  });
  document.addEventListener('submit', (e) => { const f = e.target.closest('[data-form]'); if (!f) return; e.preventDefault(); const fn = handlers[f.dataset.form]; if (fn) fn(f, e); });
  document.addEventListener('change', (e) => { const el = e.target.closest('[data-change]'); if (el && handlers[el.dataset.change]) handlers[el.dataset.change](el, e); });
  document.addEventListener('input', (e) => { const el = e.target.closest('[data-input]'); if (el && handlers[el.dataset.input]) handlers[el.dataset.input](el, e); });
  ['pointerdown', 'keydown'].forEach((ev) => document.addEventListener(ev, () => resetIdle()));
  function closePopoverIfOutside(e) { if (S.ui.pop && !e.target.closest('.popover')) { S.ui.pop = null; const p = MS.$('.popover'); if (p) p.remove(); } }

  // ---------------------------------------------------------------- router
  const routes = []; MS.route = (re, fn) => routes.push([re, fn]);
  MS.go = (path) => { if (location.hash === '#' + path) MS.refresh(); else location.hash = '#' + path; };
  MS.refresh = () => route();
  MS.query = new URLSearchParams('');
  async function route() {
    const full = location.hash.slice(1) || '/';
    const [path, qs] = full.split('?');
    MS.query = new URLSearchParams(qs || '');
    for (const [re, fn] of routes) {
      const m = path.match(re);
      if (m) { try { await fn(...m.slice(1)); } catch (err) { fatal(err); } window.scrollTo(0, 0); return; }
    }
    MS.go('/');
  }
  function fatal(err) {
    if (err && err.status === 401 && location.hash.match(/#\/(dashboard|case|referrals|followups|admin)/)) { S.staff = { user: null, csrf: null }; MS.go('/staff'); return; }
    console.error(err);
    MS.render(html`<main><div class="err" role="alert">${err.message || MS.t('err')}</div><button class="btn primary" data-act="home">Home</button></main>`);
  }
  MS.render = (tpl) => {
    MS.$('#app').innerHTML = tpl.__raw; document.documentElement.lang = S.lang; MS.$('#app').dataset.view = location.hash;
    if (S.ui.pop === 'a11y') MS.$('#app').insertAdjacentHTML('beforeend', MS.popoverHtml().__raw);
  };
  MS.toast = (msg) => {
    const d = document.createElement('div'); d.className = 'toast'; d.setAttribute('role', 'status'); d.textContent = msg;
    document.body.appendChild(d); setTimeout(() => d.remove(), 3500);
  };

  // ---------------------------------------------------------------- accessibility
  function applyA11y() {
    document.documentElement.dataset.size = S.a11y.size === 'md' ? '' : S.a11y.size;
    document.body.classList.toggle('hc', !!S.a11y.hc);
    localStorage.setItem('ms_a11y', JSON.stringify(S.a11y));
  }
  handlers.a11ysize = (el) => { S.a11y.size = el.dataset.size; S.ui.pop = 'a11y'; applyA11y(); MS.refresh(); };
  handlers.a11yhc = () => { S.a11y.hc = !S.a11y.hc; S.ui.pop = 'a11y'; applyA11y(); MS.refresh(); };
  handlers.pop = (el) => { S.ui.pop = S.ui.pop === el.dataset.pop ? null : el.dataset.pop; const p = MS.$('.popover'); if (p) p.remove(); if (S.ui.pop) MS.$('#app').insertAdjacentHTML('beforeend', MS.popoverHtml().__raw); };
  MS.popoverHtml = () => html`<div class="popover" role="dialog" aria-label="${MS.t('acc_title')}">
      <h3>${MS.t('acc_title')}</h3>
      <div class="muted small">${MS.t('acc_size')}</div>
      <div class="row" style="margin:.4rem 0 .8rem">
        ${[['md', 'A'], ['lg', 'A+'], ['xl', 'A++']].map(([k, l]) => html`<button class="chip ${S.a11y.size === k ? 'on' : ''}" data-act="a11ysize" data-size="${k}" aria-pressed="${S.a11y.size === k}">${l}</button>`)}
      </div>
      <button class="chip ${S.a11y.hc ? 'on' : ''}" data-act="a11yhc" aria-pressed="${!!S.a11y.hc}">${MS.t('acc_contrast')}</button>
    </div>`;

  // ---------------------------------------------------------------- shells
  MS.logo = () => html`<img src="/static/img/logo.png" alt="" width="44" height="44">`;
  MS.kioskShell = (content, opts = {}) => html`
    <header class="topbar">
      <button class="brand" data-act="home" aria-label="MANASETU AI home">${MS.logo()}<span><div class="name">MANASETU AI</div><div class="tag">${MS.t('tagline')}</div></span></button>
      <div class="top-actions">
        <label class="small muted" for="uilang" style="margin:0" hidden>${MS.t('language')}</label>
        <select id="uilang" class="chip" data-change="uilang" aria-label="${MS.t('language')}">
          ${S.meta.languages.map((l) => html`<option value="${l.code}" ${S.lang === l.code ? 'selected' : ''}>${l.native}</option>`)}
        </select>
        <button class="chip" data-act="goprivacy">\u{1F512} ${MS.t('privacy')}</button>
        <button class="chip" data-act="pop" data-pop="a11y" aria-haspopup="dialog">\u267F ${MS.t('access')}</button>
      </div>
    </header>
    <main id="main" class="kiosk">${content}
      <p class="footer-note">${MS.t('synthetic')} \u00b7 ${S.meta.profile.identity_source}</p>
      <p class="center"><a href="#/staff" class="small">${MS.t('staff_signin')}</a></p>
    </main>`;
  handlers.home = () => { if (S.kiosk.profile) kioskReset(true); MS.go('/'); };
  handlers.goprivacy = () => MS.go('/privacy');
  handlers.uilang = (el) => { S.lang = el.value; localStorage.setItem('ms_lang', S.lang); MS.refresh(); };

  MS.staffShell = (active, content) => {
    const u = S.staff.user;
    const links = u.role === 'admin' ? [['admin', '/admin', 'Administration']]
      : [['dashboard', '/dashboard', 'Dashboard'], ['referrals', '/referrals', 'Referrals'], ['followups', '/followups', 'Follow-ups']];
    return html`
    <div id="urgent-slot">${urgentBanner()}</div>
    <header class="topbar">
      <button class="brand" data-act="staffhome" aria-label="MANASETU AI home">${MS.logo()}<span><div class="name">MANASETU AI</div><div class="tag">${MS.t('tagline')}</div></span></button>
      <nav class="nav" aria-label="Main">${links.map(([k, href, l]) => html`<a href="#${href}" class="${active === k ? 'active' : ''}">${l}</a>`)}</nav>
      <div class="top-actions"><span class="small muted">${u.display_name} \u00b7 <b>${u.role}</b></span>
        <button class="chip" data-act="pop" data-pop="a11y">\u267F</button>
        <button class="chip" data-act="signout">Sign out</button></div>
    </header>
    <main id="main">${content}
      <p class="footer-note">${S.meta.synthetic_data_notice} \u00b7 AI identifies meaningful changes. Authorized professionals review the evidence. Qualified clinicians decide the appropriate care.</p>
    </main>`;
  };
  handlers.staffhome = () => MS.go(S.staff.user.role === 'admin' ? '/admin' : '/dashboard');
  handlers.signout = async () => {
    try { await MS.api('POST', '/api/auth/logout', {}, 'staff'); } catch (e) { /* ignore */ }
    S.staff = { user: null, csrf: null }; stopPolling(); MS.go('/staff');
  };

  function urgentBanner() {
    if (!S.staff.user || S.staff.user.role === 'admin' || !S.notif.urgent) return html``;
    const ids = S.notif.items.filter((i) => i.kind === 'urgent_review').slice(0, 4);
    return html`<div class="urgent-banner" role="alert"><span><b>${S.notif.urgent}</b> case(s) need urgent human review \u2014 follow the facility's approved emergency or clinical protocol.
      ${ids.map((i) => html` <a href="#/case/${i.person_id}">${i.person_id}</a>`)}</span>
      <a class="btn sm" href="#/dashboard?priority=urgent">View urgent cases</a></div>`;
  }
  let pollTimer = null;
  MS.refreshNotifications = async () => {
    if (!S.staff.user || S.staff.user.role === 'admin') return;
    try { const n = await MS.api('GET', '/api/notifications'); S.notif = { urgent: n.urgent_count, items: n.items };
      const slot = MS.$('#urgent-slot'); if (slot) slot.innerHTML = urgentBanner().__raw; } catch (e) { /* ignore */ }
  };
  function startPolling() { stopPolling(); pollTimer = setInterval(MS.refreshNotifications, 30000); }
  function stopPolling() { if (pollTimer) clearInterval(pollTimer); pollTimer = null; S.notif = { urgent: 0, items: [] }; }
  MS.startPolling = startPolling;

  // ---------------------------------------------------------------- kiosk session housekeeping
  function kioskReset(callServer) {
    if (MS.voiceReset) MS.voiceReset();
    if (callServer && S.kiosk.csrf) MS.api('POST', '/api/kiosk/end', {}, 'kiosk').catch(() => {});
    S.kiosk = { csrf: null, profile: null, language: null, sid: null, instrument: null, responses: {}, doneKind: null, consent: null, busy: false };
  }
  MS.kioskReset = kioskReset;
  let idleTimer = null;
  function resetIdle() {
    if (idleTimer) clearTimeout(idleTimer);
    if (!S.kiosk.profile) return;
    idleTimer = setTimeout(() => { if (S.kiosk.profile) { kioskReset(true); S.timedOut = true; MS.go('/'); } }, 5 * 60 * 1000);
  }
  MS.resetIdle = resetIdle;
  MS.featureVoice = () => !!(S.meta && S.meta.features && S.meta.features.voice_assistant);

  MS.ensureKiosk = async () => {
    if (S.kiosk.profile) return true;
    try {
      const me = await MS.api('GET', '/api/kiosk/me');
      S.kiosk.csrf = me.csrf_token; S.kiosk.profile = me.profile; S.kiosk.language = me.language;
      if (S.kiosk.language && !localStorage.getItem('ms_lang')) S.lang = S.kiosk.language;
      return true;
    } catch (e) { MS.go('/id'); return false; }
  };
  MS.requireStaff = async () => {
    if (S.staff.user) return true;
    try { const me = await MS.api('GET', '/api/auth/me'); S.staff = { user: me.user, csrf: me.csrf_token }; startPolling(); return true; }
    catch (e) { MS.go('/staff'); return false; }
  };

  // ---------------------------------------------------------------- boot
  MS.boot = async () => {
    applyA11y();
    try { S.meta = await MS.api('GET', '/api/meta'); }
    catch (e) { document.getElementById('app').innerHTML = '<main><div class="err">Cannot reach the MANASETU AI server. Start it with run.ps1 and reload.</div></main>'; return; }
    // quietly restore any existing sessions after a page reload (no 401 noise: /api/session always answers 200)
    try {
      const ss = await MS.api('GET', '/api/session');
      if (ss.staff) { S.staff = { user: ss.staff.user, csrf: ss.staff.csrf_token }; startPolling(); MS.refreshNotifications(); }
      if (ss.kiosk) { const me = await MS.api('GET', '/api/kiosk/me'); S.kiosk.csrf = me.csrf_token; S.kiosk.profile = me.profile; S.kiosk.language = me.language; resetIdle(); }
    } catch (e) { /* none */ }
    window.addEventListener('hashchange', route);
    route();
  };
})();
