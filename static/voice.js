/* MANASETU AI — voice assistant primitives.
   - speak(): text-to-speech via the browser's speechSynthesis (needs an installed voice for the language)
   - listen(): one-shot speech recognition via the browser's SpeechRecognition (Chrome / Edge). The browser may send
     audio to its vendor's speech service. Manasetu itself never records, uploads or stores audio or transcripts.
   - interpret()/parseYesNo(): pure functions that map a transcript to an answer option or a command.
   The matcher is unit-tested in tests/voice_matcher.test.mjs. Tamil/Hindi vocabulary is demonstration-level and
   must be reviewed with native speakers and tested with real recognition engines before any real use. */
(function (root) {
  'use strict';
  const LANG = { ta: 'ta-IN', hi: 'hi-IN', en: 'en-IN' };

  // ------------------------------------------------------------------ text helpers
  const norm = (s) => String(s || '').toLowerCase().normalize('NFC')
    .replace(/[\u0966-\u096F]/g, (d) => String(d.charCodeAt(0) - 0x0966))      // Devanagari digits -> ASCII
    .replace(/[\u0BE6-\u0BEF]/g, (d) => String(d.charCodeAt(0) - 0x0BE6))      // Tamil digits -> ASCII
    .replace(/[.,!?;:"'()\u2019\u2018\-\u2013\u2014_\u0964]/g, ' ').replace(/\s+/g, ' ').trim();
  const isLatin = (p) => /^[a-z0-9 ]+$/.test(p);
  // Latin phrases must match whole words; Indic phrases match as substrings (Tamil/Hindi attach suffixes to words).
  const has = (text, phrase) => {
    const p = norm(phrase); if (!p) return false;
    // short phrases (any script) must be whole words: Hindi "ना" must not fire inside "नाम"
    return (isLatin(p) || p.length <= 3) ? (' ' + text + ' ').includes(' ' + p + ' ') : text.includes(p);
  };

  const NUMBERS = {
    1: ['one', '1', 'ek', 'एक', 'ஒன்று', 'ஒண்ணு', 'ondru', 'onnu'],
    2: ['two', '2', 'do', 'दो', 'இரண்டு', 'ரெண்டு', 'irandu', 'rendu'],
    3: ['three', '3', 'teen', 'तीन', 'மூன்று', 'மூணு', 'moondru', 'moonu'],
    4: ['four', '4', 'char', 'chaar', 'चार', 'நான்கு', 'நாலு', 'naangu', 'naalu'],
    5: ['five', '5', 'paanch', 'panch', 'पाँच', 'पांच', 'ஐந்து', 'அஞ்சு', 'ainthu', 'anju'],
  };
  const COMMANDS = {
    stop: ['stop', 'stop voice', 'quit', 'बंद', 'रुको', 'बंद करो', 'நிறுத்து', 'நிறுத்துங்கள்'],   // NOT 'போதும்': it is inside 'ஒருபோதும்' (never)
    repeat: ['repeat', 'again', 'say again', 'दोबारा', 'फिर से', 'फिरसे', 'दोहराओ', 'மீண்டும்', 'திரும்ப சொல்லுங்கள்', 'மறுபடியும்'],
    back: ['back', 'previous', 'go back', 'पीछे', 'पिछला', 'वापस', 'முந்தைய', 'பின்னால்', 'பின்செல்'],
    next: ['next', 'next question', 'अगला', 'आगे', 'அடுத்து', 'அடுத்தது'],
    skip: ['skip', 'prefer not to answer', 'pass', 'छोड़ो', 'छोड़ दो', 'उत्तर नहीं देना', 'जवाब नहीं देना', 'தவிர்', 'பதிலளிக்க விரும்பவில்லை', 'பதில் வேண்டாம்'],
  };
  const YES = ['yes', 'yeah', 'yep', 'correct', 'right', 'ok', 'okay', 'confirm', 'हाँ', 'हां', 'जी', 'ठीक', 'सही', 'हाँ जी', 'ஆம்', 'ஆமாம்', 'சரி', 'சரிதான்', 'சரியானது', 'ஆமா'];
  const NO = ['no', 'nope', 'wrong', 'incorrect', 'try again', 'नहीं', 'ना', 'गलत', 'फिर से बोलो', 'இல்லை', 'வேண்டாம்', 'தவறு', 'இல்ல'];

  // ------------------------------------------------------------------ interpretation (pure)
  function findCommand(text) {
    for (const name of ['stop', 'repeat', 'back', 'skip', 'next']) {      // order matters: 'stop' wins over everything
      if (COMMANDS[name].some((p) => has(text, p))) return name;
    }
    return null;
  }
  function numbersIn(text) {
    const found = new Set();
    const toks = text.split(' ');
    for (const [d, words] of Object.entries(NUMBERS)) if (words.some((w) => toks.includes(norm(w)))) found.add(Number(d));   // whole words only
    return [...found];
  }
  /** options: [{value, label}] in display order. Returns one of
      {type:'command',name} | {type:'answer',value,label,by:'label'|'number'} | {type:'ambiguous'} | {type:'unknown'} | {type:'none'} */
  function interpret(transcript, options) {
    const text = norm(transcript);
    if (!text) return { type: 'none' };
    const cmd = findCommand(text);
    if (cmd) return { type: 'command', name: cmd };
    // 1) spoken answer text, longest label first ("very often" must beat "often")
    const byLabel = options.map((o) => ({ o, l: norm(o.label) })).filter((x) => x.l && has(text, x.l)).sort((a, b) => b.l.length - a.l.length);
    if (byLabel.length) {
      const top = byLabel[0].l.length;
      const same = byLabel.filter((x) => x.l.length === top);
      if (same.length === 1) return { type: 'answer', value: same[0].o.value, label: same[0].o.label, by: 'label' };
      return { type: 'ambiguous' };
    }
    // 2) option number 1..N (1 = first option shown)
    const nums = numbersIn(text).filter((n) => n >= 1 && n <= options.length);
    if (nums.length === 1) { const o = options[nums[0] - 1]; return { type: 'answer', value: o.value, label: o.label, by: 'number' }; }
    if (nums.length > 1) return { type: 'ambiguous' };
    return { type: 'unknown' };
  }
  /** Try several recogniser alternatives, keep the first useful one. */
  function interpretAll(alternatives, options) {
    let last = { type: 'none' };
    for (const a of alternatives || []) { const r = interpret(a, options); if (r.type === 'command' || r.type === 'answer') return r; if (r.type !== 'none') last = r; }
    return last;
  }
  function parseYesNo(transcripts) {
    const list = Array.isArray(transcripts) ? transcripts : [transcripts];
    for (const t of list) {
      const text = norm(t); if (!text) continue;
      const no = NO.some((p) => has(text, p)); const yes = YES.some((p) => has(text, p));
      if (no && !yes) return 'no'; if (yes && !no) return 'yes';
    }
    return 'unknown';
  }

  const INTENT = {
    not_now: ['not now', 'later', 'postpone', 'maybe later', 'बाद में', 'अभी नहीं', 'இப்போது வேண்டாம்', 'பிறகு', 'பின்னர்'],
    no: ['no', 'nope', 'decline', 'नहीं', 'मना', 'इनकार', 'இல்லை', 'மறுக்கிறேன்', 'வேண்டாம்'],
    yes: ['yes', 'yeah', 'yep', 'start', 'begin', 'ok', 'okay', 'हाँ', 'हां', 'जी', 'शुरू', 'ஆம்', 'ஆமாம்', 'சரி', 'தொடங்கு', 'தொடங்கலாம்'],
  };
  /** Yes / Not now / No gate. Order matters: "अभी नहीं" and "இப்போது வேண்டாம்" are NOT a plain 'no'. */
  function parseIntent(transcripts) {
    const list = Array.isArray(transcripts) ? transcripts : [transcripts];
    for (const t of list) {
      const text = norm(t); if (!text) continue;
      if (INTENT.not_now.some((p) => has(text, p))) return 'not_now';
      const no = INTENT.no.some((p) => has(text, p)); const yes = INTENT.yes.some((p) => has(text, p));
      if (no && !yes) return 'no'; if (yes && !no) return 'yes';
    }
    return 'unknown';
  }

  // ------------------------------------------------------------------ browser wrappers
  const api = { LANG, norm, interpret, interpretAll, parseYesNo, parseIntent, findCommand };
  api.supported = () => {
    const w = typeof window !== 'undefined' ? window : {};
    return { stt: !!(w.SpeechRecognition || w.webkitSpeechRecognition), tts: !!w.speechSynthesis };
  };
  api.hasVoiceFor = (lang) => {
    if (!api.supported().tts) return false;
    const vs = window.speechSynthesis.getVoices();
    return vs.length === 0 ? null : vs.some((v) => v.lang.toLowerCase().startsWith((LANG[lang] || 'en-IN').slice(0, 2)));   // null = voice list not loaded yet
  };
  let _rec = null;
  api.cancel = () => {
    try { if (typeof window !== 'undefined' && window.speechSynthesis) window.speechSynthesis.cancel(); } catch (e) { /* ignore */ }
    try { if (_rec) { _rec.onresult = _rec.onerror = _rec.onend = null; _rec.abort(); } } catch (e) { /* ignore */ }
    _rec = null;
  };
  api.speak = (text, lang) => new Promise((resolve) => {
    if (!api.supported().tts) return resolve(false);
    const u = new window.SpeechSynthesisUtterance(text); u.lang = LANG[lang] || 'en-IN'; u.rate = 0.88;
    const voices = window.speechSynthesis.getVoices(); const v = voices.find((x) => x.lang.toLowerCase().startsWith(u.lang.slice(0, 2).toLowerCase()));
    if (v) u.voice = v;
    const guard = setTimeout(() => resolve(true), Math.max(4000, text.length * 120));        // some engines never fire onend
    u.onend = () => { clearTimeout(guard); resolve(true); }; u.onerror = () => { clearTimeout(guard); resolve(false); };
    window.speechSynthesis.speak(u);
  });
  /** Resolves {alternatives:[...]}, or null when nothing was heard. Rejects with Error('not-allowed') if the mic is blocked. */
  api.listen = (lang, timeoutMs = 9000) => new Promise((resolve, reject) => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition; if (!SR) return reject(new Error('unsupported'));
    const rec = new SR(); _rec = rec; rec.lang = LANG[lang] || 'en-IN'; rec.interimResults = false; rec.maxAlternatives = 4; rec.continuous = false;
    let settled = false; const done = (v, err) => { if (settled) return; settled = true; clearTimeout(t); try { rec.abort(); } catch (e) { /* ignore */ } err ? reject(err) : resolve(v); };
    const t = setTimeout(() => done(null), timeoutMs);
    rec.onresult = (e) => { const r = e.results[0]; const alts = []; for (let i = 0; i < r.length; i++) alts.push(r[i].transcript); done({ alternatives: alts }); };
    rec.onerror = (e) => (e.error === 'not-allowed' || e.error === 'service-not-allowed') ? done(null, new Error('not-allowed')) : done(null);
    rec.onend = () => done(null);
    try { rec.start(); } catch (e) { done(null); }
  });

  root.MSVoice = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
