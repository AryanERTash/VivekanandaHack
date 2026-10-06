# Stillpoint

Stillpoint is a responsive reflective mentor inspired by Swami Vivekananda's documented writings. It keeps excerpts and AI interpretation visibly separate, links passages to their sources, and encourages the visitor to decide on a next step for themselves.

## Run locally

Use the supplied Conda environment:

```bash
conda activate p30
pip install -r requirements.txt
uvicorn app:app --reload
```

Open <http://127.0.0.1:8000>.

## Deploy to Vercel

The FastAPI application is exported from the root `app.py`, which Vercel detects as a Python ASGI app. Frontend files live in `public/` for CDN delivery, while `vercel.json` includes the writings and public assets in the Python function bundle for retrieval and local fallback serving. The Vercel Python runtime is set to Python 3.12 in `.python-version`.

1. Import this repository into Vercel, or install the Vercel CLI and run `npx vercel` from the project directory.
2. In the Vercel project’s **Settings → Environment Variables**, add `GROQ_API_KEY` for Preview and Production. Add `GROQ_MODEL` only if you want to override the default.
3. Deploy with `npx vercel --prod` (or push to the connected Git branch).

The local `.env` file is git-ignored and is not uploaded automatically. Configure the key in Vercel before deploying if you want Groq-powered responses. Vercel supports FastAPI apps and streamed Python function responses; data files required by the function are explicitly included in its bundle.

Set `GROQ_API_KEY` in the existing `.env` file or in the process environment to enable streamed LLM reflections. The default model is `openai/gpt-oss-120b`; set `GROQ_MODEL` to use another model available to your Groq account. If no key is configured, the mentor streams a clearly labeled general reflection, and the local retrieval, source excerpts, quiz, and practices continue to work.

On the first retrieval request, the app reads the Markdown records in `data/`, extracts the original source text and metadata, chunks the writings, and creates a TF-IDF vector index in memory. Returned passages preserve their title and source URL. No external embedding service or API key is needed for retrieval.

## What’s included

- Streaming FastAPI chat with Groq, source passages, and a non-impersonation prompt.
- Safe rendering for basic chat Markdown and LaTeX math notation.
- Local retrieval over the supplied writings.
- Multiple-choice quiz with source links.
- Guided paced breathing and a 5–4–3–2–1 grounding activity.
- Browser-local chat history stored in `localStorage`.
- Responsive saffron, parchment, and forest-green styling using the supplied transparent portraits.

Chat history is saved in the current browser's local storage and is not stored by this FastAPI app. When a Groq key is configured, each new message and the recent conversation context are sent to Groq to generate the reflection. The quiz and reflective practices do not require an account.
