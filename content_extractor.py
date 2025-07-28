import os
import fitz  # PyMuPDF
import json
import re
import pandas as pd
from google.generativeai import GenerativeModel, configure

# === CONFIG ===
GOOGLE_API_KEY = "AIzaSyAlBLVrh3Jqsf2bE2U467GBprNzSoonjG4"
INPUT_DIR = "INPUT"
OUTPUT_JSON_DIR = "OUTPUT/json"
OUTPUT_EXCEL_DIR = "OUTPUT/excel"

# === SETUP ===
configure(api_key=GOOGLE_API_KEY)
model = GenerativeModel("gemini-2.5-pro")

# === ENSURE OUTPUT FOLDERS EXIST ===
os.makedirs(OUTPUT_JSON_DIR, exist_ok=True)
os.makedirs(OUTPUT_EXCEL_DIR, exist_ok=True)

# === PROMPT ===
def get_extraction_prompt():
    return """
You are an intelligent assistant trained to extract structured educational content from Indian NCERT Class 8 Science textbooks given as Input.

Your task is to extract and organize content from a given chapter into the **exact JSON format** shown below.

📦 Output Format (sample):
{
  "chapter_number": "4",
  "chapter_name": "Combustion and Flame",
  "topics": [
    {
      "topic_number": "4.0",
      "topic_title": "Introduction",
      "content": [
        {
          "page_no": "40",
          "sequence_no": 1,
          "type": "Paragraph",
          "internal_name": "4.0.1",
          "actual_content": "<Extracted content>"
        }
      ]
    }
  ]
}

🔍 Extraction Rules:
1. Extract structured content in this exact format:
   - `chapter_number`: The number from the textbook (e.g., 4)
   - `chapter_name`: As given in the textbook
   - `topic_number`: Format as `<chapter_number>.<index>` (e.g., 4.1, 4.2...)
   - `topic_title`: Heading of the topic
   - `content`: List of content blocks under the topic
     - `page_no`: The page number in the original PDF
     - `sequence_no`: Order of the content within the topic (1, 2, 3, ...)
     - `type`: Type of content (e.g., Paragraph, Activity, Diagram, Image, Example, Exercise, Boxed Fact, Table)
     - `internal_name`: Format as `<topic_number>.<index>` (e.g., 4.1.1)
     - `actual_content`: The raw, extracted content (verbatim)

2. Maintain the order of content as it appears in the book.
3. Do **not** summarize, explain, or interpret anything.
4. If a section has multiple types of content (e.g., paragraph and activity), extract each as a separate block in the `content` list with the appropriate `type`.
5. Use the topic headers to identify topic titles.
6. Skip unrelated metadata or headers (like NCERT copyright).

---
Begin extraction using this format now.
"""

# === UTILITIES ===

def extract_text_from_pdf(pdf_path):
    with fitz.open(pdf_path) as doc:
        return "".join([page.get_text() for page in doc])

def extract_json_from_text(response_text):
    matches = re.findall(r"```(?:json)?\s*({.*?})\s*```", response_text, re.DOTALL)
    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass
    brace_match = re.search(r"\{.*\}", response_text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass
    return None

def get_structured_content(pdf_text):
    prompt = get_extraction_prompt()
    chunks = [pdf_text[i:i+10000] for i in range(0, len(pdf_text), 10000)]

    for chunk in chunks:
        print("   🔹 Sending chunk to Gemini...")
        response = model.generate_content(f"{prompt}\n\nText:\n{chunk}")
        result = extract_json_from_text(response.text)
        if result:
            return result
    return None

def parse_json_to_rows(data):
    rows = []
    chapter_number = data.get("chapter_number", "")
    chapter_name = data.get("chapter_name", "")
    for topic in data.get("topics", []):
        topic_number = topic.get("topic_number", "")
        topic_title = topic.get("topic_title", "")
        for content in topic.get("content", []):
            rows.append({
                "chapter_number": chapter_number,
                "chapter_name": chapter_name,
                "topic_number": topic_number,
                "topic_title": topic_title,
                "sequence_no": content.get("sequence_no", ""),
                "page_no": content.get("page_no", ""),
                "type": content.get("type", ""),
                "internal_name": content.get("internal_name", ""),
                "actual_content": content.get("actual_content", "")
            })
    return rows


# === MAIN SCRIPT ===

def process_all_pdfs():
    pdf_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(".pdf")]

    if not pdf_files:
        print("📂 No PDFs found in INPUT folder.")
        return

    for pdf_file in pdf_files:
        print(f"📘 Processing: {pdf_file}")
        input_path = os.path.join(INPUT_DIR, pdf_file)
        base_name = os.path.splitext(pdf_file)[0]
        json_out = os.path.join(OUTPUT_JSON_DIR, f"{base_name}.json")
        excel_out = os.path.join(OUTPUT_EXCEL_DIR, f"{base_name}.xlsx")

        try:
            pdf_text = extract_text_from_pdf(input_path)
            structured_data = get_structured_content(pdf_text)

            if not structured_data:
                print(f"❌ Failed to extract content from {pdf_file}")
                continue

            # Save JSON
            with open(json_out, "w", encoding="utf-8") as jf:
                json.dump(structured_data, jf, indent=2)

            # Save Excel
            rows = parse_json_to_rows(structured_data)
            df = pd.DataFrame(rows)
            df.to_excel(excel_out, index=False)

            print(f"✅ Success: {pdf_file} → JSON + Excel")

        except Exception as e:
            print(f"❌ Error processing {pdf_file}: {e}")


if __name__ == "__main__":
    process_all_pdfs()
