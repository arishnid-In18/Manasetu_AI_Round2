/* MANASETU AI — officer / clinician views. */
(function () {
  'use strict';
  const MS = window.MS; const { S, html, raw } = MS;
  const D = (iso) => MS.fmtDate(iso);
  const errBox = (e) => html`<div class="err" role="alert">${e.message}</div>`;
  const GROUP = () => S.meta.profile.group_label;

  // ------------------------------------------------------------ staff sign-in
  MS.route(/^\/staff$/, async () => {
    if (S.staff.user) return MS.go(S.staff.user.role === 'admin' ? '/admin' : '/dashboard');
    MS.render(MS.kioskShell(html`
      <div class="card stack" style="max-width:480px;margin:1rem auto">
        <h1>Staff sign-in</h1>
        <p class="muted">Authorized screening officers, clinicians and administrators only. Every sign-in and record access is audit-logged.</p>
        <form data-form="stafflogin" novalidate>
          <label for="u">Username</label><input id="u" type="text" autocomplete="username" autocapitalize="none" required>
          <label for="p">Password</label><input id="p" type="password" autocomplete="current-password" required>
          <div id="login-error" role="alert"></div>
          <button class="btn primary" style="width:100%;margin-top:1rem" id="loginbtn" type="submit">Sign in</button>
        </form>
        <div class="note small">Prototype accounts (synthetic): <b>officer1</b>, <b>officer2</b>, <b>clinician1</b>, <b>clinician2</b>, <b>admin1</b>. Demo passwords are listed in README.md.</div>
        <a href="#/" class="small">\u2190 Back to the check-in kiosk</a>
      </div>`));
  });
  MS.handlers.stafflogin = async () => {
    const b = MS.$('#loginbtn'); b.disabled = true; MS.$('#login-error').innerHTML = '';
    try {
      const r = await MS.api('POST', '/api/auth/login', { username: MS.$('#u').value, password: MS.$('#p').value });
      S.staff = { user: r.user, csrf: r.csrf_token }; MS.startPolling(); MS.refreshNotifications();
      MS.go(r.user.role === 'admin' ? '/admin' : '/dashboard');
    } catch (e) { b.disabled = false; MS.$('#login-error').innerHTML = errBox(e).__raw; }
  };

  // ------------------------------------------------------------ dashboard
  const DF = { search: '', group: '', priority: '', review_status: '', due: '', sort: 'priority', order: 'desc', page: 1 };
  const PRIO_Q = { urgent: 'Urgent Human Review', follow: 'Human Follow-Up Recommended', monitor: 'Monitor', routine: 'Routine Monitoring' };
  MS.route(/^\/dashboard$/, async () => {
    if (!(await MS.requireStaff())) return;
    if (S.staff.user.role === 'admin') return MS.go('/admin');
    const q = MS.query.get('priority'); if (q && PRIO_Q[q]) { Object.assign(DF, { priority: PRIO_Q[q], page: 1 }); }
    const groups = S.meta.profile.groups;
    MS.render(MS.staffShell('dashboard', html`
      <div class="row between"><div><h1>Mental Health Support Dashboard</h1>
        <p class="muted">Identify meaningful changes. Review evidence. Coordinate appropriate support.</p></div>
        <div class="small muted">${S.staff.user.role === 'officer' ? 'Officer view \u2014 detail limited to your role' : 'Clinician view'} \u00b7 scope: ${S.staff.user.group_scope === '*' ? 'all' : S.staff.user.group_scope}</div></div>
      <div id="dash-summary"></div>
      <div class="card" style="margin-top:1rem">
        <div class="filters">
          <div><label for="f-search">Search ID</label><input id="f-search" type="text" data-input="dfsearch" value="${DF.search}" placeholder="${S.meta.profile.id_example}"></div>
          <div><label for="f-group">${GROUP()}</label><select id="f-group" data-change="dffilter" data-k="group"><option value="">All</option>
            ${Object.entries(groups).map(([k, v]) => html`<option value="${k}" ${DF.group === k ? 'selected' : ''}>${v}</option>`)}</select></div>
          <div><label for="f-prio">Support priority</label><select id="f-prio" data-change="dffilter" data-k="priority"><option value="">All</option>
            ${[...Object.values(PRIO_Q), 'Not yet assessed'].map((p) => html`<option ${DF.priority === p ? 'selected' : ''}>${p}</option>`)}</select></div>
          <div><label for="f-rev">Review status</label><select id="f-rev" data-change="dffilter" data-k="review_status"><option value="">All</option>
            ${['pending', 'reviewed'].map((p) => html`<option value="${p}" ${DF.review_status === p ? 'selected' : ''}>${p}</option>`)}</select></div>
          <div><label for="f-due">Check-in status</label><select id="f-due" data-change="dffilter" data-k="due"><option value="">All</option>
            ${['Up to date', 'Due', 'Overdue', 'Incomplete', 'Postponed', 'Declined', 'In progress'].map((p) => html`<option ${DF.due === p ? 'selected' : ''}>${p}</option>`)}</select></div>
          <div style="flex:none"><button class="btn sm ghost" data-act="dfreset">Reset</button></div>
        </div>
        <div id="dash-table"><span class="spinner"></span></div>
      </div>`));
    loadDash();
  });
  async function loadDash() {
    const qs = new URLSearchParams(); Object.entries(DF).forEach(([k, v]) => { if (v !== '' && v !== null) qs.set(k, v); });
    qs.set('page_size', 12);
    try {
      const d = await MS.api('GET', '/api/dashboard?' + qs.toString());
      const s = d.summary;
      const card = (cls, n, label, act, extra = '') => html`<button class="stat ${cls}" data-act="${act}" ${raw(extra)}><div class="n">${n}</div><div class="l">${label}</div></button>`;
      const sum = MS.$('#dash-summary'); if (!sum) return;
      sum.innerHTML = html`
        <div class="grid g6">
          ${card('urgent', s.urgent, 'Cases Requiring Urgent Human Review', 'dfprio', 'data-p="Urgent Human Review"')}
          ${card('follow', s.follow_up, 'Human Follow-Up Recommended', 'dfprio', 'data-p="Human Follow-Up Recommended"')}
          ${card('monitor', s.monitor, 'Cases to Monitor', 'dfprio', 'data-p="Monitor"')}
          ${card('routine', s.routine, 'Routine Monitoring', 'dfprio', 'data-p="Routine Monitoring"')}
          ${card('pend', s.follow_ups_pending, 'Follow-ups Pending', 'tofollow')}
          ${card('due', s.assessments_due, 'Assessments Due', 'dfdue', 'data-d="Due"')}
        </div>
        <p class="small muted" style="margin:.6rem .2rem">${s.unreviewed_flagged} flagged case(s) awaiting human review \u00b7 ${s.unassessed} not yet assessed \u00b7
          ${s.welfare_checks_suggested} administrative welfare check(s) suggested after repeated declines (not a distress inference) \u00b7 ${s.total_in_scope} in your scope</p>`.__raw;
      const th = (k, l) => html`<th scope="col" aria-sort="${DF.sort === k ? (DF.order === 'asc' ? 'ascending' : 'descending') : 'none'}"><button data-act="dfsort" data-k="${k}">${l}${DF.sort === k ? (DF.order === 'asc' ? ' \u25B2' : ' \u25BC') : ''}</button></th>`;
      MS.$('#dash-table').innerHTML = html`
        <div class="tablewrap"><table>
          <thead><tr>${th('person_id', 'Case / ID')}${th('group_code', GROUP())}${th('latest_assessment_date', 'Latest assessment')}${th('trend', 'Trend')}${th('priority', 'Support priority')}
            <th scope="col">Review status</th><th scope="col">Assigned professional</th>${th('next_follow_up', 'Next follow-up')}${th('due_status', 'Check-in status')}</tr></thead>
          <tbody>${d.rows.length ? d.rows.map((r) => html`<tr class="click" data-act="opencase" data-id="${r.person_id}" tabindex="0" role="link" aria-label="Open case ${r.person_id}">
            <td><b>${r.person_id}</b></td><td>${r.group_code}</td><td>${D(r.latest_assessment_date)}</td><td>${r.trend || '\u2014'}</td>
            <td>${MS.priorityBadge(r.priority)}${r.unacknowledged_urgent ? html` <span class="badge b-urgent">ALERT</span>` : ''}</td>
            <td>${r.review_status ? html`<span class="badge ${r.review_status === 'reviewed' ? 'b-ok' : 'b-warn'}">${r.review_status}</span>` : '\u2014'}</td>
            <td>${(r.assigned_professional || '').split(' (')[0] || '\u2014'}</td><td>${D(r.next_follow_up)}</td>
            <td><span class="badge ${['Due', 'Overdue', 'Incomplete'].includes(r.due_status) ? 'b-warn' : 'b-none'}">${r.due_status}</span>${r.welfare_check_suggested ? html` <span class="badge b-warn" title="Policy flag after repeated declines. Administrative only; not an inference about distress.">welfare check</span>` : ''}</td></tr>`)
            : html`<tr><td colspan="9" class="center muted" style="padding:2rem">No cases match these filters.</td></tr>`}</tbody></table></div>
        <div class="pager"><span class="small muted">${d.total} case(s) \u00b7 page ${d.page} of ${d.pages}</span>
          <button class="btn sm ghost" data-act="dfpage" data-p="${d.page - 1}" ${d.page <= 1 ? 'disabled' : ''}>Previous</button>
          <button class="btn sm ghost" data-act="dfpage" data-p="${d.page + 1}" ${d.page >= d.pages ? 'disabled' : ''}>Next</button></div>`.__raw;
    } catch (e) { const t = MS.$('#dash-table'); if (t) t.innerHTML = errBox(e).__raw; }
  }
  let sT = null;
  MS.handlers.dfsearch = (el) => { clearTimeout(sT); sT = setTimeout(() => { DF.search = el.value.trim(); DF.page = 1; loadDash(); }, 250); };
  MS.handlers.dffilter = (el) => { DF[el.dataset.k] = el.value; DF.page = 1; loadDash(); };
  MS.handlers.dfreset = () => { Object.assign(DF, { search: '', group: '', priority: '', review_status: '', due: '', sort: 'priority', order: 'desc', page: 1 }); MS.refresh(); };
  MS.handlers.dfprio = (el) => { DF.priority = DF.priority === el.dataset.p ? '' : el.dataset.p; DF.page = 1; MS.refresh(); };
  MS.handlers.dfdue = (el) => { DF.due = DF.due === el.dataset.d ? '' : el.dataset.d; DF.page = 1; MS.refresh(); };
  MS.handlers.dfsort = (el) => { const k = el.dataset.k; DF.order = DF.sort === k && DF.order === 'desc' ? 'asc' : 'desc'; DF.sort = k; loadDash(); };
  MS.handlers.dfpage = (el) => { DF.page = parseInt(el.dataset.p, 10); loadDash(); };
  MS.handlers.tofollow = () => MS.go('/followups');
  MS.handlers.opencase = (el) => MS.go('/case/' + el.dataset.id);
  document.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches && e.target.matches('tr.click')) MS.go('/case/' + e.target.dataset.id); });

  // ------------------------------------------------------------ case detail
  const CV = { tab: 'chart', audit: null };
  const DECISIONS = [['no_concern_found', 'No concern found on review'], ['monitor_only', 'Continue monitoring'], ['follow_up_planned', 'Follow-up planned'],
                     ['referral_decided', 'Referral decided'], ['escalated_to_protocol', 'Escalated per facility emergency / clinical protocol']];
  const STAGES = ['recommended', 'accepted', 'appointment_scheduled', 'appointment_completed', 'follow_up_pending', 'closed'];
  const STAGE_LABEL = { recommended: 'Referral recommended', accepted: 'Referral accepted', appointment_scheduled: 'Appointment scheduled', appointment_completed: 'Appointment completed', follow_up_pending: 'Follow-up pending', closed: 'Closed' };
  const NEXT = { recommended: ['accepted', 'closed'], accepted: ['appointment_scheduled', 'closed'], appointment_scheduled: ['appointment_completed', 'closed'], appointment_completed: ['follow_up_pending', 'closed'], follow_up_pending: ['closed'], closed: [] };
  const destLabel = (d, key) => ((d.destinations || []).find((x) => x.key === key) || { label: key }).label;

  function stepper(status) {
    const i = STAGES.indexOf(status);
    return html`<div class="stepper" aria-label="Referral stage: ${STAGE_LABEL[status]}">${STAGES.map((s, k) => html`<span class="${k < i ? 'done' : k === i ? 'cur' : ''}">${STAGE_LABEL[s]}</span>`)}</div>`;
  }

  MS.route(/^\/case\/([A-Za-z0-9-]+)$/, async (id) => {
    if (!(await MS.requireStaff())) return;
    if (S.staff.user.role === 'admin') return MS.go('/admin');
    const d = await MS.api('GET', '/api/cases/' + encodeURIComponent(id));
    CV.data = d; const clin = S.staff.user.role === 'clinician';
    const p = d.profile, r = d.recommendation, snap = d.snapshot;
    const completed = d.history.filter((h) => h.status === 'completed');
    const prev = completed.slice(0, -1).map((h) => h.score);
    MS.render(MS.staffShell('dashboard', html`
      <p><a href="#/dashboard">\u2190 Dashboard</a></p>
      <div class="card row between" style="margin-bottom:1rem">
        <div class="row"><img class="avatar" src="/api/photo/${p.person_id}" alt="Synthetic profile illustration">
          <div><h1 style="margin:0">${p.person_id}</h1>
            <div class="muted">${p.display_name} \u00b7 ${S.meta.profile.group_label}: ${p.group_name} \u00b7 language: ${(S.meta.languages.find((l) => l.code === p.language) || {}).name}</div>
            <div class="row" style="margin-top:.4rem">${MS.priorityBadge(r && r.priority)}
              <span class="badge ${snap.due_status === 'Up to date' ? 'b-ok' : 'b-warn'}">Check-in: ${snap.due_status}</span>
              ${snap.assigned_professional ? html`<span class="badge b-none">Assigned: ${snap.assigned_professional}</span>` : ''}
              ${snap.welfare_check_suggested ? html`<span class="badge b-warn">Welfare check suggested (policy flag)</span>` : ''}</div></div></div>
        <div class="small muted" style="text-align:right">Identity source: ${p.identity_source}<br>Synthetic demonstration record</div>
      </div>
      <div class="cols">
        <div class="stack">
          ${whyCard(d, r, clin)}
          <div class="card"><div class="row between"><h2>Wellbeing Assessment History</h2>
              <div class="tabs"><button class="chip ${CV.tab === 'chart' ? 'on' : ''}" data-act="cvtab" data-t="chart">Chart</button><button class="chip ${CV.tab === 'table' ? 'on' : ''}" data-act="cvtab" data-t="table">Data table</button></div></div>
            ${CV.tab === 'chart' ? html`<div class="chartbox"><canvas id="histchart" role="img" aria-label="${chartSummary(d)}"></canvas></div>
              <p class="small muted" id="chart-summary">${chartSummary(d)}</p>
              <p class="small muted">Higher values represent greater reported difficulty on the ${d.instrument.id} scale (0\u2013${d.instrument.score_max}). Grey crosses mark check-ins that were not completed (partial, declined or postponed) \u2014 they are missing observations, not zeros. Dashed amber lines mark authorized case events, shown for context only.</p>`
              : historyTable(d)}</div>
          ${analysisCard(d, r, prev)}
          ${d.events.length ? html`<div class="card"><h2>${S.meta.profile.context_label} \u2014 authorized events</h2>
            <ul class="clean">${d.events.map((e) => html`<li><b>${D(e.date)}</b> \u2014 ${e.label} <span class="muted small">(${e.source})</span></li>`)}</ul>
            <p class="small muted">Wellbeing changes may occur around these events. Manasetu reports timing only and never states that an event caused a change.</p></div>` : ''}
          ${clin && d.domains ? domainCard(d.domains) : ''}
          <div class="card"><h2>Longitudinal follow-up timeline</h2>${progressNote(d, r)}
            <div class="timeline">${d.timeline.map((t) => html`<div class="t ${t.kind}"><b>${D(t.date)}</b> \u00b7 ${t.text}</div>`)}</div></div>
        </div>
        <aside class="stack" aria-label="Actions">${actionsPanel(d, clin)}</aside>
      </div>`));
    if (CV.tab === 'chart') drawChart(d);
  });

  function whyCard(d, r, clin) {
    if (!r) return html`<div class="card"><h2>No analysis yet</h2><p class="muted">No completed assessment is on file for this case. ${d.snapshot.due_status === 'Declined' || d.snapshot.due_status === 'Postponed' ? 'The latest check-in was ' + d.snapshot.due_status.toLowerCase() + '. No score or distress is inferred from this.' : 'A first check-in is due.'}</p></div>`;
    return html`<div class="card tint"><div class="row between"><h2 style="margin:0">Why was this case flagged?</h2>${MS.priorityBadge(r.priority)}</div>
      <p style="font-size:1.08rem;margin-top:.8rem"><b>${r.explanation}</b></p>
      <h3>Evidence</h3><ul class="clean">${r.reasons.map((x) => html`<li>${x}</li>`)}</ul>
      <div class="kvgrid" style="margin-top:.8rem">
        <div><div class="k">Data quality</div><div class="v">${r.data_sufficiency}</div></div>
        <div><div class="k">Recommended next step</div><div class="v">${r.priority === 'Urgent Human Review' ? 'Urgent professional review per facility protocol' : r.priority === 'Human Follow-Up Recommended' ? 'Authorized professional review' : r.priority === 'Monitor' ? 'Review at next assessment' : 'Continue routine check-ins'}</div></div>
        <div><div class="k">Clinical diagnosis</div><div class="v">Not provided by the AI</div></div>
        <div><div class="k">Review status</div><div class="v">${r.review_status}</div></div>
      </div>
      <p class="small muted" style="margin-bottom:0">Rule set ${r.rule_set_version} \u00b7 transparent rules, not a machine-learning prediction. No probability or diagnosis is produced. ${d.instrument.id === 'DEMO-WB-1' ? 'Thresholds are demonstration placeholders pending clinical approval.' : 'Published cut-points are used where they exist; project choices (persistence, sudden change, item-9 urgent level) need clinical sign-off.'}</p></div>`;
  }
  function analysisCard(d, r, prev) {
    if (!r) return html``;
    const est = r.baseline_status === 'established';
    return html`<div class="card"><h2>Personal baseline &amp; longitudinal analysis</h2>
      <div class="kvgrid">
        <div><div class="k">Current result</div><div class="v">${r.current_value ?? 'Not scored'}${r.current_value != null ? ' / ' + d.instrument.score_max : ''}</div></div>
        <div><div class="k">Previous results</div><div class="v">${prev.length ? prev.join(', ') : '\u2014'}</div></div>
        <div><div class="k">Personal baseline</div><div class="v">${est ? r.baseline_value : 'Baseline Not Established'}</div></div>
        <div><div class="k">Difference from baseline</div><div class="v">${est && r.change_from_baseline != null ? (r.change_from_baseline > 0 ? '+' : '') + r.change_from_baseline : '\u2014'}</div></div>
        <div><div class="k">Recent trend</div><div class="v">${r.trend || '\u2014'}</div></div>
        <div><div class="k">Persistence of change</div><div class="v">${r.persistent ? 'Persists across recent valid assessments' : 'Not persistent'}</div></div>
        <div><div class="k">Assessment completeness</div><div class="v">${r.completeness != null ? Math.round(r.completeness * 100) + '% of items answered' : '\u2014'}</div></div>
        <div><div class="k">Valid assessments used</div><div class="v">${r.valid_observations ?? '\u2014'}</div></div>
        <div style="grid-column:1/-1"><div class="k">Validated screening threshold</div><div class="v" style="font-weight:600">${d.instrument.threshold_note}</div></div>
      </div>
      <p class="small muted">Baseline = median of the first ${3} valid assessments of this instrument version after any clinician baseline reset; a single observation never establishes a baseline. Partial or declined check-ins are excluded and never treated as zero.</p></div>`;
  }
  function domainCard(domains) {
    return html`<div class="card"><h2>Symptom dimensions (clinician view)</h2><p class="small muted">Current response versus the baseline-period median for each dimension (0 = never, 4 = very often).</p>
      ${domains.map((x) => html`<div class="review-row"><div style="min-width:170px"><b>${x.domain}</b>${x.safety ? html` <span class="badge b-warn">safety item</span>` : ''}</div>
        <div style="flex:1"><div class="bar"><i style="width:${(x.current ?? 0) / x.scale_max * 100}%"></i><span>${x.current ?? '\u2014'}</span></div>
          ${x.baseline_median != null ? html`<div class="bar"><i class="base" style="width:${x.baseline_median / x.scale_max * 100}%"></i><span class="muted">baseline ${x.baseline_median}</span></div>` : ''}</div></div>`)}</div>`;
  }
  function historyTable(d) {
    return html`<div class="tablewrap"><table><thead><tr><th>Date</th><th>Status</th><th>Score</th><th>Baseline at the time</th><th>Trend</th><th>Priority</th></tr></thead>
      <tbody>${d.history.slice().reverse().map((h) => html`<tr><td>${D(h.date)}</td><td>${h.status}</td><td>${h.score ?? '\u2014'}</td><td>${h.baseline_value ?? '\u2014'}</td><td>${h.trend || '\u2014'}</td><td>${h.priority || '\u2014'}</td></tr>`)}</tbody></table></div>`;
  }
  function chartSummary(d) {
    const c = d.history.filter((h) => h.status === 'completed');
    const r = d.recommendation;
    const miss = d.history.length - c.length;
    return `${c.length} completed assessment(s)` + (c.length ? `: scores ${c.map((h) => h.score).join(', ')}` : '') +
      (r && r.baseline_status === 'established' ? `. Personal baseline ${r.baseline_value}` : '. Baseline not established') +
      (r && r.trend ? `. Latest trend: ${r.trend}` : '') + (miss ? `. ${miss} attempt(s) not completed (partial, declined or postponed).` : '.');
  }
  function progressNote(d, r) {
    if (r && (r.trend === 'Improving' || (r.change_from_baseline != null && r.change_from_baseline <= -3)))
      return html`<div class="ok">Improvement in the measured symptom score observed. Continue assessment and professional review according to the care plan.</div>`;
    return html``;
  }
  MS.handlers.cvtab = (el) => { CV.tab = el.dataset.t; MS.refresh(); };

  function drawChart(d) {
    const canvas = MS.$('#histchart'); if (!canvas || !window.Chart) return;
    const H = d.history; const r = d.recommendation;
    const color = { 'Urgent Human Review': '#C94C4C', 'Human Follow-Up Recommended': '#E9A23B', 'Monitor': '#3976B8', 'Routine Monitoring': '#2A9D8F' };
    const labels = H.map((h) => D(h.date));
    const scores = H.map((h) => (h.status === 'completed' ? h.score : null));
    const missing = H.map((h) => (h.status === 'completed' ? null : 0));
    const est = r && r.baseline_status === 'established';
    const evIdx = d.events.map((e) => { let best = 0, bd = Infinity; H.forEach((h, i) => { const dd = Math.abs(new Date(h.date) - new Date(e.date)); if (dd < bd) { bd = dd; best = i; } }); return { i: best, label: e.label }; });
    const eventPlugin = { id: 'events', afterDatasetsDraw(chart) {
      const { ctx, chartArea, scales } = chart; ctx.save(); ctx.strokeStyle = '#E9A23B'; ctx.setLineDash([5, 4]); ctx.fillStyle = '#8A5A0B'; ctx.font = '11px Segoe UI, sans-serif';
      evIdx.forEach((e, k) => { const x = scales.x.getPixelForValue(e.i); ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
        ctx.fillText('\u2691 ' + e.label, Math.min(x + 4, chartArea.right - 120), chartArea.top + 12 + (k % 3) * 13); });
      ctx.restore(); } };
    new Chart(canvas, { type: 'line', plugins: [eventPlugin],
      data: { labels, datasets: [
        { label: 'Assessment score', data: scores, borderColor: '#176B57', backgroundColor: '#176B57', tension: 0.25, spanGaps: false, borderWidth: 2.5,
          pointRadius: 6, pointBackgroundColor: H.map((h) => color[h.priority] || '#176B57'), pointBorderColor: '#fff', pointBorderWidth: 2 },
        ...(est ? [{ label: 'Personal baseline', data: H.map(() => r.baseline_value), borderColor: '#3976B8', borderDash: [8, 6], pointRadius: 0, borderWidth: 2 }] : []),
        { label: 'Not completed', data: missing, showLine: false, pointStyle: 'crossRot', pointRadius: 7, borderColor: '#64748B', backgroundColor: '#64748B' },
      ] },
      options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'nearest', intersect: true },
        scales: { y: { min: 0, suggestedMax: d.instrument.score_max, title: { display: true, text: 'Score (higher = greater reported difficulty)' } }, x: { title: { display: true, text: 'Assessment date' } } },
        plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { afterLabel: (c) => { const h = H[c.dataIndex]; return h ? [`Status: ${h.status}`, h.priority ? `Priority: ${h.priority}` : '', h.trend ? `Trend: ${h.trend}` : ''].filter(Boolean) : ''; } } } } } });
  }

  // ------------------------------------------------------------ actions panel
  function actionsPanel(d, clin) {
    const r = d.recommendation; const snap = d.snapshot;
    const cards = [];
    cards.push(html`<div class="card"><h2>Record Human Review</h2>
      ${r ? html`<form data-form="doreview" class="stack" data-rid="${r.recommendation_id}"><label for="rv-d">Review decision</label>
        <select id="rv-d">${DECISIONS.map(([k, l]) => html`<option value="${k}">${l}</option>`)}</select>
        <label for="rv-n">Note</label><textarea id="rv-n" maxlength="2000" placeholder="Brief, factual note"></textarea>
        <div id="rv-e"></div><button class="btn primary" type="submit">Record review</button></form>` : html`<p class="muted">No recommendation to review yet.</p>`}
      ${d.reviews.length ? html`<h3 style="margin-top:1rem">Review history</h3><ul class="clean">${d.reviews.slice().reverse().slice(0, 4).map((v) => html`<li><b>${v.decision.replace(/_/g, ' ')}</b> \u2014 ${v.reviewer} <span class="muted small">${MS.fmtDateTime(v.at)}</span>${v.note ? html`<div class="small muted">${v.note}</div>` : ''}</li>`)}</ul>` : ''}</div>`);
    cards.push(html`<div class="card"><h2>Assign Counsellor</h2><form data-form="doassign" class="row"><select id="as-u" style="flex:1" aria-label="Clinician"><option value="">Loading…</option></select>
      <button class="btn sm primary" type="submit">Assign</button></form><div id="as-e"></div></div>`);
    cards.push(html`<div class="card"><h2>Refer</h2>${r ? html`<form data-form="doreferral" class="stack" data-rid="${r.recommendation_id}">
      <label for="rf-d">Authorized destination</label><select id="rf-d">${d.destinations.map((x) => html`<option value="${x.key}">${x.label}</option>`)}</select>
      <label for="rf-r">Referral reason</label><textarea id="rf-r" maxlength="1000" placeholder="Why is this referral recommended?"></textarea>
      <label for="rf-f">Follow-up date (optional)</label><input id="rf-f" type="date"><div id="rf-e"></div>
      <button class="btn primary" type="submit">Create referral (status: recommended)</button></form>
      <p class="small muted">Creating a referral does not mark it completed. Medication is never prescribed by the system \u2014 only a qualified clinician makes treatment decisions.</p>` : html`<p class="muted">Available once an assessment exists.</p>`}</div>`);
    cards.push(html`<div class="card"><h2>Referrals</h2>${d.referrals.length ? d.referrals.slice().reverse().map((rf) => referralBlock(d, rf, clin)) : html`<p class="muted">No referrals yet.</p>`}</div>`);
    cards.push(html`<div class="card"><h2>Schedule Follow-Up</h2><form data-form="dofollow" class="stack" data-rid="${r ? r.recommendation_id : ''}">
      <label for="fu-d">Date</label><input id="fu-d" type="date" required><label for="fu-n">Note (optional)</label><input id="fu-n" type="text" maxlength="500"><div id="fu-e"></div>
      <button class="btn primary" type="submit">Schedule</button></form>
      ${d.follow_ups.length ? html`<ul class="clean" style="margin-top:.8rem">${d.follow_ups.slice().reverse().map((f) => html`<li><b>${D(f.scheduled_for)}</b> \u2014 ${f.status}${f.note ? ' \u00b7 ' + f.note : ''}
        ${f.status === 'pending' ? html` <button class="btn sm ghost" data-act="fucomplete" data-id="${f.follow_up_id}">Mark completed</button>` : ''}</li>`)}</ul>` : ''}</div>`);
    if (clin) {
      cards.push(html`<div class="card"><h2>Support plan &amp; clinical notes</h2>
        <form data-form="donote" class="stack"><select id="nt-k"><option value="support_plan">Support plan</option><option value="note">Clinical note</option></select>
          <textarea id="nt-b" maxlength="4000" placeholder="Visible to clinicians only"></textarea><div id="nt-e"></div><button class="btn primary" type="submit">Save</button></form>
        ${(d.notes || []).length ? html`<ul class="clean" style="margin-top:.8rem">${d.notes.slice(0, 5).map((n) => html`<li><b>${n.kind.replace('_', ' ')}</b> \u2014 ${n.author} <span class="muted small">${MS.fmtDateTime(n.at)}</span><div>${n.body}</div></li>`)}</ul>` : ''}</div>`);
      cards.push(html`<div class="card"><h2>Baseline</h2><p class="small muted">Start a new baseline reference period (e.g. after treatment or an instrument change). History is kept.${d.profile.baseline_anchor_date ? ' Current reference starts ' + D(d.profile.baseline_anchor_date) + '.' : ''}</p>
        <button class="btn sm ghost" data-act="doreset">Reset baseline from today</button><div id="rs-e"></div></div>`);
    }
    cards.push(html`<div class="card"><h2>Audit history</h2><button class="btn sm ghost" data-act="loadaudit">View audit history for this case</button><div id="audit-box"></div></div>`);
    setTimeout(loadClinicians, 0);
    return cards;
  }
  function referralBlock(d, rf, clin) {
    const nexts = NEXT[rf.status].filter((n) => clin || (rf.status === 'recommended' && n === 'closed'));
    return html`<div class="review-row" style="display:block"><div class="row between"><b>${destLabel(d, rf.destination)}</b><span class="badge b-none">${STAGE_LABEL[rf.status]}</span></div>
      ${stepper(rf.status)}<div class="small muted" style="margin:.3rem 0">${rf.reason}${rf.appointment_at ? ' \u00b7 appointment ' + rf.appointment_at.replace('T', ' ').slice(0, 16) : ''}${rf.outcome_status ? ' \u00b7 outcome: ' + rf.outcome_status : ''}</div>
      ${nexts.length ? html`<form data-form="refstatus" data-id="${rf.referral_id}" class="stack"><div class="row"><select class="rs-s" aria-label="Next stage">${nexts.map((n) => html`<option value="${n}">${n === 'closed' ? (rf.status === 'recommended' ? 'Withdraw / close' : 'Close referral') : STAGE_LABEL[n]}</option>`)}</select>
        <button class="btn sm primary" type="submit">Update</button></div>
        <div class="row"><input class="rs-a" type="datetime-local" aria-label="Appointment date and time (when scheduling)"><input class="rs-o" type="text" maxlength="60" placeholder="Outcome (required to close)" aria-label="Outcome"></div><div class="rs-e"></div></form>` : ''}</div>`;
  }
  async function loadClinicians() {
    const sel = MS.$('#as-u'); if (!sel) return;
    try { const r = await MS.api('GET', '/api/staff/clinicians'); const cur = CV.data.snapshot.assigned_professional;
      sel.innerHTML = '<option value="">Select clinician…</option>' + r.items.map((u) => `<option value="${MS.esc(u.user_id)}" ${u.display_name === cur ? 'selected' : ''}>${MS.esc(u.display_name)}</option>`).join(''); } catch (e) { /* ignore */ }
  }
  const pid = () => CV.data.profile.person_id;
  const done = (msg) => { MS.toast(msg); MS.refresh(); };
  const fail = (sel, e) => { const b = MS.$(sel); if (b) b.innerHTML = errBox(e).__raw; };
  MS.handlers.doreview = async (f) => {
    try { await MS.api('POST', `/api/cases/${pid()}/review`, { recommendation_id: f.dataset.rid, decision: MS.$('#rv-d').value, note: MS.$('#rv-n').value }, 'staff'); done('Human review recorded'); MS.refreshNotifications(); }
    catch (e) { fail('#rv-e', e); } };
  MS.handlers.doassign = async () => {
    try { await MS.api('POST', `/api/cases/${pid()}/assign`, { user_id: MS.$('#as-u').value }, 'staff'); done('Professional assigned'); } catch (e) { fail('#as-e', e); } };
  MS.handlers.doreferral = async (f) => {
    try { await MS.api('POST', `/api/cases/${pid()}/referrals`, { recommendation_id: f.dataset.rid, destination: MS.$('#rf-d').value, reason: MS.$('#rf-r').value, follow_up_date: MS.$('#rf-f').value || null }, 'staff'); done('Referral created (recommended)'); }
    catch (e) { fail('#rf-e', e); } };
  MS.handlers.refstatus = async (f) => {
    const body = { status: MS.$('.rs-s', f).value, appointment_at: MS.$('.rs-a', f).value || null, outcome_status: MS.$('.rs-o', f).value || null };
    try { await MS.api('PATCH', `/api/referrals/${f.dataset.id}/status`, body, 'staff'); done('Referral updated'); } catch (e) { MS.$('.rs-e', f).innerHTML = errBox(e).__raw; } };
  MS.handlers.dofollow = async (f) => {
    try { await MS.api('POST', `/api/cases/${pid()}/follow-ups`, { when: MS.$('#fu-d').value, note: MS.$('#fu-n').value || null, recommendation_id: f.dataset.rid || null }, 'staff'); done('Follow-up scheduled'); }
    catch (e) { fail('#fu-e', e); } };
  MS.handlers.fucomplete = async (el) => { try { await MS.api('PATCH', `/api/follow-ups/${el.dataset.id}/complete`, {}, 'staff'); done('Follow-up completed'); } catch (e) { MS.toast(e.message); } };
  MS.handlers.donote = async () => {
    try { await MS.api('POST', `/api/cases/${pid()}/notes`, { kind: MS.$('#nt-k').value, body: MS.$('#nt-b').value }, 'staff'); done('Saved'); } catch (e) { fail('#nt-e', e); } };
  MS.handlers.doreset = async () => { if (!confirm('Start a new baseline reference period for this case? History is kept.')) return;
    try { await MS.api('POST', `/api/cases/${pid()}/baseline-reset`, {}, 'staff'); done('Baseline reset'); } catch (e) { fail('#rs-e', e); } };
  MS.handlers.loadaudit = async () => {
    try { const r = await MS.api('GET', `/api/cases/${pid()}/audit`);
      MS.$('#audit-box').innerHTML = html`<ul class="clean" style="margin-top:.6rem">${r.items.slice(0, 25).map((a) => html`<li><b>${a.action.replace(/_/g, ' ')}</b> \u00b7 ${a.actor || a.actor_type} <span class="muted small">${MS.fmtDateTime(a.ts)} \u00b7 ${a.outcome}</span></li>`)}</ul>`.__raw;
    } catch (e) { fail('#audit-box', e); } };

  // ------------------------------------------------------------ referral tracking (all cases)
  let refFilter = '';
  MS.route(/^\/referrals$/, async () => {
    if (!(await MS.requireStaff())) return;
    const r = await MS.api('GET', '/api/referrals' + (refFilter ? '?status=' + refFilter : ''));
    const dest = {}; (S.meta.profile.destinations || []).forEach((x) => (dest[x.key] = x.label));
    MS.render(MS.staffShell('referrals', html`
      <h1>Referral &amp; Follow-up Tracking</h1>
      <p class="muted">Case flagged \u2192 human review \u2192 referral decision \u2192 appointment \u2192 follow-up \u2192 next assessment due. A referral is only complete when an authorized user closes it with an outcome.</p>
      <div class="card"><div class="filters"><div><label for="rf-s">Stage</label><select id="rf-s" data-change="reffilter"><option value="">All stages</option>
        ${STAGES.map((s) => html`<option value="${s}" ${refFilter === s ? 'selected' : ''}>${STAGE_LABEL[s]}</option>`)}</select></div></div>
      <div class="tablewrap"><table><thead><tr><th>Case</th><th>Destination</th><th>Stage</th><th>Reason</th><th>Appointment</th><th>Follow-up date</th><th>Outcome</th></tr></thead>
        <tbody>${r.items.length ? r.items.map((x) => html`<tr class="click" data-act="opencase" data-id="${x.person_id}"><td><b>${x.person_id}</b></td><td>${dest[x.destination] || x.destination}</td>
          <td>${stepper(x.status)}</td><td style="max-width:240px">${x.reason}</td><td>${x.appointment_at ? x.appointment_at.replace('T', ' ').slice(0, 16) : '\u2014'}</td><td>${D(x.follow_up_date)}</td><td>${x.outcome_status || '\u2014'}</td></tr>`)
          : html`<tr><td colspan="7" class="center muted" style="padding:2rem">No referrals in this view.</td></tr>`}</tbody></table></div></div>`));
  });
  MS.handlers.reffilter = (el) => { refFilter = el.value; MS.refresh(); };

  // ------------------------------------------------------------ follow-up dashboard
  let fuStatus = 'pending';
  MS.route(/^\/followups$/, async () => {
    if (!(await MS.requireStaff())) return;
    const r = await MS.api('GET', '/api/follow-ups?status=' + fuStatus);
    MS.render(MS.staffShell('followups', html`
      <h1>Follow-up Dashboard</h1>
      <p class="muted">Scheduled follow-ups across your authorized cases. Improvement in a score is never labelled "recovered" \u2014 continue assessment and professional review according to the care plan.</p>
      <div class="card"><div class="tabs"><button class="chip ${fuStatus === 'pending' ? 'on' : ''}" data-act="fustatus" data-s="pending">Pending</button><button class="chip ${fuStatus === 'completed' ? 'on' : ''}" data-act="fustatus" data-s="completed">Completed</button></div>
      <div class="tablewrap"><table><thead><tr><th>Case</th><th>Scheduled</th><th>Status</th><th>Note</th><th></th></tr></thead>
        <tbody>${r.items.length ? r.items.map((f) => html`<tr><td><a href="#/case/${f.person_id}"><b>${f.person_id}</b></a></td><td>${D(f.scheduled_for)} ${f.overdue ? html`<span class="badge b-warn">overdue</span>` : ''}</td>
          <td>${f.status}</td><td>${f.note || '\u2014'}</td><td>${f.status === 'pending' ? html`<button class="btn sm ghost" data-act="fucomplete2" data-id="${f.follow_up_id}">Mark completed</button>` : ''}</td></tr>`)
          : html`<tr><td colspan="5" class="center muted" style="padding:2rem">Nothing here.</td></tr>`}</tbody></table></div></div>`));
  });
  MS.handlers.fustatus = (el) => { fuStatus = el.dataset.s; MS.refresh(); };
  MS.handlers.fucomplete2 = async (el) => { try { await MS.api('PATCH', `/api/follow-ups/${el.dataset.id}/complete`, {}, 'staff'); MS.toast('Follow-up completed'); MS.refresh(); } catch (e) { MS.toast(e.message); } };
})();
