import unittest

from ebta_engine.procedures.candidate_matrix import build_candidate_matrix
from ebta_engine.procedures.complexity_selection import select_complexity
from ebta_engine.procedures.ml_manifest import build_ml_manifest
from ebta_engine.procedures.optimization import optimize_on_train
from ebta_engine.procedures.search_space import build_search_space_snapshot


class Sop06ProcedureTests(unittest.TestCase):
    def _space(self):
        return build_search_space_snapshot(
            "FAM-SOP06",
            "FOLD-001",
            {"complexity": [1, 2], "lookback": [5, 10]},
            base_spec={"logic": "moving_average"},
        )

    def test_search_space_snapshot_is_deterministic(self):
        first = self._space()
        second = self._space()
        self.assertEqual(first["canonical_hash"], second["canonical_hash"])
        self.assertEqual(first["candidate_count"], 4)
        self.assertEqual(
            [candidate["candidate_id"] for candidate in first["candidates"]],
            [candidate["candidate_id"] for candidate in second["candidates"]],
        )

    def test_search_space_counts_strategy_asset_pairs(self):
        space = build_search_space_snapshot(
            "FAM-ASSET",
            "FOLD-001",
            {"asset": ["EURUSD", "XAUUSD"], "complexity": [1, 2], "lookback": [5]},
            base_spec={"logic": "moving_average"},
            asset_universe=["EURUSD", "XAUUSD"],
            asset_selection_axis="asset",
            asset_selection_rule="evaluate_all_declared_assets",
        )
        self.assertEqual(space["candidate_count"], 4)
        self.assertEqual(space["asset_candidate_count"], {"EURUSD": 2, "XAUUSD": 2})
        self.assertEqual(set(space["candidate_asset_map"].values()), {"EURUSD", "XAUUSD"})
        self.assertTrue(all(candidate["asset"] in {"EURUSD", "XAUUSD"} for candidate in space["candidates"]))

    def test_search_space_rejects_missing_asset_universe_member(self):
        with self.assertRaises(ValueError):
            build_search_space_snapshot(
                "FAM-ASSET",
                "FOLD-001",
                {"asset": ["EURUSD"], "complexity": [1]},
                asset_universe=["EURUSD", "XAUUSD"],
                asset_selection_axis="asset",
            )

    def test_train_optimization_selects_representative_per_complexity(self):
        space = self._space()
        scores = {
            candidate["candidate_id"]: index / 10
            for index, candidate in enumerate(space["candidates"], start=1)
        }
        report = optimize_on_train(space, scores)
        self.assertEqual(len(report["representatives"]), 2)
        self.assertTrue(all(item["status"] == "EVALUATED" for item in report["evaluations"]))

    def test_ml_manifest_requires_train_only_transforms(self):
        manifest = build_ml_manifest(
            "ML-PILOT",
            train_segment="Train_k",
            features=["ret_1", "vol_5"],
            transformations=[{"name": "scale", "fit_segment": "Train_k"}],
            hyperparameters={"depth": 2},
            seeds=[7],
            complexity_levels=[1, 2],
            selection_rule="max_test_score",
        )
        self.assertEqual(manifest["features"], ["ret_1", "vol_5"])
        self.assertTrue(manifest["manifest_id"].startswith("ML-"))
        with self.assertRaises(ValueError):
            build_ml_manifest(
                "ML-BAD",
                train_segment="Train_k",
                features=["ret_1"],
                transformations=[{"name": "scale", "fit_segment": "Test_k"}],
                hyperparameters={},
                seeds=[1],
                complexity_levels=[1],
                selection_rule="max_test_score",
            )

    def test_complexity_selection_uses_test_max_then_tie_breaks(self):
        representatives = [
            {"candidate_id": "CAND-HIGH", "complexity": 3, "stability": 1, "turnover": 2, "cost": 2, "exposure": 2},
            {"candidate_id": "CAND-LOW", "complexity": 1, "stability": 1, "turnover": 2, "cost": 2, "exposure": 2},
        ]
        report = select_complexity(representatives, {"CAND-HIGH": 0.2, "CAND-LOW": 0.2})
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["selected_candidate_id"], "CAND-LOW")
        with self.assertRaises(ValueError):
            select_complexity(representatives, {"CAND-HIGH": 0.2}, test_segment="OOS_k")

    def test_complexity_selection_returns_no_model_without_admissible_candidates(self):
        report = select_complexity([{"candidate_id": "CAND-X", "complexity": 1}], {})
        self.assertEqual(report["status"], "NO_MODEL")
        self.assertIsNone(report["selected_candidate_id"])

    def test_candidate_matrix_requires_complete_influential_family(self):
        matrix = build_candidate_matrix(
            {"CAND-A": [0.1, 0.2], "CAND-B": [0.0, -0.1]},
            dates=["2022-01-03", "2022-01-04"],
            influential_candidates=["CAND-A", "CAND-B"],
        )
        self.assertEqual(matrix["row_count"], 2)
        self.assertEqual(matrix["candidate_ids"], ["CAND-A", "CAND-B"])
        with self.assertRaises(ValueError):
            build_candidate_matrix({"CAND-A": [0.1]}, influential_candidates=["CAND-A", "CAND-MISSING"])

    def test_candidate_matrix_rejects_incomplete_asset_axis_coverage(self):
        matrix = build_candidate_matrix(
            {"CAND-EUR": [0.1, 0.2], "CAND-XAU": [0.0, -0.1]},
            asset_universe=["EURUSD", "XAUUSD"],
            candidate_assets={"CAND-EUR": "EURUSD", "CAND-XAU": "XAUUSD"},
        )
        self.assertEqual(matrix["asset_universe"], ["EURUSD", "XAUUSD"])
        with self.assertRaises(ValueError):
            build_candidate_matrix(
                {"CAND-EUR": [0.1, 0.2]},
                asset_universe=["EURUSD", "XAUUSD"],
                candidate_assets={"CAND-EUR": "EURUSD"},
            )


if __name__ == "__main__":
    unittest.main()
