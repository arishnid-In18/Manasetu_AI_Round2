# Instruments, thresholds and what is (and is not) evidence-based

Select the instrument with `MANASETU_INSTRUMENT` (`DEMO-WB-1` default, or `PHQ-9`). Rules are chosen per instrument (`analysis.rules_for`).

## PHQ-9 (installed, English wording only)
**Published** (used as-is): 9 items scored 0-3, total 0-27; severity bands at 5/10/15/20; usual cut-point >=10 (Kroenke, Spitzer & Williams, 2001, J Gen Intern Med 16:606);
minimal clinically important change ~5 points (Lowe et al., 2004); any non-zero item 9 needs clinical attention. The PHQ screeners are published free of copyright restriction for reproduction and translation.
**Project choices** (NOT published; need clinical sign-off): baseline = median of first 3 valid scores; persistence = 3 consecutive assessments >= baseline+5; sudden change = +10 vs previous;
trend slope >= 1/assessment and >= 5 total; item 9 >= 2 -> "Urgent Human Review"; persistent AND score >= 20 -> "Urgent Human Review".
**Limits:** validated for depression severity in primary-care populations, **not by this project for victims of atrocities or people in custody**; trauma-focused measures (e.g. PCL-5) may be more suitable.
**Translations:** official Hindi/Tamil texts could not be retrieved here, so they are deliberately NOT included and the kiosk disables those languages in PHQ-9 mode.
To add one: obtain the official version (phqscreeners.com), have a clinician check cultural adaptation, then add the item/option/stem strings under `translations` in `app/instruments.py` and add the language code to `"translations"`.
Hindi PHQ-9 cultural-adaptation work exists for specific groups (Bhardwaj et al., Indian J Palliat Care); Tamil needs checking.

## DEMO-WB-1 (default)
Placeholder content in 3 languages so the whole workflow can be demonstrated. Not validated. Thresholds are invented for the demo.

## What would make this "tested" clinically
A pre-registered study: clinicians choose the instrument and thresholds; translations are professionally back-translated and piloted; the rules are run on real, consented, de-identified histories
and compared with clinician judgement (sensitivity/specificity, false-alert burden, time-to-review); an ethics committee approves consent for people in custody or in legal proceedings.
