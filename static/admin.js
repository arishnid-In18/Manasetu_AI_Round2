/* MANASETU AI — administrator console. Aggregate / system data only; no case-level clinical data. */
(function () {
  'use strict';
  const MS = window.MS; const { S, html } = MS;
  const errBox = (e) => html`<div class="err" role="alert">${e.message}</div>`;
  let tab = 'users'; let auditPage = 1; let auditFilter = { action: '', outcome: '' };

  MS.route(/^\/admin(?:\/(\w+))?$/, async (t) => {
    if (!(await MS.requireStaff())) return;
    if (S.staff.user.role !== 'admin') return MS.go('/dashboard');
    if (t) tab = t;
    MS.render(MS.staffShell('admin', html`
      <h1>Administration</h1>
      <p class="muted">Manage accounts, languages, schedules, audit logs and system health. Administrators do not have access to individual responses, clinical notes or case detail.</p>
      <div class="tabs" role="tablist">${[['users', 'Accounts & roles'], ['languages', 'Languages & instrument'], ['schedule', 'Screening schedule'], ['audit', 'Audit log'], ['health', 'Health & data quality']]
        .map(([k, l]) => html`<button class="chip ${tab === k ? 'on' : ''}" role="tab" aria-selected="${tab === k}" data-act="admintab" data-t="${k}">${l}</button>`)}</div>
      <div id="admin-body"><span class="spinner"></span></div>`));
    const body = MS.$('#admin-body');
    try { body.innerHTML = (await VIEWS[tab]()).__raw; } catch (e) { body.innerHTML = errBox(e).__raw; }
  });
  MS.handlers.admintab = (el) => { tab = el.dataset.t; MS.refresh(); };

  const VIEWS = {
    async users() {
      const r = await MS.api('GET', '/api/admin/users');
      const groups = Object.keys(S.meta.profile.groups).join(', ');
      return html`<div class="cols"><div class="card"><h2>Accounts</h2><div class="tablewrap"><table><thead><tr><th>User</th><th>Role</th><th>Scope</th><th>Status</th><th></th></tr></thead>
        <tbody>${r.items.map((u) => html`<tr><td><b>${u.username}</b><div class="small muted">${u.display_name}</div></td><td>${u.role}</td><td>${u.group_scope}</td>
          <td><span class="badge ${u.account_status === 'active' ? 'b-ok' : 'b-none'}">${u.account_status}</span>${u.locked ? html` <span class="badge b-warn">locked</span>` : ''}</td>
          <td class="row">${u.locked ? html`<button class="btn sm ghost" data-act="uunlock" data-id="${u.user_id}">Unlock</button>` : ''}
            <button class="btn sm ghost" data-act="utoggle" data-id="${u.user_id}" data-s="${u.account_status === 'active' ? 'disabled' : 'active'}">${u.account_status === 'active' ? 'Disable' : 'Enable'}</button></td></tr>`)}</tbody></table></div><div id="u-msg"></div></div>
        <div class="card"><h2>Create account</h2><form data-form="ucreate" class="stack">
          <label for="nu-u">Username</label><input id="nu-u" type="text" autocapitalize="none" placeholder="lowercase letters, digits . _ -">
          <label for="nu-d">Display name</label><input id="nu-d" type="text">
          <label for="nu-r">Role</label><select id="nu-r"><option>officer</option><option>clinician</option><option>admin</option></select>
          <label for="nu-s">Scope (${groups} or *)</label><input id="nu-s" type="text" value="*">
          <label for="nu-p">Temporary password (10+ characters)</label><input id="nu-p" type="password" autocomplete="new-password">
          <div id="nu-e"></div><button class="btn primary" type="submit">Create</button></form></div></div>`;
    },
    async languages() {
      const r = await MS.api('GET', '/api/admin/languages');
      return html`<div class="card"><h2>Supported languages</h2>
        <div class="row">${r.supported.map((l) => html`<span class="badge b-ok">${l.native} \u00b7 ${l.name}</span>`)}</div>
        <p class="muted" style="margin-top:.8rem">${r.note}</p>
        <h3>Active instrument</h3>
        <div class="kvgrid"><div><div class="k">Instrument</div><div class="v">${r.instrument.title}</div></div>
          <div><div class="k">Version</div><div class="v">${r.instrument.id} v${r.instrument.version}</div></div>
          <div><div class="k">Clinically validated</div><div class="v">${r.instrument.validated ? 'Yes' : 'No \u2014 placeholder'}</div></div>
          <div><div class="k">Recall period</div><div class="v">${r.instrument.recall_period}</div></div></div>
        <div class="warn">${r.instrument.status_note}</div></div>`;
    },
    async schedule() {
      const r = await MS.api('GET', '/api/admin/config');
      const labels = { assessment_interval_days: 'Days between scheduled assessments', overdue_grace_days: 'Grace days before "Overdue"', postpone_retry_days: 'Days before re-offering after "Not now"',
        decline_retry_days: 'Days before re-offering after "Decline"', welfare_check_after_declines: 'Consecutive declines that raise an administrative welfare-check flag', stale_session_hours: 'Hours before an unfinished check-in is closed as incomplete', voice_assistant_enabled: 'Voice assistant at the kiosk (1 = on, 0 = touch only)' };
      return html`<div class="cols"><div class="card"><h2>Approved screening schedule</h2>
        <p class="muted">Changes are validated and audit-logged. These control scheduling only; they never change a person's risk category.</p>
        ${Object.entries(r.config).map(([k, v]) => html`<form data-form="cfgsave" data-k="${k}" class="row" style="margin:.5rem 0"><label style="flex:1;margin:0" for="c-${k}">${labels[k] || k}</label>
          <input id="c-${k}" type="text" inputmode="numeric" value="${v}" style="width:90px"><button class="btn sm ghost" type="submit">Save</button></form>`)}<div id="cfg-msg"></div></div>
        <div class="card"><h2>Rule set (read-only)</h2><p class="small muted">${r.rules_note}</p><pre style="white-space:pre-wrap;font-size:.8rem;background:#F5F9F7;padding:.8rem;border-radius:10px;overflow:auto">${JSON.stringify(r.rules, null, 2)}</pre></div></div>`;
    },
    async audit() {
      const qs = new URLSearchParams({ page: auditPage, page_size: 20 }); if (auditFilter.action) qs.set('action', auditFilter.action); if (auditFilter.outcome) qs.set('outcome', auditFilter.outcome);
      const r = await MS.api('GET', '/api/admin/audit?' + qs.toString());
      return html`<div class="card"><div class="row between"><h2>Audit log</h2><button class="btn sm primary" data-act="auditverify">Verify tamper-evident chain</button></div>
        <div id="chain-msg"></div>
        <div class="filters"><div><label for="a-act">Action contains</label><input id="a-act" type="text" value="${auditFilter.action}" data-input="auditaction"></div>
          <div><label for="a-out">Outcome</label><select id="a-out" data-change="auditoutcome"><option value="">All</option>${['success', 'denied', 'failure'].map((o) => html`<option ${auditFilter.outcome === o ? 'selected' : ''}>${o}</option>`)}</select></div></div>
        <div class="tablewrap"><table><thead><tr><th>#</th><th>Time</th><th>Actor</th><th>Action</th><th>Record</th><th>Outcome</th></tr></thead><tbody>
          ${r.items.map((a) => html`<tr><td>${a.audit_id}</td><td>${MS.fmtDateTime(a.ts)}</td><td>${a.actor || a.actor_type} <span class="muted small">(${a.actor_type})</span></td><td>${a.action}</td><td class="small">${a.record_type || ''} ${a.record_id || ''}</td>
            <td><span class="badge ${a.outcome === 'success' ? 'b-ok' : a.outcome === 'denied' ? 'b-urgent' : 'b-warn'}">${a.outcome}</span></td></tr>`)}</tbody></table></div>
        <div class="pager"><span class="small muted">${r.total} entries \u00b7 page ${r.page} of ${r.pages}</span>
          <button class="btn sm ghost" data-act="auditpage" data-p="${r.page - 1}" ${r.page <= 1 ? 'disabled' : ''}>Previous</button>
          <button class="btn sm ghost" data-act="auditpage" data-p="${r.page + 1}" ${r.page >= r.pages ? 'disabled' : ''}>Next</button></div>
        <p class="small muted">Scores, responses and notes are never written to the audit log. Each row's hash covers the previous row, so edits or deletions are detectable.</p></div>`;
    },
    async health() {
      const h = await MS.api('GET', '/api/admin/health');
      const stat = (n, l, cls = '') => html`<div class="stat ${cls}" style="cursor:default"><div class="n">${n}</div><div class="l">${l}</div></div>`;
      const sess = h.sessions_by_status;
      return html`<div class="grid g3">
          ${stat(h.database_ok ? 'OK' : 'DOWN', 'Database', h.database_ok ? 'routine' : 'urgent')}
          ${stat(h.audit_chain_valid ? 'Valid' : 'BROKEN', `Audit chain (${h.audit_rows} rows)`, h.audit_chain_valid ? 'routine' : 'urgent')}
          ${stat(h.active_staff_sessions, 'Active staff sessions', 'monitor')}</div>
        <div class="card" style="margin-top:1rem"><h2>Data quality</h2><div class="kvgrid">
          <div><div class="k">Registered people</div><div class="v">${h.registered_people}</div></div>
          <div><div class="k">With at least one completed assessment</div><div class="v">${h.people_with_a_completed_assessment}</div></div>
          <div><div class="k">Check-in completion rate</div><div class="v">${Math.round(h.completion_rate * 100)}%</div></div>
          <div><div class="k">Incomplete or failed check-ins</div><div class="v">${h.incomplete_or_failed} (failed: ${h.failed_sessions})</div></div>
          <div><div class="k">Answers given by voice</div><div class="v">${Math.round((h.voice_answer_share || 0) * 100)}%</div></div>
          <div><div class="k">Pending follow-ups</div><div class="v">${h.pending_follow_ups}</div></div><div><div class="k">Open referrals</div><div class="v">${h.open_referrals}</div></div></div>
          <h3 style="margin-top:1rem">Check-ins by status</h3><div class="row">${Object.entries(sess).map(([k, v]) => html`<span class="badge b-none">${k}: ${v}</span>`)}</div>
          <h3 style="margin-top:1rem">Recommendations issued (aggregate)</h3><div class="row">${Object.entries(h.recommendations).map(([k, v]) => html`<span class="badge b-none">${k}: ${v}</span>`)}</div>
          <p class="small muted">Profile: ${h.profile} \u00b7 version ${h.app_version}. ${h.case_level_access}</p></div>`;
    },
  };

  MS.handlers.ucreate = async () => {
    try { await MS.api('POST', '/api/admin/users', { username: MS.$('#nu-u').value.trim(), display_name: MS.$('#nu-d').value, role: MS.$('#nu-r').value, group_scope: MS.$('#nu-s').value, password: MS.$('#nu-p').value }, 'staff'); MS.toast('Account created'); MS.refresh(); }
    catch (e) { MS.$('#nu-e').innerHTML = errBox(e).__raw; } };
  MS.handlers.utoggle = async (el) => { try { await MS.api('PATCH', '/api/admin/users/' + el.dataset.id, { account_status: el.dataset.s }, 'staff'); MS.refresh(); } catch (e) { MS.$('#u-msg').innerHTML = errBox(e).__raw; } };
  MS.handlers.uunlock = async (el) => { try { await MS.api('PATCH', '/api/admin/users/' + el.dataset.id, { unlock: true }, 'staff'); MS.refresh(); } catch (e) { MS.$('#u-msg').innerHTML = errBox(e).__raw; } };
  MS.handlers.cfgsave = async (f) => {
    try { await MS.api('PUT', '/api/admin/config', { key: f.dataset.k, value: parseInt(MS.$('input', f).value, 10) }, 'staff'); MS.$('#cfg-msg').innerHTML = '<div class="ok">Saved and audit-logged.</div>'; }
    catch (e) { MS.$('#cfg-msg').innerHTML = errBox(e).__raw; } };
  MS.handlers.auditverify = async () => {
    const r = await MS.api('GET', '/api/admin/audit/verify');
    MS.$('#chain-msg').innerHTML = r.valid ? `<div class="ok">Chain valid \u2014 ${r.checked} entries verified.</div>` : `<div class="err">Chain broken at entry #${r.first_invalid_audit_id}.</div>`; };
  MS.handlers.auditpage = (el) => { auditPage = parseInt(el.dataset.p, 10); MS.refresh(); };
  let aT = null;
  MS.handlers.auditaction = (el) => { clearTimeout(aT); aT = setTimeout(() => { auditFilter.action = el.value.trim(); auditPage = 1; MS.refresh(); }, 400); };
  MS.handlers.auditoutcome = (el) => { auditFilter.outcome = el.value; auditPage = 1; MS.refresh(); };
})();
