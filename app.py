"""
AI Resume Analyzer - local version (no AWS, no API key needed)

Run:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000

Scoring is rule-based (skills, keywords, resume quality checks).
OPTIONAL: set the GROQ_API_KEY environment variable to also get written
AI feedback. Without it, everything else still works.
"""

import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from io import BytesIO

from flask import Flask, jsonify, request, send_from_directory
from pypdf import PdfReader

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024  # 4 MB uploads

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analyses.db")
MAX_CHARS = 15000

# ---------------------------------------------------------------- skills ----
# canonical name -> list of ways it is written in resumes / job descriptions
SKILLS = {
    "Python": ["python"],
    "Java": ["java"],
    "JavaScript": ["javascript", "js"],
    "TypeScript": ["typescript"],
    "C Programming": ["c programming", "c language"],
    "C++": ["c++"],
    "C#": ["c#"],
    "PHP": ["php"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3"],
    "Bootstrap": ["bootstrap"],
    "Tailwind CSS": ["tailwind", "tailwind css"],
    "React": ["react", "react.js", "reactjs"],
    "Angular": ["angular"],
    "Vue": ["vue", "vue.js"],
    "Node.js": ["node.js", "nodejs", "node js"],
    "Flask": ["flask"],
    "Django": ["django"],
    "FastAPI": ["fastapi"],
    "Streamlit": ["streamlit"],
    "REST APIs": ["rest api", "rest apis", "restful", "api", "apis"],
    "SQL": ["sql"],
    "MySQL": ["mysql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MongoDB": ["mongodb"],
    "SQLite": ["sqlite"],
    "Firebase": ["firebase"],
    "Git": ["git"],
    "GitHub": ["github"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes"],
    "Linux": ["linux"],
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure"],
    "Google Cloud": ["gcp", "google cloud"],
    "CI/CD": ["ci/cd", "cicd"],
    "Machine Learning": ["machine learning", "ml"],
    "Deep Learning": ["deep learning"],
    "NLP": ["nlp", "natural language processing"],
    "Computer Vision": ["computer vision", "opencv"],
    "Generative AI": ["generative ai", "genai", "gen ai"],
    "LLMs": ["llm", "llms", "large language model", "large language models"],
    "Prompt Engineering": ["prompt engineering"],
    "LangChain": ["langchain"],
    "RAG": ["rag", "retrieval augmented generation"],
    "TensorFlow": ["tensorflow"],
    "PyTorch": ["pytorch"],
    "Scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Matplotlib": ["matplotlib"],
    "Seaborn": ["seaborn"],
    "Data Analysis": ["data analysis", "data analytics"],
    "Power BI": ["power bi", "powerbi"],
    "Tableau": ["tableau"],
    "Excel": ["excel"],
    "n8n": ["n8n"],
    "Data Structures": ["data structures", "dsa"],
    "Algorithms": ["algorithms"],
    "OOP": ["oop", "object oriented", "object-oriented"],
    "Testing": ["testing", "unit testing", "selenium"],
    "Agile": ["agile", "scrum"],
    "Jira": ["jira"],
    "IoT": ["iot", "internet of things"],
    "Arduino": ["arduino"],
    "Raspberry Pi": ["raspberry pi"],
    "Embedded Systems": ["embedded", "embedded systems"],
    "MATLAB": ["matlab"],
    "Verilog": ["verilog", "vhdl"],
    "Communication": ["communication skills", "communicator", "written communication", "verbal communication"],
    "Teamwork": ["teamwork", "team player", "collaboration"],
    "Problem Solving": ["problem solving", "problem-solving"],
}

SKILL_PATTERNS = {
    name: re.compile(
        r"(?<![\w+#.])(?:" + "|".join(re.escape(a) for a in aliases) + r")(?![\w+#])"
    )
    for name, aliases in SKILLS.items()
}
ALL_ALIASES = {a for aliases in SKILLS.values() for a in aliases}
ALIAS_WORDS = {w for a in ALL_ALIASES for w in re.split(r"[\s/]+", a)}

STOPWORDS = set(
    """the and for with that this from will have has are you your our their they them who
    what when where which while about into over under more most such than then also can
    able must should would could may might not but all any each other some very per via
    etc job role work working works team teams ability skills skill knowledge strong good
    great excellent years year experience experienced candidate candidates required
    requirements requirement preferred responsibilities responsibility including include
    looking join opportunity company position fresher freshers trainee engineer developer
    developers development using use used understanding understand basic plus well new
    help support ensure across within based related relevant like need needs make
    building build create creating hiring basics etc""".split()
)

ACTION_VERBS = [
    "built", "developed", "designed", "implemented", "created", "led", "optimized",
    "deployed", "analyzed", "automated", "integrated", "improved", "managed",
    "launched", "trained", "tested", "engineered",
]


# ----------------------------------------------------------------- helpers ----
def extract_text(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception:
        raise ValueError("Could not read this PDF. Try exporting it again.")
    if not text:
        raise ValueError("No text found in this PDF. It may be a scanned image.")
    return text[:MAX_CHARS]


def skills_in(text: str) -> list[str]:
    lowered = text.lower()
    return [name for name, pattern in SKILL_PATTERNS.items() if pattern.search(lowered)]


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z+#.\-]{2,}", text.lower())
    return [w.strip(".-") for w in words]


def top_keywords(text: str, n: int = 25) -> list[str]:
    counts = Counter(w for w in tokens(text) if len(w) > 2 and w not in STOPWORDS)
    return [w for w, _ in counts.most_common(n)]


def resume_checks(text: str) -> list[dict]:
    lowered = text.lower()
    words = len(text.split())
    verbs = sum(1 for v in ACTION_VERBS if re.search(rf"\b{v}\b", lowered))

    return [
        {
            "label": "Email address present",
            "passed": bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)),
            "tip": "Add a professional email address at the top of your resume.",
        },
        {
            "label": "Phone number present",
            "passed": bool(re.search(r"\+?\d[\d\s\-]{8,}\d", text)),
            "tip": "Add your phone number so recruiters can reach you.",
        },
        {
            "label": "LinkedIn or GitHub link",
            "passed": "linkedin" in lowered or "github" in lowered,
            "tip": "Add your GitHub and LinkedIn links. Recruiters want to see your projects.",
        },
        {
            "label": "Skills section",
            "passed": "skills" in lowered,
            "tip": "Add a clear Skills section listing your technical skills.",
        },
        {
            "label": "Projects section",
            "passed": "project" in lowered,
            "tip": "Add a Projects section with 2-4 projects and what each one does.",
        },
        {
            "label": "Education section",
            "passed": "education" in lowered or "b.tech" in lowered or "degree" in lowered,
            "tip": "Add an Education section with your degree, college, and year.",
        },
        {
            "label": "Experience, internship or certifications",
            "passed": any(k in lowered for k in ["experience", "internship", "certification", "certificate"]),
            "tip": "Add internships, certifications, or training to show practical learning.",
        },
        {
            "label": "Strong action verbs (built, developed, ...)",
            "passed": verbs >= 3,
            "tip": "Start bullet points with action verbs like built, developed, designed, deployed.",
        },
        {
            "label": "Numbers or results mentioned",
            "passed": bool(re.search(r"\d+\s?%|\b\d{2,}\+?\s?(users|records|requests|projects|students)", lowered)),
            "tip": "Add numbers to your achievements, for example 'improved accuracy to 92%'.",
        },
        {
            "label": "Reasonable length (200-1000 words)",
            "passed": 200 <= words <= 1000,
            "tip": "Keep the resume between one and two pages (about 200-1000 words).",
        },
    ]


def analyze_text(resume_text: str, jd_text: str) -> dict:
    required = skills_in(jd_text)
    have = set(skills_in(resume_text))
    matched = [s for s in required if s in have]
    missing = [s for s in required if s not in have]

    jd_keywords = top_keywords(jd_text)
    resume_words = set(tokens(resume_text))
    kw_missing = [k for k in jd_keywords if k not in resume_words]
    kw_score = 100 * (len(jd_keywords) - len(kw_missing)) / len(jd_keywords) if jd_keywords else 0
    shown_kw_missing = [k for k in kw_missing if k not in ALIAS_WORDS][:10]

    skill_score = 100 * len(matched) / len(required) if required else kw_score

    checks = resume_checks(resume_text)
    quality_score = 100 * sum(c["passed"] for c in checks) / len(checks)

    score = round(0.55 * skill_score + 0.25 * kw_score + 0.20 * quality_score)
    score = max(0, min(100, score))

    if score >= 75:
        summary = "Strong match. Your resume covers most of what this job asks for."
    elif score >= 50:
        summary = "Decent match, but several required skills or keywords are missing from your resume."
    else:
        summary = "Low match for this job. Focus on the missing skills and the resume checklist below."
    if required:
        summary += f" You match {len(matched)} of {len(required)} skills found in the job description."
    else:
        summary += " No standard skills were detected in the job description, so keywords were used instead."

    suggestions = []
    if missing:
        top = ", ".join(missing[:6])
        suggestions.append(
            f"The job description mentions {top}, but your resume doesn't. "
            "Add them only if you have really used them."
        )
        suggestions.append(
            f"If you haven't used {missing[0]} yet, build a small project with it and add it to your resume."
        )
    suggestions += [c["tip"] for c in checks if not c["passed"]]
    if not suggestions:
        suggestions.append("Your resume looks solid. Tailor your project descriptions to this job's wording.")

    return {
        "match_score": score,
        "summary": summary,
        "matched_skills": matched,
        "missing_skills": missing,
        "keywords_missing": shown_kw_missing,
        "checks": [{"label": c["label"], "passed": c["passed"]} for c in checks],
        "suggestions": suggestions[:10],
    }


def ai_feedback(resume_text: str, jd_text: str):
    """Optional: only runs if GROQ_API_KEY is set. Returns None otherwise."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    payload = {
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.3,
        "messages": [
            {
                "role": "system",
                "content": "You are a technical recruiter. Give 5 short, specific bullet-point "
                "improvements for this resume for the given job. Do not invent experience.",
            },
            {"role": "user", "content": f"RESUME:\n{resume_text}\n\nJOB DESCRIPTION:\n{jd_text}"},
        ],
    }
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "resume-analyzer/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except Exception as err:  # AI is a bonus, never break the main result
        print("AI feedback skipped:", repr(err))
        return None


# ---------------------------------------------------------------- database ----
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS analyses "
            "(id TEXT PRIMARY KEY, created_at INTEGER, filename TEXT, data TEXT)"
        )


init_db()


# ------------------------------------------------------------------ routes ----
def fail(message: str, status: int = 400):
    return jsonify({"error": message}), status


@app.errorhandler(413)
def too_large(_err):
    return fail("PDF is too large. Keep it under 4 MB.", 413)


@app.get("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.post("/analyze")
def analyze():
    file = request.files.get("resume")
    jd = (request.form.get("job_description") or "").strip()[:MAX_CHARS]

    if file is None or not file.filename:
        return fail("Please upload a resume PDF.")
    if len(jd) < 30:
        return fail("Please paste a longer job description.")

    pdf_bytes = file.read()
    if not pdf_bytes.startswith(b"%PDF"):
        return fail("That file is not a valid PDF.")

    try:
        resume_text = extract_text(pdf_bytes)
    except ValueError as err:
        return fail(str(err))

    result = analyze_text(resume_text, jd)
    result["ai_feedback"] = ai_feedback(resume_text, jd)

    item = {
        "id": str(uuid.uuid4()),
        "created_at": int(time.time()),
        "filename": file.filename[:100],
        **result,
    }
    with db() as conn:
        conn.execute(
            "INSERT INTO analyses (id, created_at, filename, data) VALUES (?, ?, ?, ?)",
            (item["id"], item["created_at"], item["filename"], json.dumps(result)),
        )
    return jsonify(item)


@app.get("/history")
def history():
    rows = db().execute(
        "SELECT id, created_at, filename, data FROM analyses ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    return jsonify(
        [
            {**json.loads(r["data"]), "id": r["id"], "created_at": r["created_at"], "filename": r["filename"]}
            for r in rows
        ]
    )


if __name__ == "__main__":
    app.run(debug=True)