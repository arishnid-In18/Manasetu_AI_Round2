# Demo script (~6 minutes)

Start: `.\run.ps1` (victims profile) · accounts: `officer1`/`Officer#2026`, `clinician1`/`Clinician#2026`, `admin1`/`Admin#2026`.

1. **Problem (30 s)** – SIH26094 beneficiaries are victims/complainants; existing systems track legal compliance, not wellbeing.
2. **Mock integration (45 s)** – Kiosk → Begin → enter `CMP9999` (friendly error) → `CMP1051` (unavailable: same message, nothing revealed) → `CMP1021`
   → profile appears (Ravi Kumar, District B, Tamil auto-selected). Point at "Identity source: Simulated …".
3. **Choice + consent (45 s)** – "Not now" and "No" are recorded without any score. Choose **Yes** → language → consent (3 acknowledgements;
   "ask a staff member" alternative).
3b. **Voice (45 s, Chrome/Edge)** – on the choice screen press *Answer by voice*; on a question press *Voice assistant* → accept the privacy notice → answer by saying the option or its number; the assistant reads it back. The sensitive last question is touch-only.
4. **Check-in (60 s)** – answer 8 questions; show read-aloud, "prefer not to answer", review screen blocking unanswered items. Submit with total **≥10**.
   The person sees only a thank-you: no score.
5. **Longitudinal comparison (90 s)** – sign in `clinician1` → search `CMP1021`. Previous 4, 4, 5, 6; baseline 4; new score; trend; "Why was this case flagged?";
   data quality; "Clinical diagnosis: Not provided by the AI". (Score 7–9 → Monitor; ≥10 → Follow-up recommended.)
6. **Urgent path (45 s)** – red banner → `CMP1003` (safety item) → cannot be dismissed; cleared only by *Record Human Review*.
7. **Human follow-up (60 s)** – on `CMP1016`: record review → create referral (status "recommended") → schedule follow-up; clinician advances the stage; officer cannot.
8. **Governance (30 s)** – `officer1` cannot open block C (404); `admin1` cannot open cases; Audit log → *Verify chain*.

Other IDs: `CMP1019` urgent (handled) · `CMP1002` pipeline mid-way · `CMP1013/1035/1047` high baseline stays high · `CMP1043` two declines (administrative welfare-check flag only) ·
`CMP1025/1038/1049` incomplete history · `CMP1007` no assessment yet · `CMP1011` single high result.
Inmate version: `.\run.ps1 -Profile correctional` → IDs `INM1001–INM1050`.
