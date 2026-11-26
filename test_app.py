import io
import json
import tempfile
import unittest
from pathlib import Path

from app import create_app


CSV = b"age,spend,segment\n22,40,blue\n24,45,blue\n25,42,blue\n51,180,gold\n53,175,gold\n54,190,gold\n31,72,blue\n33,75,blue\n34,78,blue\n49,160,gold\n52,184,gold\n56,195,gold\n"


class PatternIQTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-key",
                "DATABASE": str(Path(self.temp_dir.name) / "test.sqlite3"),
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def upload(self, name="sample.csv", contents=CSV):
        return self.client.post(
            "/upload",
            data={"dataset": (io.BytesIO(contents), name)},
            content_type="multipart/form-data",
            follow_redirects=True,
        )

    def test_upload_discovers_patterns_and_keeps_raw_csv_out_of_history(self):
        response = self.upload()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Pattern discovery", response.data)
        self.assertIn(b"Principal components", response.data)
        self.assertIn(b"SUGGESTED NEXT STEPS", response.data)
        self.assertIn(b"sample.csv", response.data)
        history = self.client.get("/history")
        self.assertIn(b"sample.csv", history.data)
        with self.app.app_context():
            from app import connect

            with connect(self.app.config["DATABASE"]) as db:
                stored = db.execute("SELECT result_json FROM scans").fetchone()[0]
        self.assertNotIn("spend,segment", stored)
        self.assertIsInstance(json.loads(stored)["clusters"]["count"], int)

    def test_upload_rejects_non_csv_and_duplicate_columns(self):
        response = self.upload("data.txt")
        self.assertIn(b"Only .csv files are supported", response.data)
        response = self.upload("duplicate.csv", b"a,a\n1,2\n3,4\n")
        self.assertIn(b"Column names must be unique", response.data)
        self.assertEqual(self.client.get("/history").status_code, 200)
        self.assertNotIn(b"duplicate.csv", self.client.get("/history").data)

    def test_report_and_delete_routes_work(self):
        self.upload()
        with self.app.app_context():
            from app import connect

            with connect(self.app.config["DATABASE"]) as db:
                scan_id = db.execute("SELECT id FROM scans").fetchone()[0]
        report = self.client.get(f"/scans/{scan_id}/report.pdf")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.mimetype, "application/pdf")
        self.assertTrue(report.data.startswith(b"%PDF"))
        self.client.post(f"/scans/{scan_id}/delete")
        self.assertEqual(self.client.get(f"/scans/{scan_id}").status_code, 404)

    def test_feature_pages_and_missing_scan_routes(self):
        for path in ("/", "/dashboard", "/patterns", "/anomalies", "/reports", "/history", "/about"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(self.client.get("/scans/not-an-id").status_code, 404)

    def test_constant_features_do_not_claim_clusters_or_anomalies(self):
        contents = b"constant,category\n1,same\n1,same\n1,same\n1,same\n1,same\n1,same\n1,same\n1,same\n1,same\n1,same\n"
        response = self.upload("constant.csv", contents)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"do not vary enough", response.data)
        self.assertIn(b"Variance explained: 0.0% + 0.0%", response.data)


if __name__ == "__main__":
    unittest.main()
