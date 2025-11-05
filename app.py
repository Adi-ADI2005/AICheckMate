from flask import Flask, request, render_template, send_file
import PyPDF2
import docx
import requests
from serpapi import GoogleSearch 
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
import os

SAPLING_API_KEY = "UXFL96YDVU57R31SIF92TJ9KS8I53LI7"
SERP_API_KEY = "a5f469ce3f45c5275b39d6036c34949c881b826b89b16da9447292d79137de9d"
app = Flask(__name__)

# ✅ GLOBAL STORAGE (used for PDF download)
LAST_REPORT = {}

# ✅ Extract text from PDF
def extract_text_from_pdf(file):
    reader = PyPDF2.PdfReader(file)
    text = ""
    for page in reader.pages:
        t = page.extract_text()
        if t:
            text += t + "\n"
    return text

# ✅ Extract text from DOCX
def extract_text_from_docx(file):
    doc = docx.Document(file)
    return "\n".join([p.text for p in doc.paragraphs])

# ✅ Extraction text from dispatcher
def extract_text(file, filename):
    if filename.endswith(".pdf"):
        return extract_text_from_pdf(file)
    if filename.endswith(".docx"):
        return extract_text_from_docx(file)
    if filename.endswith(".txt"):
        return file.read().decode("utf-8")
    return None

# ✅ AI Detection (Sapling)
def detect_ai(text):
    response = requests.post(
        "https://api.sapling.ai/api/v1/aidetect",
        json={"key": SAPLING_API_KEY, "text": text}
    ).json()

    score = response.get("score", 0)
    verdict = (
        "AI-generated" if score > 0.85 else
        "Possibly AI-generated" if score > 0.50 else
        "Human-written"
    )

    return {"score": score, "verdict": verdict}

# ✅ Guess model
def guess_model(text):
    t = text.lower()
    if len(text) < 100:
        return "Text too short to identify."

    if "as an ai" in t: return "Likely GPT-3.5"
    if "hallucination" in t: return "Likely GPT-4"
    if "anthropic" in t: return "Likely Claude"
    if "gemini" in t: return "Likely Google Gemini"

    return "Unknown / Possibly Human"

# ✅ Summary plagiarism
def plagiarism_check(text):
    first_12 = " ".join(text.split()[:12])
    result = GoogleSearch({"engine": "google", "q": first_12, "api_key": SERP_API_KEY}).get_dict()

    sources = []
    if "organic_results" in result:
        for r in result["organic_results"][:5]:
            sources.append({"title": r.get("title"), "link": r.get("link")})

    return sources

# ✅ Line-by-line plagiarism + % 
def line_wise_plagiarism(text):
    lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 8]
    copied = []

    for line in lines:
        result = GoogleSearch({
            "engine": "google",
            "q": f"\"{line}\"",
            "api_key": SERP_API_KEY
        }).get_dict()

        if "organic_results" in result and len(result["organic_results"]) > 0:
            src = result["organic_results"][0]
            copied.append({
                "line": line,
                "title": src.get("title"),
                "link": src.get("link")
            })

    total = len(lines)
    percent = round((len(copied) / total) * 100, 2) if total else 0

    return copied, percent

# ✅ HOME
@app.route("/")
def home():
    return render_template("index.html")

# ✅ ANALYZE
@app.route("/analyze", methods=["POST"])
def analyze():
    text_input = request.form.get("text_input")

    if "file" in request.files and request.files["file"].filename != "":
        file = request.files["file"]
        extracted_text = extract_text(file, file.filename)
    else:
        extracted_text = text_input

    if not extracted_text:
        return "No text found!", 400

    ai_result = detect_ai(extracted_text)
    model_guess = guess_model(extracted_text)
    summary_sources = plagiarism_check(extracted_text)
    detailed_sources, plagiarism_percent = line_wise_plagiarism(extracted_text)

    # ✅ Save to global for PDF generation
    LAST_REPORT["ai"] = ai_result
    LAST_REPORT["model"] = model_guess
    LAST_REPORT["summary"] = summary_sources
    LAST_REPORT["detailed"] = detailed_sources
    LAST_REPORT["percent"] = plagiarism_percent

    return render_template(
        "result.html",
        ai_result=ai_result,
        model_guess=model_guess,
        sources=summary_sources,
        detailed=detailed_sources,
        plagiarism_percent=plagiarism_percent
    )

# ✅ DOWNLOAD PDF
@app.route("/download")
def download():
    filename = "report.pdf"
    doc = SimpleDocTemplate(filename, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    # ✅ Add sections
    story.append(Paragraph("<b>AI Detection Result</b>", styles['Heading2']))
    story.append(Paragraph(f"Verdict: {LAST_REPORT['ai']['verdict']}", styles['Normal']))
    story.append(Paragraph(f"Score: {LAST_REPORT['ai']['score']}", styles['Normal']))
    story.append(Spacer(1, 12))

    story.append(Paragraph("<b>Model Guess</b>", styles['Heading2']))
    story.append(Paragraph(LAST_REPORT["model"], styles['Normal']))
    story.append(Spacer(1, 12))

    story.append(Paragraph("<b>Plagiarism Summary</b>", styles['Heading2']))
    story.append(Paragraph(f"Plagiarism Percentage: {LAST_REPORT['percent']}%", styles['Normal']))
    story.append(Spacer(1, 12))

    for s in LAST_REPORT["summary"]:
        story.append(Paragraph(f"- {s['title']} ({s['link']})", styles['Normal']))

    story.append(Spacer(1, 20))

    story.append(Paragraph("<b>Line-by-Line Plagiarism</b>", styles['Heading2']))
    for d in LAST_REPORT["detailed"]:
        story.append(Paragraph(f"<b>Line:</b> {d['line']}", styles['Normal']))
        story.append(Paragraph(f"Source: {d['title']}", styles['Normal']))
        story.append(Paragraph(f"Link: {d['link']}", styles['Normal']))
        story.append(Spacer(1, 12))

    doc.build(story)

    return send_file(filename, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
