import unittest
import json
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
        self.assertGreaterEqual(len(EXERCISES), 20)
        media_dir = Path(__file__).resolve().parents[1] / "public" / "exercises"
        for exercise in EXERCISES.values():
            self.assertIn(exercise["videoKey"], VIDEO_CREDITS)
            video = VIDEO_CREDITS[exercise["videoKey"]]
            self.assertTrue((media_dir / Path(video["src"]).name).is_file())
            self.assertTrue((media_dir / Path(video["poster"]).name).is_file())

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
