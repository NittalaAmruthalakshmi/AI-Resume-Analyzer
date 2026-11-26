# AI Resume Analyzer

Upload a resume PDF and paste a job description. The app scores the match, shows matched and missing skills, runs a resume checklist, and gives improvement suggestions. It runs fully on your own computer: **no AWS account and no API key needed.**

**Stack:** Python, Flask, SQLite, pypdf, HTML/CSS/JavaScript

## Run it

```bash
cd resume-analyzer-local
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 in your browser.

## How the score works

| Part | Weight | What it measures |
|------|--------|------------------|
| Skills match | 55% | Known skills in the job description that also appear in your resume |
| Keyword match | 25% | Top keywords from the job description found in your resume |
| Resume quality | 20% | Checklist: contact info, sections, action verbs, numbers, length |

Missing skills and failed checklist items become your suggestions.

## Files

| File | Purpose |
|------|---------|
| `app.py` | Flask backend: PDF reading, scoring, history in SQLite |
| `static/index.html` | The web page |
| `analyses.db` | Created automatically, stores past analyses |

## Optional: add AI written feedback

The app works without this. If you want extra AI-written tips, get a free key from console.groq.com and set it before starting the app:

- Windows: `set GROQ_API_KEY=your_key`
- Mac/Linux: `export GROQ_API_KEY=your_key`

Never put the key in `index.html` or upload it to GitHub.

## Limits (be honest about these in interviews)

- Scoring is rule-based. It only knows the skills listed in the `SKILLS` dictionary in `app.py`, so add more skills there for your field.
- Scanned (image-only) PDFs can't be read.
- The score is a guide, not what real hiring systems use.

## Ideas to extend

- Add more skills and aliases to the `SKILLS` dictionary
- Compare one resume against several job descriptions
- Download the report as PDF
- Add user login
- Deploy it free online (for example on Render or PythonAnywhere) and put the live link in your resume