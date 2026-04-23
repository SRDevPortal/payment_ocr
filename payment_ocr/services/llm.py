import json
import re


def cleanup_with_llm(text, settings):
	if not settings.get("enable_llm_fallback") or not settings.get("openai_api_key"):
		return {}

	import requests

	prompt = f"""
Extract payment details from this OCR text.

Return only JSON in this format:
{{
  "amount": number,
  "date": "YYYY-MM-DD",
  "transaction_id": "",
  "status": "",
  "payer": "",
  "receiver": ""
}}

OCR TEXT:
{text}
"""
	response = requests.post(
		"https://api.openai.com/v1/responses",
		headers={
			"Authorization": f"Bearer {settings.openai_api_key}",
			"Content-Type": "application/json",
		},
		json={
			"model": settings.openai_model or "gpt-4.1-mini",
			"input": prompt,
		},
		timeout=45,
	)
	response.raise_for_status()
	data = response.json()

	for item in data.get("output", []):
		for content in item.get("content", []):
			text_value = content.get("text")
			if not text_value:
				continue
			match = re.search(r"\{.*\}", text_value.strip(), flags=re.DOTALL)
			if match:
				return json.loads(match.group(0))

	return {}
