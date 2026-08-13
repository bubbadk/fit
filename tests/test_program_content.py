import unittest
import json
import hashlib
from pathlib import Path

from program_content import (
    EXERCISES,
    VIDEO_CREDITS,
    apply_program_structure,
    ensure_meal_safety,
    total_weeks,
)
import server


class ProgramContentTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "activity": "starter", "minutes": 25, "walk": True, "swim": True,
            "strength": True, "knees": False, "back": False, "mobility": "independent",
            "diet": "flex", "allergies": "", "dislikes": "", "cookingMinutes": 30,
        }
        self.plan = {
            "days": [
                {"day": day, "movement": {}, "meals": {kind: {"title": "Test", "ingredients": ["gulerod"], "portion": "1 portion"} for kind in ("breakfast", "lunch", "dinner", "snack")}}
                for day in range(1, 8)
            ]
        }

    def test_catalogue_has_stable_media_for_every_exercise(self):
        self.assertEqual(len(EXERCISES), 20)
        self.assertEqual(len(VIDEO_CREDITS), 20)
        media_dir = Path(__file__).resolve().parents[1] / "public" / "exercises"
        video_keys = []
        video_paths = []
        poster_paths = []
        source_pages = []
        video_hashes = []
        for exercise in EXERCISES.values():
            self.assertIn(exercise["videoKey"], VIDEO_CREDITS)
            video = VIDEO_CREDITS[exercise["videoKey"]]
            video_path = media_dir / Path(video["src"]).name
            poster_path = media_dir / Path(video["poster"]).name
            self.assertTrue(video_path.is_file())
            self.assertTrue(poster_path.is_file())
            video_keys.append(exercise["videoKey"])
            video_paths.append(video["src"])
            poster_paths.append(video["poster"])
            source_pages.append(video["source"])
            video_hashes.append(hashlib.sha256(video_path.read_bytes()).hexdigest())

        # One exercise means one demonstration. Reused keys, source clips or
        # files must fail before they can recreate the duplicated-video bug.
        self.assertEqual(len(video_keys), len(set(video_keys)))
        self.assertEqual(len(video_paths), len(set(video_paths)))
        self.assertEqual(len(poster_paths), len(set(poster_paths)))
        self.assertEqual(len(source_pages), len(set(source_pages)))
        self.assertEqual(len(video_hashes), len(set(video_hashes)))

    def test_program_is_real_multiweek_progression(self):
        week_one = apply_program_structure(self.plan, self.profile, 1, total_weeks(180))
        self.assertEqual(week_one["program"]["totalWeeks"], 26)
        self.assertEqual(len(week_one["strengthWorkouts"]), 2)
        self.assertGreaterEqual(len(week_one["strengthGuide"]), 8)
        self.assertEqual(len(week_one["exerciseLibrary"]), len(EXERCISES))
        self.assertEqual(sum(day["movement"]["type"] == "styrke" for day in week_one["days"]), 2)
        self.assertTrue(any(day["movement"]["type"] == "svømning" for day in week_one["days"]))
        muscles = {muscle for exercise in week_one["strengthGuide"] for muscle in exercise["muscleGroups"]}
        self.assertTrue({"lår", "baller", "bryst", "øvre ryg", "mave", "skuldre", "arme"}.issubset(muscles))

    def test_common_allergens_are_removed(self):
        self.profile["allergies"] = "gluten og laktose"
        self.plan["days"][0]["meals"]["breakfast"] = {
            "title": "Havregrød med skyr", "ingredients": ["havregryn", "mælk", "skyr"]
        }
        safe = ensure_meal_safety(self.plan, self.profile)
        text = str(safe["days"][0]["meals"]["breakfast"]).lower()
        for word in ("havregryn", "mælk", "skyr", "rugbrød"):
            self.assertNotIn(word, text)

    def test_thin_ai_recipe_is_replaced_with_real_instructions(self):
        plan = {
            "days": [{
                "meals": {
                    "dinner": {
                        "title": "Bagt torsk med kartofler og remoulade-dressing",
                        "ingredients": [
                            "200 g torskefilet", "300 g kartofler",
                            "150 g gulerødder og broccoli", "1 spsk let remoulade",
                            "citronsaft og persille",
                        ],
                        "portion": "½ grønt, ¼ fisk, ¼ kartofler",
                        "method": ["Tilbered råvarerne enkelt og brug portionsforslaget som pejlemærke."],
                        "prepMinutes": 45,
                    }
                }
            }]
        }
        upgraded = ensure_meal_safety(plan, self.profile)
        recipe = upgraded["days"][0]["meals"]["dinner"]
        self.assertGreaterEqual(len(recipe["method"]), 5)
        joined = " ".join(recipe["method"])
        self.assertIn("200 °C", joined)
        self.assertIn("10-14 minutter", joined)
        self.assertIn("60 °C", joined)
        self.assertNotIn("Tilbered råvarerne enkelt", joined)

    def test_catalogue_meals_have_quantities_and_full_methods(self):
        for kind in ("breakfast", "lunch", "dinner", "snack"):
            meal = server.safe_meal(kind, self.profile)
            plan = {"days": [{"meals": {kind: meal}}]}
            upgraded = ensure_meal_safety(plan, self.profile)["days"][0]["meals"][kind]
            self.assertGreaterEqual(len(upgraded["method"]), 4)
            self.assertTrue(any(char.isdigit() for item in upgraded["ingredients"] for char in item))

    def test_recipe_repair_respects_the_dish_name(self):
        cases = [
            ("Kyllingewok med grønt og ris", "wok", "Varm ovnen op til 200 °C."),
            ("Kyllingekarry med ris", "karry", "Varm ovnen op til 200 °C."),
            ("Fisk, rugbrød og råkost", "rugbrød", "Varm ovnen op til 200 °C."),
            ("Grøntsagssuppe med bønner", "suppe", "Tilbered råvarerne enkelt."),
            ("Rester efter tallerkenmodellen", "rester", "Tilbered råvarerne enkelt."),
        ]
        for title, expected_word, wrong_step in cases:
            plan = {"days": [{"meals": {"dinner": {
                "title": title,
                "ingredients": ["150 g protein", "200 g grøntsager", "60 g tilbehør"],
                "portion": "½ grønt, ¼ protein, ¼ tilbehør",
                "method": [wrong_step] * 4,
                "prepMinutes": 30,
            }}}]}
            recipe = ensure_meal_safety(plan, self.profile)["days"][0]["meals"]["dinner"]
            joined = " ".join(recipe["method"]).lower()
            self.assertIn(expected_word, joined)
            if expected_word in {"wok", "karry", "rugbrød"}:
                self.assertNotIn("varm ovnen", joined)

    def test_partial_ai_days_are_completed_before_email(self):
        partial = server.fallback_plan(self.profile)
        del partial["days"][0]["meals"]["breakfast"]
        partial["days"][1]["movement"] = {"type": "styrke"}
        completed = server.extract_json(json.dumps(partial, ensure_ascii=False), self.profile)
        self.assertTrue(completed["days"][0]["meals"]["breakfast"]["title"])
        self.assertTrue(completed["days"][1]["movement"]["title"])
        self.assertIsInstance(completed["days"][1]["movement"]["instructions"], list)


if __name__ == "__main__":
    unittest.main()
