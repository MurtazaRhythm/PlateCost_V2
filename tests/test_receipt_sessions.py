import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from storage3.exceptions import StorageApiError

from receipts.extract import PROMPT
from receipts.present import dashboard_payload, in_local_day, local_day_bounds, receipt_payload
from receipts.sessions import image_extension, ordered_image_rows
from receipts.store import missing_bucket


class SessionOrderTests(unittest.TestCase):
    def test_images_sort_by_sequence_not_insertion_order(self):
        rows = [
            {"sequence_number": 3, "storage_path": "c", "created_at": "2026-10-02T12:00:03Z"},
            {"sequence_number": 1, "storage_path": "a", "created_at": "2026-10-02T12:00:01Z"},
            {"sequence_number": 2, "storage_path": "b", "created_at": "2026-10-02T12:00:02Z"},
        ]
        ordered = ordered_image_rows(rows)
        self.assertEqual([row["storage_path"] for row in ordered], ["a", "b", "c"])

    def test_upload_names_keep_capture_order(self):
        blobs = [b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"RIFF1234WEBP"]
        self.assertEqual([image_extension(blob)[0] for blob in blobs], ["jpg", "png", "webp"])


class BucketErrorTests(unittest.TestCase):
    def test_missing_bucket_matches_the_storage_error(self):
        self.assertTrue(missing_bucket(StorageApiError("Bucket not found", "Bucket not found", 400)))
        self.assertFalse(missing_bucket(StorageApiError("The resource already exists", "Duplicate", 409)))


class PromptTests(unittest.TestCase):
    def test_prompt_treats_every_photo_as_one_receipt(self):
        self.assertIn("Treat all images as one receipt", PROMPT)
        self.assertIn("Do not duplicate items that appear in overlapping sections", PROMPT)
        self.assertIn("Return one structured receipt object", PROMPT)


class PresentTests(unittest.TestCase):
    def test_receipt_payload_uses_app_field_names(self):
        payload = receipt_payload(
            {
                "id": "r1",
                "receipt_session_id": "s1",
                "vendor_name": "Restaurant Depot",
                "purchase_date": "2026-10-02",
                "subtotal": "182.45",
                "tax_total": "23.72",
                "tip": "0",
                "total": "206.17",
                "payment_method": "Visa",
                "category": "Food Inventory",
                "currency": "USD",
                "needs_review": False,
                "created_at": "2026-10-02T14:00:00Z",
            },
            [
                {
                    "name": None,
                    "description": "Chicken",
                    "quantity": "1",
                    "unit_price": "82.00",
                    "total_price": "82.00",
                    "category": "Food Inventory",
                    "confidence": "0.900",
                }
            ],
            [{"sequence_number": 1, "signed_url": "https://example.test/1.jpg", "image_url": "path"}],
        )
        self.assertEqual(payload["vendor"], "Restaurant Depot")
        self.assertEqual(payload["date"], "2026-10-02")
        self.assertEqual(payload["tax"], 23.72)
        self.assertEqual(payload["items"][0]["name"], "Chicken")
        self.assertEqual(payload["images"][0]["image_url"], "https://example.test/1.jpg")
        self.assertEqual(payload["images"][0]["sequence_number"], 1)

    def test_today_total_uses_the_restaurant_timezone(self):
        start, end = local_day_bounds("America/New_York", datetime(2026, 10, 2, 15, 0, tzinfo=ZoneInfo("America/New_York")))
        morning = "2026-10-02T14:30:00+00:00"
        previous = "2026-10-02T03:30:00+00:00"
        self.assertTrue(in_local_day(morning, start, end))
        self.assertFalse(in_local_day(previous, start, end))

        payload = dashboard_payload(
            "Test Kitchen",
            [
                {"id": "a", "vendor_name": "Sysco", "total": "10.00", "currency": "USD", "purchase_date": "2026-10-02", "purchase_time": "10:15:00", "created_at": morning},
                {"id": "b", "vendor_name": "Costco", "total": "5.50", "currency": "USD", "purchase_date": "2026-10-01", "purchase_time": "23:00:00", "created_at": previous},
            ],
            "America/New_York",
            now=datetime(2026, 10, 2, 15, 0, tzinfo=ZoneInfo("America/New_York")),
        )
        self.assertEqual(payload["today"]["count"], 1)
        self.assertEqual(payload["today"]["total"], 10.0)
        self.assertEqual(payload["recent"][0]["vendor"], "Sysco")
        self.assertEqual(payload["recent"][0]["time"], "10:15")


if __name__ == "__main__":
    unittest.main()
