from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
PUBLIC_DIR = ROOT / "public"
STATIC_DIR = PUBLIC_DIR / "static"
IMAGE_DIR = PUBLIC_DIR / "images"
load_dotenv(ROOT / ".env")

app = FastAPI(title="Stillpoint — a reflective mentor")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")


def _extract_document(path: Path) -> dict[str, str] | None:
    """Read the original dataset text, keeping provenance attached to each passage."""
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    front = re.search(r"(?ms)^---\s*\n(.*?)\n---", raw)
    meta: dict[str, str] = {}
    if front:
        for line in front.group(1).splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip().lower()] = value.strip()
    topic = meta.get("topic", "The Complete Works")
    subtopic = meta.get("subtopic", path.stem)
    url = meta.get("url", "")
    section = re.search(r"(?ms)^## Original Dataset Text\s*\n(.*?)(?:\n---\s*\n|\Z)", raw)
    text = section.group(1).strip() if section else ""
    # Source records store this field as a JSON array of text fragments.
    try:
        value = json.loads(text)
        if isinstance(value, list):
            text = "\n".join(str(item) for item in value)
        elif isinstance(value, str):
            text = value
    except (json.JSONDecodeError, TypeError):
        pass
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\[\d+\]", "", text)
    if len(text) < 40 or text.startswith("Error:"):
        # A subset of records has its full source text in the scraped Wiki Content.
        section = re.search(r"(?ms)^## Wiki Content\s*\n(.*?)(?:\n---\s*\n|\Z)", raw)
        if section:
            candidate = re.sub(r"\s+", " ", section.group(1)).strip()
            if len(candidate) > len(text) and not candidate.startswith("Error:"):
                text = candidate
    if len(text) < 40:
        return None
    return {"text": text, "topic": topic, "title": subtopic, "url": url}


def _make_chunks(doc: dict[str, str]) -> list[dict[str, str]]:
    # Paragraphs make for more useful citations than arbitrary fixed windows.
    paragraphs = re.split(r"(?<=[.!?])\s+|\n+", doc["text"])
    chunks: list[dict[str, str]] = []
    current = ""
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(current) + len(paragraph) > 1100 and current:
            chunks.append({**doc, "text": current})
            current = ""
        current = f"{current} {paragraph}".strip()
    if current:
        chunks.append({**doc, "text": current})
    return chunks


@lru_cache(maxsize=1)
def _index() -> tuple[list[dict[str, str]], Any, Any]:
    from sklearn.feature_extraction.text import TfidfVectorizer

    chunks: list[dict[str, str]] = []
    for path in DATA_DIR.glob("*.md"):
        doc = _extract_document(path)
        if doc:
            chunks.extend(_make_chunks(doc))
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=160_000, sublinear_tf=True)
    matrix = vectorizer.fit_transform([item["text"] for item in chunks]) if chunks else None
    return chunks, vectorizer, matrix


def retrieve(query: str, limit: int = 4) -> list[dict[str, Any]]:
    from sklearn.metrics.pairwise import cosine_similarity

    chunks, vectorizer, matrix = _index()
    if not chunks or matrix is None:
        return []
    query_vector = vectorizer.transform([query])
    scores = cosine_similarity(query_vector, matrix).ravel()
    best = scores.argsort()[::-1][:limit]
    results = []
    for index in best:
        if scores[index] <= 0:
            continue
        item = chunks[int(index)]
        results.append({**item, "score": round(float(scores[index]), 3)})
    return results


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=3000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=12)


@app.get("/")
async def home() -> FileResponse:
    return FileResponse(PUBLIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    chunks, _, _ = _index()
    return {"ok": True, "indexed_passages": len(chunks), "llm_available": bool(os.getenv("GROQ_API_KEY"))}


@app.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    sources = retrieve(request.message, limit=3)
    contexts = "\n\n".join(
        f"[{i + 1}] {s['title']} — {s['topic']}\n{s['text'][:1150]}\nSource URL: {s['url']}"
        for i, s in enumerate(sources)
    ) or "No close passage was found in the supplied local writings."

    async def events():
        safe_sources = [
            {"title": s["title"], "topic": s["topic"], "url": s["url"], "excerpt": s["text"][:340]}
            for s in sources
        ]
        yield f"event: sources\ndata: {json.dumps(safe_sources, ensure_ascii=False)}\n\n"
        api_key = os.getenv("GROQ_API_KEY")
        sent_token = False
        if api_key:
            try:
                from groq import AsyncGroq

                client = AsyncGroq(api_key=api_key)
                messages: list[dict[str, str]] = [{
                    "role": "system",
                    "content": (
                        "You are Stillpoint, a reflective mentor inspired by Swami Vivekananda's documented writings. "
                        "Never impersonate him. Treat the retrieved passages as the only source for any attributed teaching. "
                        "Do not invent or loosely paraphrase a quotation as if exact. When using a passage, refer to its title; "
                        "the interface separately displays its source and labels your words as interpretation. If no relevant "
                        "passage was retrieved, say so briefly and give general reflective support without attributing it to him. "
                        "Be warm, grounded, concise (120-180 words). Acknowledge the feeling without diagnosing. Ask one useful "
                        "open question and suggest one small action the person chooses. Use only basic Markdown: paragraphs, **bold**, *italics*, "
                        "simple bullet or numbered lists, and headings up to ###. Never emit raw HTML, tables, or fenced code. When math is useful, "
                        "write inline math as $expression$ and display math as $$expression$$. Do not add equations when they do not help. "
                        "Do not make promises or shame the user. "
                        "For signs of immediate danger or self-harm, encourage reaching a trusted person and local emergency or crisis support.\n\n"
                        f"Retrieved passages from the supplied corpus:\n{contexts}"
                    ),
                }]
                for turn in request.history[-8:]:
                    role = "assistant" if turn.get("role") == "assistant" else "user"
                    content = str(turn.get("content", ""))[:1500]
                    if content:
                        messages.append({"role": role, "content": content})
                messages.append({"role": "user", "content": request.message})
                stream = await client.chat.completions.create(
                    model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
                    messages=messages,
                    temperature=0.55,
                    max_tokens=420,
                    stream=True,
                )
                async for part in stream:
                    token = part.choices[0].delta.content if part.choices else None
                    if token:
                        sent_token = True
                        yield f"event: token\ndata: {json.dumps(token, ensure_ascii=False)}\n\n"
                await client.close()
            except Exception:
                fallback = (
                    "\n\nThe connection paused before the reflection finished. Please try again if you’d like a complete response."
                    if sent_token else _fallback_reflection(request.message, sources)
                )
                for word in re.findall(r"\S+\s*", fallback):
                    yield f"event: token\ndata: {json.dumps(word, ensure_ascii=False)}\n\n"
        else:
            fallback = _fallback_reflection(request.message, sources)
            for word in re.findall(r"\S+\s*", fallback):
                yield f"event: token\ndata: {json.dumps(word, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _fallback_reflection(message: str, sources: list[dict[str, Any]]) -> str:
    prompt = "A passage from the supplied writings appears alongside this reply" if sources else "I could not find a close passage in the supplied writings, so I will keep this reflection general"
    return (
        f"Thank you for putting this into words. {prompt}. A difficult moment can feel like a verdict, "
        "but it may help to look at the specific event separately from what it says about you as a person. "
        "What is one part of this situation that you can influence today, even a little? Try writing that down, "
        "then choose one manageable next step and a time to take it. You do not have to solve everything at once. "
        "The passage shown here is a documented source; this response is a practical reflection, not Vivekananda's words."
    )


QUIZ = [
    {"question": "In the well-known address on the theme of strength, what does Vivekananda encourage listeners to seek?", "options": ["Strength and courage", "Avoiding every challenge", "Approval before acting", "A perfect outcome"], "answer": 0, "search": "strength is life weakness is death address"},
    {"question": "In his writings on education, what is education meant to help bring out?", "options": ["The perfection already within a person", "Only facts for examinations", "One fixed career path", "Dependence on praise"], "answer": 0, "search": "education manifestation perfection already in man"},
    {"question": "What does the Parliament address 'Why We Disagree' use the well story to illustrate?", "options": ["The limits of a narrow point of view", "That travel solves every conflict", "That questions should be avoided", "That people must agree on everything"], "answer": 0, "search": "Why We Disagree frog well narrow views"},
    {"question": "In teachings about action, what quality is repeatedly encouraged alongside effort?", "options": ["Steadiness and perseverance", "Waiting for certainty", "Comparing your pace with everyone", "Giving up after one setback"], "answer": 0, "search": "perseverance steady work effort teachings"},
    {"question": "The phrase 'Arise, awake' is commonly associated with which kind of invitation?", "options": ["Awakening and striving toward a goal", "Avoiding responsibility", "Seeking comfort above all", "Refusing to learn"], "answer": 0, "search": "Arise awake stop not until goal reached"},
]


@app.get("/api/quiz")
async def quiz() -> list[dict[str, Any]]:
    questions = []
    for entry in QUIZ:
        matches = retrieve(entry["search"], limit=1)
        source = matches[0] if matches else None
        questions.append({
            "question": entry["question"], "options": entry["options"],
            "answer": entry["answer"], "explanation": "This question checks the idea behind a documented teaching. Read the linked passage and decide how you would apply it in your own words.",
            "source": {"title": source["title"], "topic": source["topic"], "url": source["url"]} if source else None,
        })
    return questions


@app.get("/api/search")
async def search(q: str) -> list[dict[str, Any]]:
    if len(q) < 2:
        raise HTTPException(400, "Enter a longer search phrase")
    return [{"title": x["title"], "topic": x["topic"], "url": x["url"], "excerpt": x["text"][:340]} for x in retrieve(q)]
