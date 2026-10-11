"""Deployment profiles.

SIH26094 (verified against the official statement on the SIH 2026 portal) targets
victims / complainants under the SC/ST (Prevention of Atrocities) Act, 1989 who are
registered through NHAA 14566 / the Integrated Portal. A prison deployment is a
separate adaptation. The engine is the same; the profile swaps vocabulary,
groupings, identity-source wording and referral destinations.
"""
from typing import Dict, Any

_COMMON_DEST = [
    {"key": "counselling", "label": "Counselling (trained counsellor)", "clinical": True},
    {"key": "psychological", "label": "Psychological assessment", "clinical": True},
    {"key": "psychiatric", "label": "Medical / psychiatric assessment", "clinical": True},
    {"key": "tele_manas", "label": "Tele-MANAS (14416) linkage", "clinical": True},
]

PROFILES: Dict[str, Dict[str, Any]] = {
    "atrocity_victims": {
        "key": "atrocity_victims",
        "title": "Victims & complainants (SIH26094 · PoA Act · NHAA 14566 / Integrated Portal)",
        "short": "Victim & complainant wellbeing monitoring",
        "person_label": "Complainant",
        "id_prefix": "CMP",
        "id_example": "CMP1021",
        "group_label": "District",
        "groups": {"A": "District A (demo)", "B": "District B (demo)", "C": "District C (demo)"},
        "identity_source": "Simulated NHAA 14566 / Integrated Portal integration",
        "identity_note": "Production would use an approved interface with MoSJE; no live API is accessed here.",
        "context_label": "Case stage",
        "destinations": _COMMON_DEST + [
            {"key": "dmhp", "label": "District Mental Health Programme (DMHP)", "clinical": True},
            {"key": "victim_support", "label": "Victim support / legal-aid coordination (non-clinical)", "clinical": False},
        ],
        "strings": {
            "en": {"id_label": "Registration ID", "id_prompt": "Please enter your registration ID to continue.",
                   "id_placeholder": "Enter your ID", "subject": "check-in", "group": "District"},
            "ta": {"id_label": "பதிவு எண்", "id_prompt": "தொடர உங்கள் பதிவு எண்ணை உள்ளிடவும்.",
                   "id_placeholder": "உங்கள் எண்ணை உள்ளிடவும்", "subject": "நலன் சரிபார்ப்பு", "group": "மாவட்டம்"},
            "hi": {"id_label": "पंजीकरण आईडी", "id_prompt": "जारी रखने के लिए कृपया अपनी पंजीकरण आईडी दर्ज करें।",
                   "id_placeholder": "अपनी आईडी दर्ज करें", "subject": "वेलबीइंग चेक-इन", "group": "जिला"},
        },
    },
    "correctional": {
        "key": "correctional",
        "title": "Correctional-facility adaptation (inmates · simulated e-Prisons)",
        "short": "Inmate wellbeing monitoring (adaptation)",
        "person_label": "Inmate",
        "id_prefix": "INM",
        "id_example": "INM1021",
        "group_label": "Block",
        "groups": {"A": "Block A", "B": "Block B", "C": "Block C"},
        "identity_source": "Simulated e-Prisons integration",
        "identity_note": "Production would require an approved e-Prisons interface, data-sharing agreement, authentication and authorisation.",
        "context_label": "Custody context",
        "destinations": _COMMON_DEST + [
            {"key": "telemedicine", "label": "Telemedicine consultation", "clinical": True},
            {"key": "prison_medical", "label": "Prison medical officer", "clinical": True},
        ],
        "strings": {
            "en": {"id_label": "Inmate ID", "id_prompt": "Please enter your authorized inmate ID to continue.",
                   "id_placeholder": "Enter your ID", "subject": "check-in", "group": "Block"},
            "ta": {"id_label": "கைதி எண்", "id_prompt": "தொடர உங்கள் அங்கீகரிக்கப்பட்ட கைதி எண்ணை உள்ளிடவும்.",
                   "id_placeholder": "உங்கள் எண்ணை உள்ளிடவும்", "subject": "நலன் சரிபார்ப்பு", "group": "பிளாக்"},
            "hi": {"id_label": "बंदी आईडी", "id_prompt": "जारी रखने के लिए कृपया अपनी अधिकृत बंदी आईडी दर्ज करें।",
                   "id_placeholder": "अपनी आईडी दर्ज करें", "subject": "वेलबीइंग चेक-इन", "group": "ब्लॉक"},
        },
    },
}


def get_profile(key: str) -> Dict[str, Any]:
    if key not in PROFILES:
        raise ValueError(f"Unknown MANASETU_PROFILE '{key}'. Choose one of: {', '.join(PROFILES)}")
    return PROFILES[key]
