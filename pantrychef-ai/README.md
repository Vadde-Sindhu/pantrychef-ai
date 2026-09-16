# PantryChef AI

Tell Chef Nova what's in your kitchen — get a live, streamed recipe built around your
ingredients, dietary needs, and cuisine preference, then ask follow-up cooking questions
in a lightweight chat.

Built for the **Vibe Coding Masterclass** capstone. Meets every project requirement:
responsive frontend, secure backend, LLM streaming, Docker packaging, and AWS deployment.

---

## 1. Tech stack

| Layer | Choice |
|---|---|
| Frontend | Vanilla HTML / CSS / JavaScript (no build step, fully responsive) |
| Backend | Python **FastAPI**, served by Uvicorn |
| LLM | Google **Gemini** (`gemini-2.5-flash`) via the official `google-generativeai` SDK, streamed |
| Container | Docker (single image, non-root user, health check) |
| Cloud | AWS App Runner *(recommended)* or Elastic Beanstalk (Docker platform) |

Architecture:

```
Browser (frontend/)                     AWS App Runner container
┌───────────────────────┐   HTTPS       ┌─────────────────────────────┐
│ index.html/style/script│ ───────────▶ │ FastAPI (backend/main.py)   │
│ fetch() + ReadableStream│ ◀─── stream ─│  /api/generate  /api/chat   │
└───────────────────────┘               │        │                    │
                                          │        ▼                    │
                                          │  Google Gemini API           │
                                          │  (key read from env var)     │
                                          └─────────────────────────────┘
```

The API key lives only in the container's environment — it is never sent to, or
readable from, the browser.

---

## 2. Run it locally

```bash
cd pantrychef-ai
cp .env.example .env
# edit .env and paste your real GOOGLE_API_KEY (get one free, no card
# required, at https://aistudio.google.com/app/apikey)

pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Open **http://localhost:8000** — the FastAPI app serves both the API and the static UI.

## 3. Run it with Docker (mirrors production)

```bash
docker build -t pantrychef-ai .
docker run --rm -p 8000:8000 --env-file .env pantrychef-ai
```

Visit **http://localhost:8000**. Confirm `/api/health` returns `{"status":"ok", "configured": true}`.

---

## 4. Deploy to AWS (free-tier friendly)

### Option A — AWS App Runner (recommended, simplest)

1. **Push the image to Amazon ECR**
   ```bash
   aws ecr create-repository --repository-name pantrychef-ai
   aws ecr get-login-password --region <your-region> \
     | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<your-region>.amazonaws.com

   docker build -t pantrychef-ai .
   docker tag pantrychef-ai:latest <account-id>.dkr.ecr.<your-region>.amazonaws.com/pantrychef-ai:latest
   docker push <account-id>.dkr.ecr.<your-region>.amazonaws.com/pantrychef-ai:latest
   ```

2. **Create the App Runner service**
   - Console → App Runner → *Create service* → Source: **Container registry** → Amazon ECR → select the image.
   - Deployment trigger: Manual (or Automatic if you'll push new tags later).
   - Port: `8000`.
   - **Environment variables** (Configure service → Environment variables): add
     `GOOGLE_API_KEY`, `GEMINI_MODEL`, `ALLOWED_ORIGINS` (set this to your App Runner
     URL once it's assigned, e.g. `https://xxxx.us-east-1.awsapprunner.com`).
   - Instance: 1 vCPU / 2 GB is more than enough (App Runner free tier eligible usage).
   - Health check path: `/api/health`.
   - Create & deploy. App Runner gives you a public **HTTPS URL** automatically — no
     load balancer or certificate setup needed.

3. **Verify**: open the HTTPS URL, generate a recipe, confirm the chat works.

### Option B — AWS Elastic Beanstalk (Docker platform)

1. Install the EB CLI: `pip install awsebcli`.
2. From the project root:
   ```bash
   eb init pantrychef-ai --platform docker --region <your-region>
   eb create pantrychef-env --single --instance-type t3.micro
   ```
3. Set secrets (never in source control):
   ```bash
   eb setenv GOOGLE_API_KEY=your-key-here GEMINI_MODEL=gemini-2.5-flash ALLOWED_ORIGINS=https://<your-eb-url>
   ```
4. `eb open` to view the live public URL. Beanstalk terminates HTTPS for you when you
   attach an ACM certificate to the environment's load balancer (or use the default
   `http://` endpoint for course-submission purposes and note it in your report).

### Cost & safety guardrails

- Both options fit comfortably in the AWS Free Tier for a short-lived class project.
- Set an **AWS Budget alert** (Billing → Budgets → Create budget, e.g. $5 threshold)
  before deploying, per the assignment's cost-awareness guideline.
- Tear down the service (`App Runner → Delete service` or `eb terminate`) after grading
  if you don't want it running indefinitely.

---

## 5. Security checklist (met by this project)

- [x] `GOOGLE_API_KEY` is read only from environment variables (`os.environ`), never
      hard-coded, never sent to the frontend.
- [x] `.env` is git-ignored; only `.env.example` (no real secret) is committed.
- [x] `.dockerignore` excludes `.env` from the image build context.
- [x] CORS is restricted via `ALLOWED_ORIGINS` (set to the real deployed origin in prod).
- [x] Backend runs as a non-root container user.
- [x] Basic request validation (`pydantic` field limits) guards against oversized inputs.

---

## 6. Project structure

```
pantrychef-ai/
├── backend/
│   ├── main.py            # FastAPI app: streaming routes + static file serving
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── script.js
├── Dockerfile
├── .dockerignore
├── .env.example
├── .gitignore
└── README.md
```

---

## 7. What "streaming" looks like here

`/api/generate` and `/api/chat` open a `StreamingResponse` in FastAPI backed by the
Google `google-generativeai` SDK's `chat.send_message(..., stream=True)` text stream.
The frontend reads the HTTP response body with `fetch(...).body.getReader()` and
re-renders the recipe card on every chunk, so text appears progressively rather than
popping in all at once after a multi-second wait.
