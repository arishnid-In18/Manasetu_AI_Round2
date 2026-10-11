// Run:  node --test tests/        (matcher logic only; real microphones / voices cannot be tested here)
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const V = createRequire(import.meta.url)('../static/voice.js');

const OPT = {
  en: ['Never', 'Rarely', 'Sometimes', 'Often', 'Very often'],
  ta: ['ஒருபோதும் இல்லை', 'அரிதாக', 'சில சமயங்களில்', 'அடிக்கடி', 'மிக அடிக்கடி'],
  hi: ['कभी नहीं', 'बहुत कम', 'कभी-कभी', 'अक्सर', 'बहुत अक्सर'],
};
const opts = (l) => OPT[l].map((label, value) => ({ value, label }));
const val = (t, l) => { const r = V.interpret(t, opts(l)); return r.type === 'answer' ? r.value : r.type === 'command' ? 'cmd:' + r.name : r.type; };

test('English answers by label, longest label wins', () => {
  assert.equal(val('never', 'en'), 0); assert.equal(val('Rarely.', 'en'), 1); assert.equal(val('sometimes', 'en'), 2);
  assert.equal(val('often', 'en'), 3); assert.equal(val('very often', 'en'), 4); assert.equal(val('I would say very often', 'en'), 4);
});
test('English answers by option number (digits and words)', () => {
  assert.equal(val('1', 'en'), 0); assert.equal(val('option two', 'en'), 1); assert.equal(val('three', 'en'), 2); assert.equal(val('number 5', 'en'), 4);
});
test('Hindi answers by label and number (incl. hyphenated and Devanagari digits)', () => {
  assert.equal(val('कभी नहीं', 'hi'), 0); assert.equal(val('बहुत कम', 'hi'), 1); assert.equal(val('कभी कभी', 'hi'), 2);
  assert.equal(val('अक्सर', 'hi'), 3); assert.equal(val('बहुत अक्सर', 'hi'), 4);
  assert.equal(val('तीन', 'hi'), 2); assert.equal(val('पाँच', 'hi'), 4); assert.equal(val('३', 'hi'), 2);
});
test('Tamil answers by label and number', () => {
  assert.equal(val('ஒருபோதும் இல்லை', 'ta'), 0); assert.equal(val('அரிதாக', 'ta'), 1); assert.equal(val('சில சமயங்களில்', 'ta'), 2);
  assert.equal(val('அடிக்கடி', 'ta'), 3); assert.equal(val('மிக அடிக்கடி', 'ta'), 4);
  assert.equal(val('நான்கு', 'ta'), 3); assert.equal(val('ஐந்து', 'ta'), 4); assert.equal(val('௨', 'ta'), 1);
});
test('commands are recognised in all three languages and beat answers', () => {
  for (const [t, c] of [['stop', 'stop'], ['repeat', 'repeat'], ['go back', 'back'], ['skip', 'skip'], ['next', 'next'], ['prefer not to answer', 'skip'],
    ['फिर से', 'repeat'], ['बंद करो', 'stop'], ['पीछे', 'back'], ['अगला', 'next'], ['उत्तर नहीं देना', 'skip'],
    ['மீண்டும்', 'repeat'], ['நிறுத்து', 'stop'], ['முந்தைய', 'back'], ['பதிலளிக்க விரும்பவில்லை', 'skip']])
    assert.equal(val(t, 'en'), 'cmd:' + c, t);
});
test('ambiguous, unknown and empty input are never guessed', () => {
  assert.equal(val('one two', 'en'), 'ambiguous'); assert.equal(val('banana', 'en'), 'unknown'); assert.equal(val('', 'en'), 'none');
  assert.equal(val('7', 'en'), 'unknown'); assert.equal(val('பேசு', 'ta'), 'unknown');
});
test('interpretAll uses the first useful recogniser alternative', () => {
  const r = V.interpretAll(['umm', 'sometimes', 'often'], opts('en')); assert.deepEqual([r.type, r.value], ['answer', 2]);
  assert.equal(V.interpretAll([], opts('en')).type, 'none');
});
test('yes / no parsing in three languages', () => {
  for (const y of ['yes', 'yeah correct', 'हाँ', 'जी ठीक', 'ஆம்', 'ஆமாம்', 'சரி']) assert.equal(V.parseYesNo(y), 'yes', y);
  for (const n of ['no', 'nope', 'नहीं', 'गलत', 'இல்லை', 'வேண்டாம்']) assert.equal(V.parseYesNo(n), 'no', n);
  assert.equal(V.parseYesNo('maybe'), 'unknown'); assert.equal(V.parseYesNo(['', 'yes']), 'yes');
});
test('short Indic words match whole words only ("ना" must not fire inside "नाम")', () => {
  assert.equal(V.parseYesNo('मेरा नाम'), 'unknown'); assert.equal(V.parseYesNo('ना'), 'no');
});
test('"yes and no" together is not guessed', () => { assert.equal(V.parseYesNo('yes no'), 'unknown'); });

test('Yes / Not now / No gate in three languages ("not now" is never read as a plain "no")', () => {
  for (const [x, w] of [['yes', 'yes'], ['start', 'yes'], ['हाँ', 'yes'], ['ஆம்', 'yes'], ['not now', 'not_now'], ['later', 'not_now'], ['अभी नहीं', 'not_now'], ['बाद में', 'not_now'],
    ['இப்போது வேண்டாம்', 'not_now'], ['no', 'no'], ['decline', 'no'], ['नहीं', 'no'], ['இல்லை', 'no']]) assert.equal(V.parseIntent(x), w, x);
  assert.equal(V.parseIntent('banana'), 'unknown'); assert.equal(V.parseIntent('yes no'), 'unknown');
});
