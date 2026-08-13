"""Curated program content for Fri Form.

AI writes the friendly weekly plan, while this module owns the safety-critical
exercise catalogue, progression and meal substitutions.  Keeping stable IDs
means the UI can always show the correct demonstration.
"""

from __future__ import annotations

import math
import re
from typing import Any


def _exercise(
    exercise_id: str,
    name: str,
    video_key: str,
    pattern: str,
    muscles: list[str],
    equipment: str,
    how: str,
    cues: list[str],
    easier: str,
    harder: str,
    caution: str = "Stop ved skarp smerte, svimmelhed eller usædvanligt ubehag.",
) -> dict[str, Any]:
    return {
        "id": exercise_id,
        "exercise": name,
        "videoKey": video_key,
        "pattern": pattern,
        "muscleGroups": muscles,
        "equipment": equipment,
        "how": how,
        "cues": cues,
        "easier": easier,
        "harder": harder,
        "caution": caution,
    }


EXERCISES = {
    item["id"]: item
    for item in [
        _exercise("chair-squat", "Kontrolleret squat", "squat", "ben", ["lår", "baller"], "Stol i nærheden ved behov", "Skub hoften roligt bagud, bøj knæene og rejs dig igen med vægten fordelt over hele foden.", ["Knæ følger tæernes retning", "Hold brystet løftet", "Kun så dybt som behageligt"], "Brug en stol som dybdemål eller hold let ved en støtte.", "Sænk dig lidt dybere med samme rolige kontrol."),
        _exercise("bodyweight-squat", "Bred squat", "bodyweight-squat", "ben", ["lår", "baller", "mave"], "Ingen", "Stå lidt bredere end hoftebredde, før hoften bagud og pres roligt op gennem hele foden.", ["Tæer og knæ peger samme vej", "Lang ryg", "Roligt tempo"], "Gør bevægelsen kortere eller hold ved en stol.", "Hold en let vægt ved brystet."),
        _exercise("wall-pushup", "Armbøjning mod væg", "wall", "pres", ["bryst", "skuldre", "arme"], "Væg", "Placér hænderne i brysthøjde, hold kroppen lang og sænk brystet roligt mod væggen.", ["Albuer let bagud", "Spænd let i maven", "Pres væggen væk"], "Stå tættere på væggen.", "Stå længere væk eller brug en solid køkkenbordskant."),
        _exercise("incline-pushup", "Armbøjning mod bord", "incline-pushup", "pres", ["bryst", "skuldre", "arme", "mave"], "Solid bordkant", "Hold kroppen i en lige linje, sænk brystet mod bordkanten og pres roligt tilbage.", ["Bordet må ikke kunne flytte sig", "Kroppen bevæges samlet", "Rolig udånding på vej op"], "Brug en væg.", "Brug en lavere, helt stabil støtte."),
        _exercise("seated-band-row", "Siddende træk med elastik", "seated-band-row", "træk", ["øvre ryg", "bagskulder", "arme"], "Træningselastik", "Sid højt, før elastikken sikkert omkring fødderne og træk albuerne roligt bagud.", ["Skuldre væk fra ørerne", "Saml skulderbladene let", "Slip langsomt frem"], "Brug en lettere elastik eller mindre bevægelse.", "Hold ét sekund i den bageste position."),
        _exercise("standing-band-pull", "Stående elastiktræk udad", "band", "træk", ["øvre ryg", "bagskulder", "arme"], "Træningselastik", "Hold elastikken foran brystet og træk hænderne roligt ud til siderne, til skulderbladene samles let.", ["Skuldre væk fra ørerne", "Bløde albuer", "Slip langsomt tilbage"], "Brug en lettere elastik eller kortere bevægelse.", "Hold ét sekund med elastikken trukket ud."),
        _exercise("high-plank", "Planke på hænder", "plank", "kropsstamme", ["mave", "ryg", "skuldre"], "Måtte", "Støt på hænder og tæer og hold kroppen lang med rolig vejrtrækning.", ["Pres gulvet let væk", "Hold hovedet i forlængelse af ryggen", "Stop før ryggen hænger"], "Lav planken på knæ eller mod et bord.", "Forlæng holdet fem sekunder."),
        _exercise("side-plank", "Sideplanke", "side-plank", "kropsstamme", ["mave", "sidekrop", "skuldre"], "Måtte", "Støt på underarm og fod, løft hoften og hold kroppen i en lang linje.", ["Albuen under skulderen", "Træk vejret roligt", "Hold hoften løftet"], "Bøj det nederste knæ og støt det i gulvet.", "Forlæng holdet eller løft den øverste arm."),
        _exercise("chair-mobility", "Siddende bevægelsespas", "chair", "mobilitet", ["skuldre", "hofter", "ryg"], "Stabil stol", "Følg de rolige siddende bevægelser og arbejd skiftevis med arme, overkrop og ben.", ["Sid højt", "Bevæg dig smertefrit", "Træk vejret frit"], "Gør bevægelserne mindre.", "Forlæng passet med en ekstra runde."),
        _exercise("jumping-jack", "Sprællemand", "jumping-jack", "puls", ["ben", "skuldre", "kondition"], "Ingen", "Hop fødderne ud til siderne, mens armene føres op, og saml dem roligt igen.", ["Land blødt", "Knæ følger tæerne", "Find et tempo du kan styre"], "Træd ét ben ud ad gangen uden hop.", "Lav bevægelsen lidt hurtigere uden at lande hårdt.", "Vælg versionen uden hop ved knæ-, hofte- eller bækkengener."),
        _exercise("glute-bridge", "Hofteløft", "bridge", "hofte", ["baller", "baglår", "mave"], "Måtte", "Lig med bøjede knæ, pres fødderne ned og løft hoften roligt, til kroppen føles lang.", ["Pres gennem hele foden", "Undgå at svaje", "Sænk langsomt"], "Løft kun hoften lidt.", "Hold to sekunder i toppen."),
        _exercise("sit-up", "Kontrolleret mavebøjning", "sit-up", "kropsstamme", ["mave", "hofter"], "Måtte", "Lig med bøjede knæ, spænd let i maven og løft overkroppen roligt uden at trække i nakken.", ["Se skråt op", "Pust ud på vej op", "Sænk kontrolleret"], "Løft kun skulderbladene fra gulvet.", "Gør vejen ned langsommere."),
        _exercise("step-up", "Step-up", "step", "ben", ["lår", "baller", "læg", "balance"], "Lav stabil kasse eller trappetrin", "Træd op med hele foden, stræk hoften og træd roligt ned igen.", ["Støtten må ikke vippe", "Kontroller vejen ned", "Hold overkroppen høj"], "Brug et lavere trin og gelænder.", "Hold en meget let vægt i hver hånd."),
        _exercise("reverse-lunge", "Baglæns udfald", "reverse-lunge", "ben", ["lår", "baller", "balance"], "Ingen", "Træd ét ben bagud, sænk dig kontrolleret og pres gennem den forreste fod tilbage til start.", ["Overkroppen høj", "Forreste knæ følger tæerne", "Kort skridtlængde er helt fint"], "Hold ved en stol og gør bevægelsen mindre.", "Gør skridtet lidt længere."),
        _exercise("calf-raise", "Hælløft", "calf", "underben", ["læg", "fødder", "balance"], "Stol eller væg ved behov", "Løft hælene roligt, find balancen og sænk kontrolleret.", ["Vægten over hele forfoden", "Ingen hop", "Stå højt"], "Hold ved en stol og løft mindre.", "Hold to sekunder på toppen."),
        _exercise("lateral-leg-raise", "Sidebenløft", "lateral-leg-raise", "ben", ["yderside hofte", "baller", "mave"], "Måtte", "Lig på siden og løft det øverste ben roligt uden at rulle hoften bagud.", ["Tæerne peger frem", "Lille kontrolleret løft", "Sænk langsomt"], "Bøj det nederste ben for mere støtte.", "Hold ét sekund i toppen."),
        _exercise("shoulder-press", "Siddende skulderpres", "shoulder", "pres", ["skuldre", "arme"], "To lette håndvægte eller vandflasker", "Sid højt og pres de lette vægte op uden at løfte skuldrene mod ørerne.", ["Start meget let", "Håndled over albuer", "Sænk roligt"], "Pres én arm ad gangen uden vægt.", "Brug en anelse mere vægt, hvis teknikken er stabil."),
        _exercise("lateral-raise", "Sideløft med håndvægte", "lateral-raise", "pres", ["skuldre", "arme"], "To lette håndvægte eller vandflasker", "Løft armene roligt ud til siderne til omtrent skulderhøjde og sænk igen.", ["Bløde albuer", "Ingen sving", "Skuldre væk fra ørerne"], "Brug ingen vægt eller løft lavere.", "Sænk vægtene på tre sekunder."),
        _exercise("biceps-curl", "Armbøjning med håndvægte", "biceps", "arme", ["arme"], "Håndvægte eller vandflasker", "Hold albuerne tæt ved siden og bøj armene uden at svinge kroppen.", ["Rolig vej ned", "Afslappede skuldre", "Neutral håndledsstilling"], "Brug mindre eller ingen vægt.", "Hold ét sekund på toppen."),
        _exercise("triceps-extension", "Tricepsstræk over hovedet", "triceps-extension", "arme", ["arme", "skuldre"], "Én let håndvægt", "Hold vægten over hovedet, bøj albuerne roligt og stræk armene igen uden at svaje.", ["Albuer peger frem", "Spænd let i maven", "Sænk kontrolleret"], "Lav bevægelsen uden vægt eller siddende.", "Gør sænkefasen langsommere."),
    ]
}


VIDEO_CREDITS = {
    "squat": {"src": "/exercises/chair-squat.mp4", "poster": "/exercises/chair-squat.webp", "title": "Kontrolleret squat", "credit": "Anna Shvets · Pexels", "source": "https://www.pexels.com/video/trainer-explaining-an-exercise-to-a-woman-4838146/"},
    "wall": {"src": "/exercises/wall-pushup.mp4", "poster": "/exercises/wall-pushup.webp", "title": "Armbøjning mod væg", "credit": "Ketut Subiyanto · Pexels", "source": "https://www.pexels.com/video/man-doing-a-wall-push-ups-on-the-outdoors-5034321/"},
    "plank": {"src": "/exercises/plank.mp4", "poster": "/exercises/plank.webp", "title": "Kontrolleret planke", "credit": "MART PRODUCTION · Pexels", "source": "https://www.pexels.com/video/a-woman-doing-a-plank-8836970/"},
    "band": {"src": "/exercises/resistance-band.mp4", "poster": "/exercises/resistance-band.webp", "title": "Træk med elastik", "credit": "Pexels", "source": "https://www.pexels.com/video/woman-exercising-using-exercise-band-4393123/"},
    "chair": {"src": "/exercises/chair-mobility.mp4", "poster": "/exercises/chair-mobility.webp", "title": "Rolig bevægelse på stol", "credit": "Pressmaster · Pexels", "source": "https://www.pexels.com/video/an-instructor-showing-elderly-some-exercise-steps-while-sitting-down-3196290/"},
    "bridge": {"src": "/exercises/glute-bridge.mp4", "poster": "/exercises/glute-bridge.webp", "title": "Hofteløft", "credit": "Polina Tankilevitch · Pexels", "source": "https://www.pexels.com/video/woman-doing-glute-bridge-exercise-6525487/"},
    "step": {"src": "/exercises/step-up.mp4", "poster": "/exercises/step-up.webp", "title": "Step-up", "credit": "Mikhail Nilov · Pexels", "source": "https://www.pexels.com/video/a-woman-doing-a-step-up-and-down-exercise-6739968/"},
    "calf": {"src": "/exercises/calf-raise.mp4", "poster": "/exercises/calf-raise.webp", "title": "Hælløft", "credit": "Gaurav Kumar · Pexels", "source": "https://www.pexels.com/video/intense-calf-workout-in-gym-setting-32115656/"},
    "shoulder": {"src": "/exercises/shoulder-press.mp4", "poster": "/exercises/shoulder-press.webp", "title": "Skulderpres", "credit": "JULLIAN PRODUCTION · Pexels", "source": "https://www.pexels.com/video/man-lifting-dumbbells-in-home-gym-36623781/"},
    "biceps": {"src": "/exercises/biceps-curl.mp4", "poster": "/exercises/biceps-curl.webp", "title": "Armbøjning med vægt", "credit": "MART PRODUCTION · Pexels", "source": "https://www.pexels.com/video/a-woman-doing-bicep-curls-at-home-8837117/"},
    "bodyweight-squat": {"src": "/exercises/bodyweight-squat.mp4", "poster": "/exercises/bodyweight-squat.webp", "title": "Bred squat", "credit": "Ketut Subiyanto · Pexels", "source": "https://www.pexels.com/video/woman-doing-squat-exercise-5034577/"},
    "incline-pushup": {"src": "/exercises/incline-pushup.mp4", "poster": "/exercises/incline-pushup.webp", "title": "Armbøjning mod bord", "credit": "Mikhail Nilov · Pexels", "source": "https://www.pexels.com/video/a-man-doing-incline-push-ups-6970145/"},
    "seated-band-row": {"src": "/exercises/seated-band-row.mp4", "poster": "/exercises/seated-band-row.webp", "title": "Siddende træk med elastik", "credit": "Kampus Production · Pexels", "source": "https://www.pexels.com/video/man-doing-seated-row-exercise-6022753/"},
    "side-plank": {"src": "/exercises/side-plank.mp4", "poster": "/exercises/side-plank.webp", "title": "Sideplanke", "credit": "Kampus Production · Pexels", "source": "https://www.pexels.com/video/a-man-doing-a-side-plank-6023266/"},
    "reverse-lunge": {"src": "/exercises/reverse-lunge.mp4", "poster": "/exercises/reverse-lunge.webp", "title": "Baglæns udfald", "credit": "ROMAN ODINTSOV · Pexels", "source": "https://www.pexels.com/video/woman-doing-lunges-exercise-8233047/"},
    "sit-up": {"src": "/exercises/sit-up.mp4", "poster": "/exercises/sit-up.webp", "title": "Kontrolleret mavebøjning", "credit": "Jill Burrow · Pexels", "source": "https://www.pexels.com/video/woman-doing-sit-ups-8893527/"},
    "lateral-leg-raise": {"src": "/exercises/lateral-leg-raise.mp4", "poster": "/exercises/lateral-leg-raise.webp", "title": "Sidebenløft", "credit": "SHVETS production · Pexels", "source": "https://www.pexels.com/video/a-woman-doing-a-lateral-leg-raise-exercise-6974513/"},
    "lateral-raise": {"src": "/exercises/lateral-raise.mp4", "poster": "/exercises/lateral-raise.webp", "title": "Sideløft med håndvægte", "credit": "Tima Miroshnichenko · Pexels", "source": "https://www.pexels.com/video/a-man-working-out-using-dumbbell-5319088/"},
    "triceps-extension": {"src": "/exercises/triceps-extension.mp4", "poster": "/exercises/triceps-extension.webp", "title": "Tricepsstræk over hovedet", "credit": "Pavel Danilyuk · Pexels", "source": "https://www.pexels.com/video/a-man-working-out-6296281/"},
    "jumping-jack": {"src": "/exercises/jumping-jack.mp4", "poster": "/exercises/jumping-jack.webp", "title": "Sprællemand", "credit": "RDNE Stock project · Pexels", "source": "https://www.pexels.com/video/women-doing-jumping-jacks-8402086/"},
}


PHASES = [
    (2, "Rolig start", "Lær bevægelserne og slut hvert pas med overskud."),
    (4, "Skab rytmen", "Gentag de gode vaner og gør planen nem at få gjort."),
    (8, "Byg videre", "Læg lidt til ad gangen på tid, gentagelser eller modstand."),
    (10_000, "Stærkere hverdag", "Variér træningen og beskyt den rytme, du har bygget."),
]


def total_weeks(program_days: int | None) -> int:
    return max(1, math.ceil((program_days or 30) / 7))


def phase_for_week(week: int) -> tuple[str, str]:
    for end, title, text in PHASES:
        if week <= end:
            return title, text
    return PHASES[-1][1], PHASES[-1][2]


def build_strength_program(profile: dict[str, Any], week: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    starter = week <= 2 or profile.get("activity") == "starter" or profile.get("mobility") in {"support", "limited"}
    knees = bool(profile.get("knees"))
    back = bool(profile.get("back"))
    ids = [
        "chair-squat" if starter or knees else "bodyweight-squat",
        "wall-pushup" if starter else "incline-pushup",
        "seated-band-row" if starter or back else "standing-band-pull",
        "high-plank" if starter or back else "side-plank",
        "chair-mobility" if starter or knees else "step-up",
        "glute-bridge",
        "calf-raise" if starter else "reverse-lunge",
        "shoulder-press" if starter or back else "lateral-raise",
    ]
    if week >= 5:
        ids.append("biceps-curl" if starter else "triceps-extension")
    sets = 2 if week <= 2 else 3
    reps = "6-10" if week <= 2 else "8-12"
    hold = "15-20 sek." if week <= 2 else "20-30 sek."
    guide = []
    for exercise_id in ids:
        item = dict(EXERCISES[exercise_id])
        item["sets"] = str(sets)
        item["reps"] = hold if "plank" in exercise_id else reps
        guide.append(item)
    workouts = [
        {"id": "A", "title": "Hele kroppen A", "exerciseIds": ids[:6], "rounds": sets, "restSeconds": 75 if week <= 2 else 60},
        {"id": "B", "title": "Hele kroppen B", "exerciseIds": [ids[0], ids[2], ids[4], ids[6], ids[7], ids[3]], "rounds": sets, "restSeconds": 75 if week <= 2 else 60},
    ]
    return guide, workouts


LESSON_BANK = [
    ("Små skridt slår perfekte dage", "Vælg den mindste version, du også kan gøre på en travl dag."),
    ("Sult er information", "Spis langsomt og læg mærke til, hvornår du er behageligt mæt."),
    ("Plan B tæller", "Halv tid eller en lettere variant holder vanen levende."),
    ("Protein og grønt først", "Lad de to dele få plads, før du fylder resten af tallerkenen."),
    ("Se på flere uger", "Vægt svinger naturligt. Retningen er vigtigere end en enkelt måling."),
    ("Gør det nemt at vælge godt", "Læg sko frem og hav et enkelt måltid klar til travle dage."),
    ("En dårlig dag nulstiller intet", "Næste måltid eller næste gåtur er et nyt, lille valg."),
]


def apply_program_structure(plan: dict[str, Any], profile: dict[str, Any], week: int, weeks: int) -> dict[str, Any]:
    week = max(1, min(week, weeks))
    phase, phase_text = phase_for_week(week)
    guide, workouts = build_strength_program(profile, week)
    plan["program"] = {
        "currentWeek": week,
        "totalWeeks": weeks,
        "phase": phase,
        "phaseText": phase_text,
        "progression": "Øg kun én ting ad gangen: lidt mere tid, 1-2 gentagelser eller en sværere variant.",
    }
    plan["strengthGuide"] = guide if profile.get("strength") else []
    plan["strengthWorkouts"] = workouts if profile.get("strength") else []
    plan["exerciseLibrary"] = []
    if profile.get("strength"):
        for exercise in EXERCISES.values():
            library_item = dict(exercise)
            library_item["sets"] = "2-3"
            library_item["reps"] = "8-12" if "plank" not in exercise["id"] else "15-30 sek."
            plan["exerciseLibrary"].append(library_item)
    plan["dailyLessons"] = [
        {"day": index + 1, "title": title, "text": text}
        for index, (title, text) in enumerate(LESSON_BANK)
    ]
    plan["weeklyTargets"] = {
        "strengthSessions": 2 if profile.get("strength") else 0,
        "walkMinutes": max(0, min(210, (int(profile.get("minutes", 20)) + (week - 1) * 3) * (3 if profile.get("walk") else 0))),
        "swimSessions": 1 if profile.get("swim") else 0,
        "recoveryDays": 1,
    }
    _shape_movements(plan, profile, week, workouts)
    return plan


def _shape_movements(plan: dict[str, Any], profile: dict[str, Any], week: int, workouts: list[dict[str, Any]]) -> None:
    days = plan.get("days", [])
    if len(days) != 7:
        return
    base = int(profile.get("minutes", 20))
    walk_minutes = min(75, base + max(0, week - 1) * 3)
    if profile.get("walk"):
        for index, factor in ((0, 0.75), (3, 1.0), (5, 1.15)):
            minutes = max(10, round(walk_minutes * factor / 5) * 5)
            days[index]["movement"] = {"type": "gåtur", "title": "Gåtur i snakketempo", "minutes": minutes, "intensity": "moderat – du kan tale i hele sætninger", "instructions": ["Start med 3 rolige minutter.", "Find et tempo du kan holde uden at hive efter vejret.", "Slut roligt og notér, hvordan kroppen havde det."], "alternative": f"Del turen i to gange {max(5, minutes // 2)} minutter."}
    if profile.get("strength"):
        for index, workout in zip((1, 4), workouts):
            days[index]["movement"] = {"type": "styrke", "title": workout["title"], "workoutId": workout["id"], "minutes": min(base, 40), "intensity": "roligt og kontrolleret", "instructions": [f"Lav {workout['rounds']} runder af øvelserne i pas {workout['id']}.", f"Hold cirka {workout['restSeconds']} sekunders pause efter behov.", "Stop med 2-3 gode gentagelser i reserve."], "alternative": "Lav én runde eller de første fire øvelser."}
    if profile.get("swim"):
        swim_minutes = min(60, base + max(0, week - 1) * 2)
        days[2]["movement"] = {"type": "svømning", "title": "Roligt intervalpas i vand", "minutes": swim_minutes, "intensity": "roligt til moderat", "instructions": ["Varm op i fem minutter.", "Skift mellem to rolige baner og en kort pause.", "Slut med meget roligt tempo."], "alternative": "Gå roligt i vandet eller svøm halvdelen af tiden."}
    days[6]["movement"] = {"type": "restitution", "title": "Fri eller rolig bevægelse", "minutes": 10, "intensity": "meget let", "instructions": ["Vælg hvile eller en helt rolig tur.", "Målet er at føle dig bedre bagefter end før."], "alternative": "Fuld hvile er også en del af planen."}


MEAL_SWAPS = {
    "breakfast": [
        {"title": "Havregrød med bær", "ingredients": ["havregryn", "mælk eller plantedrik", "bær", "skyr eller sojayoghurt"], "portion": "1 skål med en håndfuld bær", "method": ["Kog havregryn med væske.", "Top med bær og en skefuld skyr."], "prepMinutes": 8, "diets": ["flex", "vegetarian", "pescetarian"]},
        {"title": "Rugbrød med æg og tomat", "ingredients": ["rugbrød", "æg", "tomat", "purløg"], "portion": "1-2 skiver efter sult", "method": ["Kog eller steg ægget.", "Servér på rugbrød med tomat."], "prepMinutes": 10, "diets": ["flex", "vegetarian", "pescetarian"]},
        {"title": "Skyrskål med frugt og kerner", "ingredients": ["skyr eller sojayoghurt", "frugt", "græskarkerner", "havregryn"], "portion": "1 skål", "method": ["Skær frugten.", "Saml det hele i en skål."], "prepMinutes": 5, "diets": ["flex", "vegetarian", "pescetarian"]},
    ],
    "lunch": [
        {"title": "Rugbrød med æg og sprødt grønt", "ingredients": ["rugbrød", "æg", "gulerod", "agurk"], "portion": "2 åbne madder og grønt ved siden af", "method": ["Læg æg på rugbrødet.", "Servér grøntsager ved siden af."], "prepMinutes": 8, "diets": ["flex", "vegetarian", "pescetarian"]},
        {"title": "Bønnesalat med kartofler", "ingredients": ["kogte kartofler", "bønner", "kål", "tomat", "rapsolie", "citron"], "portion": "1 stor skål", "method": ["Skær kartofler og grønt.", "Vend med bønner, citron og lidt olie."], "prepMinutes": 12, "diets": ["flex", "vegetarian", "pescetarian"]},
        {"title": "Tunsalat på rugbrød", "ingredients": ["tun", "skyr", "majs", "agurk", "rugbrød"], "portion": "2 åbne madder", "method": ["Rør tun med skyr og grønt.", "Fordel på rugbrød."], "prepMinutes": 8, "diets": ["flex", "pescetarian"]},
    ],
    "dinner": [
        {"title": "Kylling, kartofler og ovngrønt", "ingredients": ["kylling", "kartofler", "broccoli", "gulerod", "rapsolie"], "portion": "½ grønt, ¼ kylling, ¼ kartofler", "method": ["Skær kartofler og grønt og vend med lidt olie.", "Bag sammen med kyllingen, til den er gennemstegt."], "prepMinutes": 35, "diets": ["flex"]},
        {"title": "Lun linsesalat med fuldkornsris", "ingredients": ["linser", "fuldkornsris", "spidskål", "peberfrugt", "citron"], "portion": "½ grønt, ¼ linser, ¼ ris", "method": ["Kog risene.", "Vend med linser og snittet grønt."], "prepMinutes": 25, "diets": ["flex", "vegetarian", "pescetarian"]},
        {"title": "Ovnbagt fisk med rodfrugter", "ingredients": ["fisk", "kartofler", "gulerod", "kål", "citron"], "portion": "½ grønt, ¼ fisk, ¼ kartofler", "method": ["Bag rodfrugterne næsten møre.", "Læg fisken ved de sidste 12-15 minutter."], "prepMinutes": 35, "diets": ["flex", "pescetarian"]},
        {"title": "Bønnegryde med grøntsager", "ingredients": ["kidneybønner", "hakkede tomater", "gulerod", "peberfrugt", "fuldkornsris"], "portion": "En mellemstor skål med ekstra grønt", "method": ["Svits grøntsagerne kort.", "Tilsæt tomat og bønner og lad gryden simre."], "prepMinutes": 25, "diets": ["flex", "vegetarian", "pescetarian"]},
        {"title": "Fuldkornspasta med linsebolognese", "ingredients": ["fuldkornspasta", "røde linser", "hakkede tomater", "gulerod", "løg"], "portion": "½ grøntsagssauce og ½ pasta", "method": ["Kog pastaen.", "Lad linser og grøntsager simre i tomatsaucen."], "prepMinutes": 30, "diets": ["flex", "vegetarian", "pescetarian"]},
    ],
    "snack": [
        {"title": "Frugt og skyr", "ingredients": ["frugt", "skyr eller sojayoghurt"], "portion": "1 frugt og en lille skål", "method": ["Servér kun, hvis du er fysisk sulten."], "prepMinutes": 2, "diets": ["flex", "vegetarian", "pescetarian"]},
        {"title": "Grøntsagsstænger med hummus", "ingredients": ["gulerod", "agurk", "hummus"], "portion": "1 håndfuld grønt og 2 spsk hummus", "method": ["Skær grøntsagerne og servér med hummus."], "prepMinutes": 5, "diets": ["flex", "vegetarian", "pescetarian"]},
    ],
}


ALLERGEN_WORDS = {
    "gluten": ["rugbrød", "pasta", "havregryn", "fuldkorn", "brød"],
    "laktose": ["skyr", "mælk", "yoghurt", "ost"],
    "mælk": ["skyr", "mælk", "yoghurt", "ost"],
    "æg": ["æg"],
    "fisk": ["fisk", "tun", "laks", "torsk"],
    "nød": ["nød", "mandel", "peanut", "jordnød"],
}


def _blocked_words(profile: dict[str, Any]) -> list[str]:
    text = f"{profile.get('allergies', '')} {profile.get('dislikes', '')}".lower()
    words: list[str] = []
    for marker, related in ALLERGEN_WORDS.items():
        if marker in text:
            words.extend(related)
    for raw in re.split(r"[,;/]", text):
        raw = raw.strip()
        if len(raw) >= 3:
            words.append(raw)
    return sorted(set(words))


def meal_conflicts(meal: dict[str, Any], profile: dict[str, Any]) -> bool:
    haystack = " ".join([str(meal.get("title", "")), *map(str, meal.get("ingredients", []))]).lower()
    return any(word in haystack for word in _blocked_words(profile))


def meal_options(kind: str, profile: dict[str, Any]) -> list[dict[str, Any]]:
    diet = profile.get("diet", "flex")
    return [dict(meal) for meal in MEAL_SWAPS.get(kind, []) if diet in meal["diets"] and not meal_conflicts(meal, profile)]


def safe_meal(kind: str, profile: dict[str, Any], avoid_title: str = "") -> dict[str, Any]:
    options = meal_options(kind, profile)
    for meal in options:
        if meal["title"] != avoid_title:
            meal.pop("diets", None)
            return meal
    # Conservative last resort when a free-text restriction removes the catalogue.
    return {"title": "Dit kendte sikre måltid", "ingredients": ["Råvarer du ved, du tåler"], "portion": "Brug tallerkenmodellen og stop behageligt mæt", "method": ["Vælg et velkendt måltid, der passer til dine allergier og aftaler med din behandler."], "prepMinutes": 10}


def ensure_meal_safety(plan: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    for day in plan.get("days", []):
        for kind, meal in list(day.get("meals", {}).items()):
            if not isinstance(meal, dict) or meal_conflicts(meal, profile):
                day["meals"][kind] = safe_meal(kind, profile)
            else:
                meal.setdefault("method", ["Tilbered råvarerne enkelt og brug portionsforslaget som pejlemærke."])
                meal.setdefault("prepMinutes", int(profile.get("cookingMinutes", 25)) if kind == "dinner" else 10)
    return plan
