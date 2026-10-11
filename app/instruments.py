"""Instrument registry and consent content.

IMPORTANT
---------
DEMO-WB-1 is a PLACEHOLDER written only so the interface and workflow can be tested.
It is NOT a validated instrument and its Tamil / Hindi wording has NOT been
professionally translated or clinically reviewed. Before any real use, qualified
mental-health professionals must select a validated instrument (and recall period,
response options, scoring rules and cut-offs) and register it here. The rest of the
system -- sessions, scoring status, baselines, trends, review workflow -- is
instrument-agnostic and keys everything on (instrument_id, major version).
"""
from typing import Dict, List, Optional, Tuple

import os
ACTIVE_INSTRUMENT = os.environ.get("MANASETU_INSTRUMENT", "DEMO-WB-1")      # DEMO-WB-1 (placeholder, 3 languages) | PHQ-9 (English only until approved translations are added)
LANGUAGES = [
    {"code": "ta", "name": "Tamil", "native": "தமிழ்"},
    {"code": "en", "name": "English", "native": "English"},
    {"code": "hi", "name": "Hindi", "native": "हिन्दी"},
]
LANGUAGE_CODES = {l["code"] for l in LANGUAGES}

_OPTIONS = {
    0: {"en": "Never", "ta": "ஒருபோதும் இல்லை", "hi": "कभी नहीं"},
    1: {"en": "Rarely", "ta": "அரிதாக", "hi": "बहुत कम"},
    2: {"en": "Sometimes", "ta": "சில சமயங்களில்", "hi": "कभी-कभी"},
    3: {"en": "Often", "ta": "அடிக்கடி", "hi": "अक्सर"},
    4: {"en": "Very often", "ta": "மிக அடிக்கடி", "hi": "बहुत अक्सर"},
}

_ITEMS = [
    {"id": "Q1", "domain": "Stress", "safety": False, "text": {
        "en": "During the past two weeks, how often did you feel stressed or under a lot of pressure?",
        "ta": "கடந்த இரண்டு வாரங்களில், நீங்கள் எவ்வளவு அடிக்கடி மன அழுத்தமாக அல்லது அதிக அழுத்தத்தில் இருப்பதாக உணர்ந்தீர்கள்?",
        "hi": "पिछले दो हफ़्तों में, आपने कितनी बार तनाव या बहुत दबाव महसूस किया?"}},
    {"id": "Q2", "domain": "Worry", "safety": False, "text": {
        "en": "During the past two weeks, how often did you find it hard to stop worrying?",
        "ta": "கடந்த இரண்டு வாரங்களில், கவலைப்படுவதை நிறுத்த உங்களுக்கு எவ்வளவு அடிக்கடி கடினமாக இருந்தது?",
        "hi": "पिछले दो हफ़्तों में, चिंता करना बंद करना आपके लिए कितनी बार कठिन रहा?"}},
    {"id": "Q3", "domain": "Sleep", "safety": False, "text": {
        "en": "During the past two weeks, how often did you have difficulty falling asleep or staying asleep?",
        "ta": "கடந்த இரண்டு வாரங்களில், தூக்கம் வருவதில் அல்லது தூக்கத்தில் நீடிப்பதில் உங்களுக்கு எவ்வளவு அடிக்கடி சிரமம் இருந்தது?",
        "hi": "पिछले दो हफ़्तों में, नींद आने या नींद बनाए रखने में आपको कितनी बार कठिनाई हुई?"}},
    {"id": "Q4", "domain": "Emotional wellbeing", "safety": False, "text": {
        "en": "During the past two weeks, how often did you feel sad, low, or down?",
        "ta": "கடந்த இரண்டு வாரங்களில், நீங்கள் எவ்வளவு அடிக்கடி சோகமாக, மனம் தளர்ந்து அல்லது வருத்தமாக உணர்ந்தீர்கள்?",
        "hi": "पिछले दो हफ़्तों में, आपने कितनी बार उदास, निराश या दुखी महसूस किया?"}},
    {"id": "Q5", "domain": "Coping", "safety": False, "text": {
        "en": "During the past two weeks, how often did you feel unable to cope with what was happening in your life?",
        "ta": "கடந்த இரண்டு வாரங்களில், உங்கள் வாழ்க்கையில் நடப்பவற்றைச் சமாளிக்க முடியாது என்று எவ்வளவு அடிக்கடி உணர்ந்தீர்கள்?",
        "hi": "पिछले दो हफ़्तों में, आपको कितनी बार लगा कि आप अपने जीवन में हो रही बातों का सामना नहीं कर पा रहे हैं?"}},
    {"id": "Q6", "domain": "Social support", "safety": False, "text": {
        "en": "During the past two weeks, how often did you feel alone, with nobody to turn to?",
        "ta": "கடந்த இரண்டு வாரங்களில், யாரிடமும் உதவி கேட்க முடியாமல் தனிமையாக இருப்பதாக எவ்வளவு அடிக்கடி உணர்ந்தீர்கள்?",
        "hi": "पिछले दो हफ़्तों में, आपने कितनी बार अकेलापन महसूस किया, जैसे कोई सहारा देने वाला न हो?"}},
    {"id": "Q7", "domain": "Interest and energy", "safety": False, "text": {
        "en": "During the past two weeks, how often did you have little interest or energy for your daily activities?",
        "ta": "கடந்த இரண்டு வாரங்களில், உங்கள் அன்றாட செயல்களில் ஆர்வம் அல்லது சக்தி குறைவாக இருந்ததாக எவ்வளவு அடிக்கடி உணர்ந்தீர்கள்?",
        "hi": "पिछले दो हफ़्तों में, आपको अपनी रोज़मर्रा की गतिविधियों में कितनी बार कम रुचि या कम ऊर्जा महसूस हुई?"}},
    {"id": "Q8", "domain": "Safety item", "safety": True, "text": {
        "en": "During the past two weeks, how often did you have thoughts that life is not worth living, or thoughts of harming yourself?",
        "ta": "கடந்த இரண்டு வாரங்களில், வாழ்க்கை வாழத் தகுதியற்றது என்ற எண்ணங்கள் அல்லது உங்களை நீங்களே காயப்படுத்திக்கொள்ளும் எண்ணங்கள் எவ்வளவு அடிக்கடி இருந்தன?",
        "hi": "पिछले दो हफ़्तों में, आपके मन में कितनी बार यह विचार आया कि जीवन जीने लायक नहीं है, या खुद को नुकसान पहुँचाने के विचार आए?"}},
]

INSTRUMENTS: Dict[str, dict] = {
    "DEMO-WB-1": {
        "translations": ["ta", "en", "hi"],
        "threshold_note": "None applies: the demonstration instrument has no validated cut-off. Placeholder thresholds only exercise the workflow.",
        "id": "DEMO-WB-1",
        "version": "0.1",
        "title": "Demonstration wellbeing check-in (PLACEHOLDER)",
        "validated": False,
        "status_note": ("Placeholder content for interface testing only. Not a validated clinical instrument. "
                        "Translations are demonstration wording pending professional review."),
        "recall_period": "past two weeks",
        "scale_min": 0, "scale_max": 4,
        "higher_means": "greater reported difficulty",
        "score_range": (0, 32),
        "options": _OPTIONS,
        "items": _ITEMS,
    }
}


_PHQ_OPTIONS = {0: {"en": "Not at all"}, 1: {"en": "Several days"}, 2: {"en": "More than half the days"}, 3: {"en": "Nearly every day"}}
_PHQ_ITEMS = [
    ("Q1", "Interest", False, "Little interest or pleasure in doing things"),
    ("Q2", "Mood", False, "Feeling down, depressed, or hopeless"),
    ("Q3", "Sleep", False, "Trouble falling or staying asleep, or sleeping too much"),
    ("Q4", "Energy", False, "Feeling tired or having little energy"),
    ("Q5", "Appetite", False, "Poor appetite or overeating"),
    ("Q6", "Self-worth", False, "Feeling bad about yourself \u2014 or that you are a failure or have let yourself or your family down"),
    ("Q7", "Concentration", False, "Trouble concentrating on things, such as reading the newspaper or watching television"),
    ("Q8", "Psychomotor", False, "Moving or speaking so slowly that other people could have noticed? Or the opposite \u2014 being so fidgety or restless that you have been moving around a lot more than usual"),
    ("Q9", "Safety item", True, "Thoughts that you would be better off dead or of hurting yourself in some way"),
]
# PHQ-9: Kroenke, Spitzer & Williams (2001), J Gen Intern Med 16(9):606-13. The PHQ screeners are published free of copyright
# restriction for reproduction and translation. Only the ENGLISH wording is included: official Hindi / Tamil versions must be
# obtained from the PHQ screeners site and added under "translations" by a clinician after a cultural-adaptation check.
INSTRUMENTS["PHQ-9"] = {
    "id": "PHQ-9", "version": "1.0", "title": "Patient Health Questionnaire-9 (PHQ-9)",
    "validated": True,
    "status_note": ("PHQ-9 is a published, validated depression-severity screener (primary-care populations). It has NOT been validated by this project "
                    "for victims of atrocities or people in custody, and it is a screener, not a diagnosis. Only English wording is installed."),
    "threshold_note": ("Published: severity bands 5/10/15/20, usual cut-point >=10 for further assessment (Kroenke 2001), minimal clinically important change "
                       "about 5 points (Lowe 2004), any non-zero item 9 needs clinical attention. Not validated by this project for this population."),
    "translations": ["en"],
    "recall_period": "last 2 weeks", "scale_min": 0, "scale_max": 3, "higher_means": "greater depressive symptom severity",
    "score_range": (0, 27), "options": _PHQ_OPTIONS,
    "stem": {"en": "Over the last 2 weeks, how often have you been bothered by the following problem?"},
    "items": [{"id": i, "domain": d, "safety": sf, "text": {"en": t}} for i, d, sf, t in _PHQ_ITEMS],
}


def available_languages(inst: Optional[dict] = None) -> List[str]:
    return list((inst or get_instrument())["translations"])


def major(version: str) -> str:
    return version.split(".")[0]


def get_instrument(instrument_id: str = ACTIVE_INSTRUMENT) -> dict:
    return INSTRUMENTS[instrument_id]


def item_ids(inst: dict) -> List[str]:
    return [i["id"] for i in inst["items"]]


def safety_item_id(inst: dict) -> Optional[str]:
    for i in inst["items"]:
        if i.get("safety"):
            return i["id"]
    return None


def public_view(lang: str, inst: Optional[dict] = None) -> dict:
    """What the kiosk is allowed to see: wording and options only (no domains / safety flags / scoring)."""
    inst = inst or get_instrument()
    lang = lang if lang in LANGUAGE_CODES else "en"
    if lang not in inst["translations"]:
        raise LookupError(f"{inst['id']} has no approved {lang} translation installed")
    return {
        "stem": inst.get("stem", {}).get(lang),
        "instrument_id": inst["id"], "instrument_version": inst["version"], "title": inst["title"],
        "validated": inst["validated"], "status_note": inst["status_note"], "language": lang,
        "options": [{"value": v, "label": o[lang]} for v, o in sorted(inst["options"].items())],
        # voice_ok=False: the sensitive item is never answered aloud (people nearby could hear it)
        "items": [{"id": i["id"], "text": i["text"][lang], "voice_ok": not i.get("safety", False)} for i in inst["items"]],
    }


def score_responses(responses: Dict[str, Optional[int]], inst: Optional[dict] = None) -> Tuple[Optional[int], str, int, int]:
    """Instrument-specific scoring (sum of all items). Returns (score, scoring_status, answered, total).

    Unanswered / skipped items are NEVER treated as zero. If any item is missing the instrument is
    not scored, because this placeholder has no approved rule for partial scoring."""
    inst = inst or get_instrument()
    ids = item_ids(inst)
    answered = sum(1 for q in ids if responses.get(q) is not None)
    if answered < len(ids):
        return None, "not_scored_incomplete", answered, len(ids)
    return sum(int(responses[q]) for q in ids), "scored", answered, len(ids)


# ------------------------------------------------------------------ consent
CONSENT_VERSION = "consent-v0.1-demo"

CONSENT = {
    "version": CONSENT_VERSION,
    "pending_review_note": {
        "en": "Demonstration wording. A real deployment needs legal, ethics and clinical review, and a "
              "process that accounts for the circumstances of people in custody or in a legal process.",
        "ta": "இது மாதிரி உரை. உண்மையான பயன்பாட்டிற்கு சட்ட, நெறிமுறை மற்றும் மருத்துவ மதிப்பாய்வு தேவை.",
        "hi": "यह केवल प्रदर्शन हेतु पाठ है। वास्तविक उपयोग से पहले कानूनी, नैतिक और चिकित्सीय समीक्षा आवश्यक है।",
    },
    "title": {"en": "Your Wellbeing and Privacy Matter", "ta": "உங்கள் நலனும் தனியுரிமையும் முக்கியம்",
              "hi": "आपका कल्याण और गोपनीयता महत्वपूर्ण हैं"},
    "sections": [
        {"id": "why", "heading": {"en": "Why this check-in is offered", "ta": "இந்த சரிபார்ப்பு ஏன் வழங்கப்படுகிறது", "hi": "यह चेक-इन क्यों दिया जाता है"},
         "body": {
             "en": "So the care team can notice changes in how you are feeling over time and connect you with support if you want or need it.",
             "ta": "காலப்போக்கில் நீங்கள் எப்படி உணர்கிறீர்கள் என்பதில் ஏற்படும் மாற்றங்களை பராமரிப்புக் குழு கவனித்து, தேவைப்பட்டால் உங்களுக்கு உதவியுடன் இணைக்க.",
             "hi": "ताकि देखभाल टीम समय के साथ आपकी भावनाओं में बदलाव को समझ सके और ज़रूरत होने पर आपको सहायता से जोड़ सके।"}},
        {"id": "what", "heading": {"en": "What is collected", "ta": "என்ன சேகரிக்கப்படுகிறது", "hi": "क्या जानकारी ली जाती है"},
         "body": {
             "en": "A few short questions about stress, worry, sleep, mood, coping and support. Your answers are saved with your ID, the date and the language you chose.",
             "ta": "மன அழுத்தம், கவலை, தூக்கம், மனநிலை, சமாளிப்பு மற்றும் ஆதரவு பற்றிய சில குறுகிய கேள்விகள். உங்கள் பதில்கள் உங்கள் எண், தேதி மற்றும் நீங்கள் தேர்ந்த மொழியுடன் சேமிக்கப்படும்.",
             "hi": "तनाव, चिंता, नींद, मनोदशा, सामना करने और सहारे के बारे में कुछ छोटे प्रश्न। आपके उत्तर आपकी आईडी, तारीख और चुनी हुई भाषा के साथ सहेजे जाते हैं।"}},
        {"id": "who", "heading": {"en": "Who can see it", "ta": "யார் பார்க்கலாம்", "hi": "इसे कौन देख सकता है"},
         "body": {
             "en": "Only authorised care and screening staff, and only what their role allows. Every time a record is opened, it is logged.",
             "ta": "அங்கீகரிக்கப்பட்ட பராமரிப்பு மற்றும் பரிசோதனை பணியாளர்கள் மட்டுமே, அவர்களின் பணிக்கு அனுமதிக்கப்பட்டதை மட்டும். ஒவ்வொரு முறை பதிவு திறக்கப்படும்போதும் அது பதிவு செய்யப்படும்.",
             "hi": "केवल अधिकृत देखभाल और स्क्रीनिंग कर्मचारी, और केवल उतना जितना उनकी भूमिका अनुमति देती है। हर बार रिकॉर्ड खोले जाने पर उसका लॉग बनता है।"}},
        {"id": "how", "heading": {"en": "How it is used", "ta": "எப்படி பயன்படுத்தப்படுகிறது", "hi": "इसका उपयोग कैसे होता है"},
         "body": {
             "en": "A computer programme compares your answers with your own earlier answers to suggest whether a person should look at your case. It does not diagnose anything. People review the suggestion and decide what happens next.",
             "ta": "உங்கள் முந்தைய பதில்களுடன் இப்போதைய பதில்களை ஒரு கணினி நிரல் ஒப்பிட்டு, ஒருவர் உங்கள் வழக்கைப் பார்க்க வேண்டுமா என்று பரிந்துரைக்கும். அது எதையும் கண்டறியாது. மனிதர்கள் பரிந்துரையை மதிப்பாய்வு செய்து அடுத்து என்ன என்பதை முடிவு செய்வார்கள்.",
             "hi": "एक कंप्यूटर प्रोग्राम आपके पहले के उत्तरों से आज के उत्तरों की तुलना करके सुझाव देता है कि कोई व्यक्ति आपके मामले को देखे या नहीं। यह कोई निदान नहीं करता। लोग सुझाव की समीक्षा करके आगे का निर्णय लेते हैं।"}},
        {"id": "stop", "heading": {"en": "If you stop or decline", "ta": "நிறுத்தினால் அல்லது மறுத்தால்", "hi": "यदि आप रुकते या मना करते हैं"},
         "body": {
             "en": "You may postpone, decline, or stop at any time, and you may skip any question. Declining is your choice and is not treated by the system as a sign of distress. A staff member can explain this to you if you ask.",
             "ta": "எந்த நேரத்திலும் ஒத்திவைக்கலாம், மறுக்கலாம் அல்லது நிறுத்தலாம்; எந்த கேள்வியையும் தவிர்க்கலாம். மறுப்பது உங்கள் விருப்பம்; அதை அமைப்பு மன உளைச்சலின் அறிகுறியாகக் கருதாது. நீங்கள் கேட்டால் ஒரு பணியாளர் விளக்குவார்.",
             "hi": "आप किसी भी समय स्थगित, मना या बंद कर सकते हैं, और किसी भी प्रश्न को छोड़ सकते हैं। मना करना आपका अधिकार है और सिस्टम इसे परेशानी का संकेत नहीं मानता। चाहें तो कोई कर्मचारी आपको यह समझा सकता है।"}},
        {"id": "dx", "heading": {"en": "Not a diagnosis", "ta": "இது நோய்கண்டறிதல் அல்ல", "hi": "यह निदान नहीं है"},
         "body": {
             "en": "This is a screening support tool, not a medical diagnosis. If you need to talk to someone urgently, please tell the nearest staff member right now.",
             "ta": "இது பரிசோதனை உதவிக் கருவி மட்டுமே; மருத்துவ நோய்கண்டறிதல் அல்ல. உடனடியாக ஒருவரிடம் பேச வேண்டுமெனில், இப்போதே அருகிலுள்ள பணியாளரிடம் சொல்லுங்கள்.",
             "hi": "यह एक स्क्रीनिंग सहायता उपकरण है, चिकित्सीय निदान नहीं। यदि आपको तुरंत किसी से बात करनी है, तो अभी निकटतम कर्मचारी को बताइए।"}},
    ],
    "acknowledgements": [
        {"id": "a1", "text": {
            "en": "I understand this check-in is voluntary and I can stop or skip questions.",
            "ta": "இந்த சரிபார்ப்பு விருப்பத்தின் பேரில் என்பதையும், நான் நிறுத்தலாம் அல்லது கேள்விகளைத் தவிர்க்கலாம் என்பதையும் புரிந்துகொள்கிறேன்.",
            "hi": "मैं समझता/समझती हूँ कि यह चेक-इन स्वैच्छिक है और मैं रुक सकता/सकती हूँ या प्रश्न छोड़ सकता/सकती हूँ।"}},
        {"id": "a2", "text": {
            "en": "I understand who can see my answers and how they may be used.",
            "ta": "என் பதில்களை யார் பார்க்கலாம், அவை எப்படி பயன்படுத்தப்படலாம் என்பதைப் புரிந்துகொள்கிறேன்.",
            "hi": "मैं समझता/समझती हूँ कि मेरे उत्तर कौन देख सकता है और उनका उपयोग कैसे हो सकता है।"}},
        {"id": "a3", "text": {
            "en": "I understand this is not a medical diagnosis.",
            "ta": "இது மருத்துவ நோய்கண்டறிதல் அல்ல என்பதைப் புரிந்துகொள்கிறேன்.",
            "hi": "मैं समझता/समझती हूँ कि यह चिकित्सीय निदान नहीं है।"}},
    ],
}


def consent_view(lang: str) -> dict:
    lang = lang if lang in LANGUAGE_CODES else "en"
    return {
        "version": CONSENT["version"], "language": lang,
        "title": CONSENT["title"][lang], "pending_review_note": CONSENT["pending_review_note"][lang],
        "sections": [{"id": s["id"], "heading": s["heading"][lang], "body": s["body"][lang]} for s in CONSENT["sections"]],
        "acknowledgements": [{"id": a["id"], "text": a["text"][lang]} for a in CONSENT["acknowledgements"]],
    }
