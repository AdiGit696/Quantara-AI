import requests

def generate_insights(summary):

    prompt = f"""
You are a data analyst.

Based on the dataset summary below, give ONLY 3 short insights.

Keep it concise.

Dataset:
{summary}
"""

    try:
        response = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": "llama3",
                "prompt": prompt,
                "stream": False
            },
            timeout=60
        )

        result = response.json()

        return result.get("response", "No response from AI")

    except Exception as e:
        return f"Error: {e}"