"""
PantryChef AI — backend
FastAPI server that keeps the LLM API key on the server side, streams
responses to the frontend in real time, and serves the static UI.
"""
import os
import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pantrychef")

# ---------------------------------------------------------------------------
# Configuration — all secrets come from environment variables, never from
# frontend code, and never committed to version control (see .env.example).
# LLM: Google Gemini (has a genuine no-card-required free tier), via the
# official google-generativeai SDK.
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("GOOGLE_API_KEY")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",")]

if not API_KEY:
    logger.warning(
        "GOOGLE_API_KEY is not set. Set it in a .env file locally, or as a "
        "secret environment variable in your AWS App Runner / Elastic Beanstalk "
        "configuration before deploying."
    )
else:
    genai.configure(api_key=API_KEY)

app = FastAPI(title="PantryChef AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class RecipeRequest(BaseModel):
    ingredients: str = Field(..., min_length=1, max_length=500)
    dietary: Optional[str] = Field("", max_length=200)
    cuisine: Optional[str] = Field("", max_length=100)
    servings: Optional[int] = Field(2, ge=1, le=12)


class ChatMessage(BaseModel):
    role: str
    content: str = Field(..., max_length=2000)


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    recipe_context: Optional[str] = Field("", max_length=4000)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_RECIPE = """You are Chef Nova, the in-app cooking assistant for PantryChef AI.
Given ingredients the user already has, dietary restrictions, a cuisine preference, and a
serving size, invent ONE achievable recipe using mostly those ingredients (a handful of
common pantry staples like oil, salt, water are fine to assume). Respond in markdown, in
exactly this shape and nothing else:

# <Recipe Name>
<one-sentence description>

## Ingredients
- <quantity> <ingredient>
(one per line, scaled correctly to the requested servings)

## Steps
1. <step>
2. <step>
...

## Chef's Tip
<one short, practical tip — a substitution, timing trick, or storage note>

Keep it concise and realistic for a home kitchen. If something essential is missing,
suggest a substitution instead of refusing to answer."""

SYSTEM_PROMPT_CHAT = """You are Chef Nova, a friendly, concise home-cooking assistant inside
PantryChef AI. The user may ask follow-up questions about the recipe you just generated
(substitutions, technique, timing, scaling, leftovers). Answer directly and practically in
a few sentences, using light markdown only where it helps (short bullet lists are fine)."""


# ---------------------------------------------------------------------------
# Streaming helper
# ---------------------------------------------------------------------------
def _to_gemini_history(messages: list):
    """Translate our simple [{role, content}, ...] messages into Gemini's
    expected history format, mapping 'assistant' -> 'model'."""
    history = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        history.append({"role": role, "parts": [m["content"]]})
    return history


def stream_gemini_text(system_prompt: str, messages: list):
    if API_KEY is None:
        def _err():
            yield "Server is not configured with a GOOGLE_API_KEY. Set it as an environment variable and restart the server."
        return _err()

    def event_generator():
        try:
            model = genai.GenerativeModel(
                model_name=MODEL,
                system_instruction=system_prompt,
            )
            history = _to_gemini_history(messages)
            # Last message is sent as the new turn; everything before it is history.
            *prior, last = history
            chat = model.start_chat(history=prior)
            response = chat.send_message(last["parts"][0], stream=True)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.exception("Gemini streaming error")
            yield f"\n\n_(The AI service returned an error: {str(e)})_"

    return event_generator()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    return JSONResponse({"status": "ok", "model": MODEL, "configured": API_KEY is not None})


@app.post("/api/generate")
async def generate_recipe(req: RecipeRequest):
    if not req.ingredients.strip():
        raise HTTPException(status_code=422, detail="Please list at least one ingredient.")

    user_msg = (
        f"Ingredients on hand: {req.ingredients}\n"
        f"Dietary restrictions: {req.dietary or 'none'}\n"
        f"Cuisine preference: {req.cuisine or 'any'}\n"
        f"Servings: {req.servings}"
    )
    messages = [{"role": "user", "content": user_msg}]
    return StreamingResponse(
        stream_gemini_text(SYSTEM_PROMPT_RECIPE, messages),
        media_type="text/plain; charset=utf-8",
    )


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not req.messages:
        raise HTTPException(status_code=422, detail="No messages provided.")

    messages = []
    if req.recipe_context:
        messages.append({
            "role": "user",
            "content": f"(Context — the current recipe on screen)\n{req.recipe_context}",
        })
        messages.append({
            "role": "assistant",
            "content": "Got it, I have the recipe in front of me. What would you like to know?",
        })
    messages.extend({"role": m.role, "content": m.content} for m in req.messages)

    return StreamingResponse(
        stream_gemini_text(SYSTEM_PROMPT_CHAT, messages),
        media_type="text/plain; charset=utf-8",
    )


# ---------------------------------------------------------------------------
# Static frontend (mounted last so /api/* routes above take priority)
# ---------------------------------------------------------------------------
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")