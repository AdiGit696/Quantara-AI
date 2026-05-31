import json
import requests
import re

def interpret_query(query, columns):

    prompt = f"""
You are a data visualization assistant.

Available dataframe columns:
{columns}

User question:
{query}

Return ONLY valid JSON in this format:

{{
 "chart":"scatter",
 "x":"column_name",
 "y":"column_name"
}}

Allowed charts:
scatter
line
bar
"""

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "llama3",
            "prompt": prompt,
            "stream": False
        }
    )

    text = response.json()["response"]

    # extract JSON from response
    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        return None

    try:
        return json.loads(match.group())
    except:
        return None