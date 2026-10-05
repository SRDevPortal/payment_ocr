import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from payment_ocr.document_privacy import guard_request, is_raw_request
from payment_ocr.number_privacy import project_response
from payment_ocr.response_privacy import scrub_response


class TestNumberPrivacy(unittest.TestCase):
    def test_restricted_projection_masks_people_and_drops_raw_payloads(self):
        source = {
            "extracted": {
                "payer": "Anita 9876543210",
                "receiver": "Clinic +91 98765 43211",
            },
            "raw_ocr_text": "Paid by 9876543210",
            "nested": {"raw_json": '{"phone":"9876543210"}'},
            "error": "Could not process proof-9876543210.png",
        }

        with patch("payment_ocr.number_privacy.restricted", return_value=True):
            result = project_response(source)

        self.assertEqual(result["extracted"]["payer"], "Anita ******3210")
        self.assertEqual(result["extracted"]["receiver"], "Clinic ********3211")
        self.assertNotIn("raw_ocr_text", result)
        self.assertNotIn("raw_json", result["nested"])
        self.assertNotIn("9876543210", result["error"])
        self.assertEqual(source["extracted"]["payer"], "Anita 9876543210")

    def test_full_visibility_keeps_original_response(self):
        source = {"extracted": {"payer": "Anita 9876543210"}}
        with patch("payment_ocr.number_privacy.restricted", return_value=False):
            self.assertIs(project_response(source), source)

    def test_raw_document_routes_are_detected(self):
        self.assertTrue(is_raw_request("/api/resource/Payment%20OCR%20Log/LOG-1", {}))
        self.assertTrue(
            is_raw_request(
                "/api/method/frappe.client.get",
                {"doctype": "Payment Gateway Transaction", "name": "TXN-1"},
            )
        )
        self.assertFalse(is_raw_request("/api/resource/Patient%20Encounter/ENC-1", {}))

    def test_raw_document_guard_blocks_restricted_http_access(self):
        request = SimpleNamespace(path="/api/resource/Payment%20OCR%20Log/LOG-1")
        with (
            patch.object(frappe.local, "request", request, create=True),
            patch.object(frappe.local, "form_dict", frappe._dict(), create=True),
            patch("payment_ocr.document_privacy.restricted", return_value=True),
        ):
            with self.assertRaises(frappe.PermissionError):
                guard_request()

    def test_patient_encounter_child_payer_is_masked_in_response(self):
        response = {"docs": [{
            "doctype": "Patient Encounter",
            "enc_multi_payments": [{"mmp_verified_payer": "Anita 9876543210"}],
        }]}

        with (
            patch("payment_ocr.response_privacy.frappe.response", response),
            patch("payment_ocr.response_privacy.restricted", return_value=True),
        ):
            scrub_response()

        self.assertEqual(
            response["docs"][0]["enc_multi_payments"][0]["mmp_verified_payer"],
            "Anita ******3210",
        )


if __name__ == "__main__":
    unittest.main()
