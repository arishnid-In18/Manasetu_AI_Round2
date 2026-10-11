/* MANASETU AI — kiosk voice assistant. Touch always works; voice is opt-in per session.
   Design rules: every spoken answer is read back and confirmed; the sensitive item is never answered aloud;
   final submission is always by touch; audio/transcripts are never sent to or stored by Manasetu. */
(function () {
  'use strict';
  const MS = window.MS; const { S, html } = MS; const Vc = window.MSVoice;
  const T = (...a) => MS.t(...a);
  const V = (MS.V = { active: false, confirming: false, accepted: false, state: 'idle', heard: '', warn: '', token: 0, lastIdx: -1 });
  const lang = () => S.kiosk.language || S.lang;
  const curIdx = () => parseInt((location.hash.match(/\/q\/(\d+)/) || [0, 1])[1], 10) - 1;
  const featureOn = () => !!(S.meta.features && S.meta.features.voice_assistant);
  const audit = (event) => MS.api('POST', '/api/kiosk/voice-event', { event }, 'kiosk').catch(() => {});

  // ------------------------------------------------------------ panel
  function inner() {
    const sup = Vc.supported();
    if (!featureOn()) return html``;
    if (!sup.stt || !sup.tts) return html`<div class="note small">${T('v_unsupported')}</div>`;
    if (V.confirming) return html`<div class="voicepanel"><h3>${T('v_privacy_title')}</h3><p>${T('v_privacy_body')}</p>
      <div class="row"><button class="btn primary" data-act="voiceaccept">\u{1F399} ${T('v_privacy_ok')}</button><button class="btn grey" data-act="voicedecline">${T('v_privacy_no')}</button></div></div>`;
    if (!V.active) return html`<div><button class="btn blue" data-act="voicestart">\u{1F399} ${T('v_start')}</button>${V.warn ? html`<div class="err" role="alert">${V.warn}</div>` : ''}</div>`;
    const label = { speaking: T('v_speaking'), listening: T('v_listening'), touch: T('v_touch_only'), idle: '' }[V.state] || '';
    return html`<div class="voicepanel" role="status" aria-live="polite"><div class="row between"><div class="row"><span class="vdot ${V.state}" aria-hidden="true"></span><b>${label}</b></div>
      <button class="btn sm grey" data-act="voicestop">${T('v_stop')}</button></div>
      ${V.heard ? html`<div class="small">${T('v_heard_label')}: \u201c${V.heard}\u201d</div>` : ''}
      ${V.state === 'touch' ? '' : html`<div class="small muted">${T('v_help_line')}</div>`}${V.warn ? html`<div class="warn small">${V.warn}</div>` : ''}</div>`;
  }
  MS.voicePanel = () => html`<div class="voice-slot">${inner()}</div>`;
  const paint = () => { const el = MS.$('.voice-slot'); if (el) el.innerHTML = inner().__raw; };
  const setState = (s) => { V.state = s; paint(); };

  // ------------------------------------------------------------ lifecycle
  MS.handlers.voicestart = () => { V.confirming = !V.accepted; if (V.accepted) activate(); else paint(); };
  MS.handlers.voiceaccept = () => { V.accepted = true; V.confirming = false; activate(); };
  MS.handlers.voicedecline = () => { V.confirming = false; paint(); };
  MS.handlers.voicestop = () => stopVoice();
  function activate() {
    V.active = true; V.warn = ''; V.heard = ''; V.lastIdx = -1; audit('started');
    if (Vc.hasVoiceFor(lang()) === false) V.warn = T('v_novoice');
    paint(); MS.voiceAfterRender(curIdx());
  }
  function stopVoice() {
    if (V.active) audit('stopped');
    V.active = false; V.confirming = false; V.token++; Vc.cancel(); V.state = 'idle'; V.heard = ''; paint();
  }
  MS.voiceReset = () => { V.active = false; V.confirming = false; V.token++; Vc.cancel(); V.state = 'idle'; V.heard = ''; V.lastIdx = -1; V.accepted = false; };
  MS.voiceOnTouch = () => { if (V.active) { V.token++; Vc.cancel(); V.state = 'idle'; paint(); } };

  // ------------------------------------------------------------ questionnaire loop
  MS.voiceAfterRender = (idx) => { if (!V.active || V.lastIdx === idx) return; V.lastIdx = idx; step(); };
  MS.voiceReview = async () => {
    if (!V.active) return; const my = ++V.token; setState('speaking'); await Vc.speak(T('s_review'), lang());
    if (my === V.token) { V.active = false; V.state = 'idle'; paint(); }       // submission is deliberate and by touch
  };
  async function step() {
    const my = ++V.token; const alive = () => V.active && my === V.token;
    const inst = S.kiosk.instrument; const idx = curIdx(); const item = inst.items[idx]; const L = lang();
    V.heard = '';
    if (item.voice_ok === false) { setState('touch'); await Vc.speak(T('s_touch_only'), L); return; }
    setState('speaking');
    await Vc.speak((inst.stem ? inst.stem + ' ' : '') + item.text + '. ' + inst.options.map((o, i) => `${i + 1}. ${o.label}`).join('. ') + '. ' + T('s_say'), L);
    for (let tries = 0; tries < 3 && alive(); tries++) {
      setState('listening'); let res;
      try { res = await Vc.listen(L); } catch (e) { if (e.message === 'not-allowed') { audit('permission_denied'); stopVoice(); V.warn = T('v_mic_denied'); paint(); } else if (e.message === 'unsupported') { audit('unsupported'); stopVoice(); } return; }
      if (!alive()) return;
      if (!res) { setState('speaking'); await Vc.speak(T('s_nohear'), L); continue; }
      V.heard = res.alternatives[0]; paint();
      const m = Vc.interpretAll(res.alternatives, inst.options);
      if (m.type === 'command') return command(m.name, idx, my);
      if (m.type === 'answer') {
        setState('speaking'); await Vc.speak(T('s_heard', { answer: m.label }), L); if (!alive()) return;
        const yn = await confirmYesNo(my); if (!alive()) return;
        if (yn === 'yes') return commit(idx, { value: m.value, skipped: false, input_mode: 'voice' }, my);
        continue;                                                          // "no" or unclear: ask again, nothing saved
      }
      setState('speaking'); await Vc.speak(T('s_unclear'), L);
    }
    if (alive()) { setState('speaking'); await Vc.speak(T('s_tap'), L); setState('touch'); }
  }
  async function confirmYesNo(my) {
    for (let k = 0; k < 2; k++) {
      setState('listening'); let r; try { r = await Vc.listen(lang(), 7000); } catch (e) { stopVoice(); return 'unknown'; }
      if (my !== V.token) return 'unknown';
      if (!r) { setState('speaking'); await Vc.speak(T('s_nohear'), lang()); continue; }
      V.heard = r.alternatives[0]; paint();
      const yn = Vc.parseYesNo(r.alternatives); if (yn !== 'unknown') return yn;
    }
    return 'unknown';
  }
  async function commit(idx, body, my) {
    const inst = S.kiosk.instrument; const item = inst.items[idx];
    try {
      await MS.api('PUT', `/api/kiosk/session/${S.kiosk.sid}/responses`, { question_id: item.id, ...body }, 'kiosk');
      S.kiosk.responses[item.id] = body.skipped ? { value: null, skipped: true } : { value: body.value, skipped: false };
    } catch (e) { MS.toast(e.message); setState('touch'); return; }
    setState('speaking'); await Vc.speak(T(body.skipped ? 's_skipped' : 's_saved'), lang());
    if (my !== V.token || !V.active) return;
    MS.go(idx === inst.items.length - 1 ? '/review' : '/q/' + (idx + 2));
  }
  async function command(name, idx, my) {
    const inst = S.kiosk.instrument; const r = S.kiosk.responses[inst.items[idx].id];
    if (name === 'stop') { stopVoice(); return Vc.speak(T('s_stopped'), lang()); }
    if (name === 'repeat') { V.lastIdx = -1; return MS.voiceAfterRender(idx); }
    if (name === 'skip') return commit(idx, { value: null, skipped: true, input_mode: 'voice' }, my);
    if (name === 'back') { if (idx === 0) { V.lastIdx = -1; return MS.voiceAfterRender(idx); } return MS.go('/q/' + idx); }
    if (name === 'next') {
      if (!r) { setState('speaking'); await Vc.speak(T('s_answer_first'), lang()); V.lastIdx = -1; return MS.voiceAfterRender(idx); }
      return MS.go(idx === inst.items.length - 1 ? '/review' : '/q/' + (idx + 2));
    }
  }

  // ------------------------------------------------------------ read-aloud (no microphone needed)
  async function readChunks(chunks) { const my = ++V.token; for (const c of chunks) { if (my !== V.token) return; await Vc.speak(c, lang()); } }
  MS.handlers.readpage = async (el) => {
    if (!Vc.supported().tts) return MS.toast(T('tts_unavailable'));
    if (el.dataset.what === 'consent' && S.kiosk.consent) {
      const c = S.kiosk.consent; return readChunks([c.title, ...c.sections.map((s) => s.heading + '. ' + s.body), T('ack_prompt'), ...c.acknowledgements.map((a) => a.text)]);
    }
    return readChunks([T('choose_title'), T('yes_t'), T('notnow_t'), T('no_t')]);
  };

  // ------------------------------------------------------------ voice Yes / Not now / No
  MS.handlers.voicechoose = async () => {
    const sup = Vc.supported(); if (!sup.stt || !sup.tts) return MS.toast(T('v_unsupported'));
    const my = ++V.token; const L = lang(); const box = MS.$('#choose-error');
    const say = (m) => { if (box) box.innerHTML = m ? html`<div class="note">${m}</div>`.__raw : ''; };
    audit('started');
    await Vc.speak(T('s_choose'), L);
    for (let tries = 0; tries < 3 && my === V.token; tries++) {
      say(T('v_choose_listen')); let r;
      try { r = await Vc.listen(L); } catch (e) { say(T('v_mic_denied')); audit('permission_denied'); return; }
      if (my !== V.token) return;
      if (!r) { await Vc.speak(T('s_nohear'), L); continue; }
      const it = Vc.parseIntent(r.alternatives);
      if (it === 'unknown') { await Vc.speak(T('s_unclear'), L); continue; }
      await Vc.speak(T('s_intent_heard', { answer: T({ yes: 'i_yes', not_now: 'i_not_now', no: 'i_no' }[it]) }), L);
      let yn = 'unknown'; for (let k = 0; k < 2 && yn === 'unknown'; k++) { const r2 = await Vc.listen(L, 7000).catch(() => null); if (my !== V.token) return; if (r2) yn = Vc.parseYesNo(r2.alternatives); }
      if (yn === 'yes') { const btn = MS.$(`[data-act=intent][data-d=${it}]`); if (btn) btn.click(); return; }
    }
    say(T('s_tap'));
  };
})();
