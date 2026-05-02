import unittest
from unittest.mock import patch

import frappe

from payment_ocr.api.ocr import get_ocr_availability, process_patient_encounter
from payment_ocr.services.processor import _merge_extracted, _needs_llm
from payment_ocr.services.settings import get_settings


class TestOcrApiSettings(unittest.TestCase):
	def setUp(self):
		frappe.local.flags = frappe._dict(in_test=True)
		frappe.local.db = frappe._dict(exists=lambda *args, **kwargs: True)

	def test_availability_uses_master_auto_and_manual_switches(self):
		settings = frappe._dict(
			enable_payment_ocr=1,
			enable_auto_ocr=0,
			enable_manual_ocr=1,
		)

		with patch("payment_ocr.api.ocr.get_settings", return_value=settings):
			self.assertEqual(
				get_ocr_availability(),
				{
					"payment_ocr_enabled": True,
					"manual_ocr_enabled": True,
					"auto_ocr_enabled": False,
				},
			)

	def test_master_switch_disables_all_ocr_availability(self):
		settings = frappe._dict(
			enable_payment_ocr=0,
			enable_auto_ocr=1,
			enable_manual_ocr=1,
		)

		with patch("payment_ocr.api.ocr.get_settings", return_value=settings):
			self.assertEqual(
				get_ocr_availability(),
				{
					"payment_ocr_enabled": False,
					"manual_ocr_enabled": False,
					"auto_ocr_enabled": False,
				},
			)

	def test_manual_switch_blocks_manual_processing(self):
		settings = frappe._dict(
			enable_payment_ocr=1,
			enable_auto_ocr=1,
			enable_manual_ocr=0,
		)

		with (
			patch("payment_ocr.api.ocr.get_settings", return_value=settings),
			patch(
				"payment_ocr.api.ocr.frappe.throw",
				side_effect=lambda message: (_ for _ in ()).throw(Exception(message)),
			) as throw,
		):
			with self.assertRaises(Exception) as exc:
				process_patient_encounter("HLC-ENC-2026-00091")

		throw.assert_called_once_with("Manual Payment OCR is disabled in Payment OCR Settings.")
		self.assertIn("Manual Payment OCR is disabled", str(exc.exception))

	def test_site_config_ocr_values_are_used_when_app_level_config_is_disabled(self):
		doc = frappe._dict(
			enable_payment_ocr=1,
			enable_auto_ocr=1,
			enable_manual_ocr=1,
			enable_gateway_verification=1,
			enable_partial_gateway_match=0,
			use_app_level_ocr_config=0,
			use_app_level_gateway_config=0,
			textract_access_key_id="APP_ACCESS",
			textract_secret_access_key="***",
			textract_region="app-region",
			openai_api_key="***",
			openai_model="app-model",
			gateway_webhook_secret="***",
			amount_mismatch_behavior="Warn Only",
			get_password=lambda fieldname: {
				"textract_secret_access_key": "APP_SECRET",
				"openai_api_key": "APP_OPENAI",
				"gateway_webhook_secret": None,
			}.get(fieldname),
		)
		conf = frappe._dict(
			aws_textract_access_key_id="SITE_ACCESS",
			aws_textract_secret_access_key="SITE_SECRET",
			aws_textract_region="site-region",
			payment_ocr_openai_api_key="SITE_OPENAI",
			payment_ocr_openai_model="site-model",
			payment_ocr_gateway_webhook_secret="SITE_GATEWAY_SECRET",
		)
		frappe.local.conf = conf

		with (
			patch("payment_ocr.services.settings.frappe.get_single", return_value=doc),
		):
			settings = get_settings()

		self.assertEqual(settings.textract_access_key_id, "SITE_ACCESS")
		self.assertEqual(settings.textract_secret_access_key, "SITE_SECRET")
		self.assertEqual(settings.textract_region, "site-region")
		self.assertEqual(settings.openai_api_key, "SITE_OPENAI")
		self.assertEqual(settings.openai_model, "site-model")
		self.assertEqual(settings.gateway_webhook_secret, "SITE_GATEWAY_SECRET")

	def test_app_ocr_values_are_used_exclusively_when_app_level_config_is_enabled(self):
		doc = frappe._dict(
			enable_payment_ocr=1,
			enable_auto_ocr=1,
			enable_manual_ocr=1,
			enable_gateway_verification=1,
			enable_partial_gateway_match=0,
			use_app_level_ocr_config=1,
			use_app_level_gateway_config=1,
			textract_access_key_id="APP_ACCESS",
			textract_secret_access_key="***",
			textract_region="app-region",
			openai_api_key="***",
			openai_model="app-model",
			gateway_webhook_secret="***",
			amount_mismatch_behavior="Warn Only",
			get_password=lambda fieldname: {
				"textract_secret_access_key": "APP_SECRET",
				"openai_api_key": "APP_OPENAI",
				"gateway_webhook_secret": "APP_GATEWAY_SECRET",
			}.get(fieldname),
		)
		conf = frappe._dict(
			aws_textract_access_key_id="SITE_ACCESS",
			aws_textract_secret_access_key="SITE_SECRET",
			aws_textract_region="site-region",
			payment_ocr_openai_api_key="SITE_OPENAI",
			payment_ocr_openai_model="site-model",
			payment_ocr_gateway_webhook_secret="SITE_GATEWAY_SECRET",
		)
		frappe.local.conf = conf

		with (
			patch("payment_ocr.services.settings.frappe.get_single", return_value=doc),
		):
			settings = get_settings()

		self.assertEqual(settings.textract_access_key_id, "APP_ACCESS")
		self.assertEqual(settings.textract_secret_access_key, "APP_SECRET")
		self.assertEqual(settings.textract_region, "app-region")
		self.assertEqual(settings.openai_api_key, "APP_OPENAI")
		self.assertEqual(settings.openai_model, "app-model")
		self.assertEqual(settings.gateway_webhook_secret, "APP_GATEWAY_SECRET")

	def test_gateway_secret_uses_site_config_when_app_level_gateway_config_is_disabled(self):
		doc = frappe._dict(
			enable_payment_ocr=1,
			enable_auto_ocr=1,
			enable_manual_ocr=1,
			enable_gateway_verification=1,
			enable_partial_gateway_match=0,
			use_app_level_ocr_config=0,
			use_app_level_gateway_config=0,
			gateway_webhook_secret="***",
			amount_mismatch_behavior="Warn Only",
			get_password=lambda fieldname: {
				"gateway_webhook_secret": "APP_GATEWAY_SECRET",
			}.get(fieldname),
		)
		frappe.local.conf = frappe._dict(payment_ocr_gateway_webhook_secret="SITE_GATEWAY_SECRET")

		with patch("payment_ocr.services.settings.frappe.get_single", return_value=doc):
			settings = get_settings()

		self.assertEqual(settings.gateway_webhook_secret, "SITE_GATEWAY_SECRET")

	def test_gateway_secret_uses_app_setting_exclusively_when_enabled(self):
		doc = frappe._dict(
			enable_payment_ocr=1,
			enable_auto_ocr=1,
			enable_manual_ocr=1,
			enable_gateway_verification=1,
			enable_partial_gateway_match=0,
			use_app_level_ocr_config=0,
			use_app_level_gateway_config=1,
			gateway_webhook_secret="***",
			amount_mismatch_behavior="Warn Only",
			get_password=lambda fieldname: {
				"gateway_webhook_secret": "APP_GATEWAY_SECRET",
			}.get(fieldname),
		)
		frappe.local.conf = frappe._dict(payment_ocr_gateway_webhook_secret="SITE_GATEWAY_SECRET")

		with patch("payment_ocr.services.settings.frappe.get_single", return_value=doc):
			settings = get_settings()

		self.assertEqual(settings.gateway_webhook_secret, "APP_GATEWAY_SECRET")

	def test_llm_merge_does_not_invent_payment_parties(self):
		extracted = _merge_extracted(
			{
				"amount": 6000,
				"date": "2026-05-02",
				"receiver": "SR INSTITUTE OF ADVANCED AYURVEDIC SCIENCES PVT LTD",
			},
			{
				"payer": "SR INSTITUTE SL OF ADVANCED AYURVEDIC SCIENCES PVT LTD",
				"receiver": "SHREE BALAJI FASHION & ACCESSORIES",
				"transaction_id": "623261681234",
			},
		)

		self.assertIsNone(extracted["payer"])
		self.assertEqual(extracted["receiver"], "SR INSTITUTE OF ADVANCED AYURVEDIC SCIENCES PVT LTD")
		self.assertEqual(extracted["transaction_id"], "623261681234")

	def test_llm_is_not_needed_only_because_reference_is_missing(self):
		self.assertFalse(
			_needs_llm(
				{"amount": 6000, "date": "2026-05-02", "transaction_id": None},
				{"enable_llm_fallback": True},
			)
		)


if __name__ == "__main__":
	unittest.main()
