# ai_agent.py

import os
from openai import OpenAI

class AIClassifier:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("Missing OPENAI_API_KEY environment variable")
        self.client = OpenAI(api_key=api_key)

    def classify_email(self, subject: str, body: str) -> str:
        prompt = f"""
You are an intelligent email classifier.

Your task is to classify the following email into one of exactly these categories:
[invoice, promotion, personal, work, spam, other]

Return ONLY one of the above category names, with no explanation, no formatting, and no punctuation.

If the classification is unclear or insufficient, return: other

---

Subject: {subject.strip()}

Body (first 1000 characters):
{body[:1000].strip()}
        """

        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful and concise email classifier."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
        )

        return response.choices[0].message.content.strip().lower()
