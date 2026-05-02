import unittest

from payment_ocr.services.parser import clean_result, parse_payment_text


class TestPaymentParser(unittest.TestCase):
	def test_payment_success_without_reference_keeps_reference_blank(self):
		result = parse_payment_text(
			[
				"Payment Successful",
				"02 May 2026 at 01:55 PM",
				"SR INSTITUTE",
				"OF ADVANCED",
				"AYURVEDIC SCIENCES",
				"PVT LTD",
				"srinstofadvayurvedic",
				"62326168@hdfcbank",
				"\u20b96,000",
				"Split Expense",
				"8 are 324121 42 41 Ref",
				"Products - will will not be replaced under any circumstances",
				"Done",
			]
		)

		self.assertEqual(result["amount"], 6000.0)
		self.assertEqual(result["date"], "2026-05-02")
		self.assertEqual(result["time"], "13:55:00")
		self.assertEqual(result["transaction_datetime"], "2026-05-02 13:55:00")
		self.assertEqual(result["status"], "SUCCESS")
		self.assertIsNone(result["transaction_id"])

	def test_llm_cleanup_rejects_plain_words_as_transaction_id(self):
		result = clean_result(
			{
				"amount": 6000,
				"date": "02 May 2026",
				"time": "01:55 PM",
				"status": "SUCCESS",
				"transaction_id": "Products",
			}
		)

		self.assertIsNone(result["transaction_id"])

	def test_numeric_transaction_reference_is_still_allowed(self):
		result = clean_result({"transaction_id": "623261681234"})

		self.assertEqual(result["transaction_id"], "623261681234")


if __name__ == "__main__":
	unittest.main()
