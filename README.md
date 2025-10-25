# Ira — AI Companion (FastAPI + Gemini + Redis)

Ira is a human-like AI companion chatbot built using FastAPI, Google Gemini, and Redis.  
It engages in short, context-aware, emotional conversations, retains memory, adapts to user language (English / Hindi / Hinglish), and provides a themed chat UI with streaming responses.

---

## Features

### Conversational intelligence
- Uses Google Gemini API for responses.
- Maintains conversation context and short-term memory in Redis.
- Automatically adapts to the user's language (English, Hindi, Hinglish).
- Produces concise, intentionally incomplete, human-like replies (5–10 words).
- Friendly, caring tone with optional romantic nuance when appropriate.

### Backend
- FastAPI application with asynchronous streaming endpoints.
- Redis for chat history and language memory.
- Dockerized for consistent builds and deployment.
- Health check endpoint `/health` for service readiness monitoring.

### Frontend
- Chat-style UI with:
  - Real-time streaming text rendering (client-paced to mimic typing).
  - Typing animation while the AI prepares a reply.
  - Persistent chat list (left column) and stored conversation threads.
  - Theme selector (Light, Dark, Romantic, Fun, Relax, Nervous).
  - Responsive layout using TailwindCSS.

---

## Architecture

```
User (browser) <--> FastAPI (templates + API) <--> Google Gemini (LLM)
                                  |
                                  +--> Redis (chat history, user language, memory)
```

Core responsibilities:
- FastAPI: routes, streaming, language detection, persistence API.
- Redis: store per-user chat lists, per-chat message lists, per-user language memory.
- Gemini: generate assistant text (called in streaming mode).
- Frontend: render history, stream tokens, theme handling, create new chats.

---

## Core files (what to check into repo)

```
main.py                 - FastAPI app (API, streaming logic, Redis integration)
templates/index.html    - Chat list and new-chat UI
templates/chat.html     - Chat interface, streaming and theme JS
static/style.css        - Optional extra CSS
Dockerfile              - Image build configuration
docker-compose.yml      - Development stack (FastAPI + Redis)
requirements.txt        - Python dependencies
render.yaml (optional)  - Render service + addon definition (IaC)
.env.example            - Example environment variables (do not commit secrets)
README.md               - This document
```

---

## Quick start (local)

1. Clone repository
```bash
git clone https://github.com/<your-username>/ira-ai-companion.git
cd ira-ai-companion
```

2. Create `.env` file (example)
```
GEMINI_API_KEY=your_gemini_api_key_here
REDIS_URL=redis://localhost:6379/0
MODEL_NAME=gemini-2.5-flash
MAX_CONTEXT=20
```

3. Install dependencies
```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

4. Run Redis locally (Docker recommended)
```bash
docker run -d -p 6379:6379 --name ira-redis redis:7
```

5. Start the app
```bash
uvicorn main:app --reload --port 8000
```

6. Open the UI
```
http://localhost:8000
```

---

## Docker (development / simple deployment)

1. Build and run with docker-compose (starts FastAPI and Redis)
```bash
docker compose build
docker compose up
```

2. Access
```
http://localhost:8000
```

3. Stop / remove
```bash
docker compose down
```

Notes:
- Ensure `.env` file exists in the project root before `docker compose up`.
- Docker builds copy your templates and static folders; ensure they are present.

---

## Render deployment (recommended for quick cloud deploy)

High-level steps and rationale:
1. Push repository to GitHub. Render pulls from GitHub for build automation.
2. Create a Redis addon on Render (or use an external Redis Cloud URI).
3. Create a Web Service on Render and choose Docker environment. Set the health check path to `/health`.
4. Configure environment variables in Render service settings:
   - GEMINI_API_KEY
   - REDIS_URL (use the Redis addon URL)
   - MODEL_NAME (e.g., gemini-2.5-flash)
   - MAX_CONTEXT
5. Deploy and monitor build/runtime logs.

Minimal `render.yaml` (optional)
```yaml
services:
  - type: web
    name: ira-chat
    env: docker
    branch: main
    repo: https://github.com/YOUR_USERNAME/YOUR_REPO
    plan: free
    health_check_path: /health

addons:
  - type: redis
    name: ira-redis
    plan: starter
```

Why Render:
- Simple Git-based deployments, managed Redis addon, automated HTTPS, minimal ops overhead. Suitable for demos and small production workloads.

---

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Home page with chat list |
| GET | `/chat/{chat_id}` | Open chat UI for a specific chat |
| POST | `/api/new_chat` | Create a new chat session |
| GET | `/api/chats?uid=<uid>` | List chats for a user |
| POST | `/api/send` | Send a user message and stream assistant reply |
| GET | `/health` | Health check endpoint |

Example request (curl)
```bash
curl -X POST "http://127.0.0.1:8000/api/send"   -H "Content-Type: application/json"   -d '{"uid":"test","chat_id":"","message":"Hey Ira!"}'
```

---

## Themes

- Light: clean, bright interface.
- Dark: low-light friendly, deep gray background and muted bubbles.
- Romantic: soft pink palette and warm accents.
- Fun: vibrant, playful colors.
- Relax: calm pastel and teal-blue tones.
- Nervous: bold purple-red palette.

Theme state is stored in browser localStorage so the selected theme persists per user.

---

## Language detection and behavior

- The backend uses a hybrid approach: `langdetect` plus a small heuristic list of romanized Hindi keywords to detect Hindi/Hinglish reliably.
- The last detected language per user is stored in Redis and used to instruct Gemini to mirror the user's language on subsequent messages.
- Prompt engineering enforces constraints (5–10 words, incomplete replies, friendly tone) and instructs the model to mirror language and maintain context.

---

## Streaming and client pacing

- The server requests Gemini in streaming mode and yields incremental chunks quickly.
- The client receives chunks and renders characters at a controlled rate (characters-per-second) to mimic human typing pace like ChatGPT.
- A typing-dot animation is shown until the first token arrives to improve perceived responsiveness.

---

## Troubleshooting

- 500 Internal Server Error: check application logs (local `uvicorn` logs or `docker logs`) for stack traces. Common causes: missing environment variables, missing `templates/` or `static/` directories, or Redis unreachable.
- Redis connection refused: ensure Redis is running and `REDIS_URL` is correct.
- Gemini authentication error: verify `GEMINI_API_KEY` is valid and configured in the environment where the app runs.
- Docker container exits immediately: ensure the container command runs Uvicorn in the foreground (`--host 0.0.0.0 --port 8000`).
- Streaming not visible: test with `curl` to observe raw chunked output, verify browser JS reads response stream correctly.

---

## Security and production notes

- Never commit `.env` or API keys. Use environment variables on the host or platform secret storage.
- Add authentication (API key or user login) before exposing the service publicly.
- Implement rate limiting or usage quotas to control costs from LLM calls.
- For production, use a managed Redis plan with persistence and backups.
- Monitor logs and set alerts for errors and high latency.

---

## Future enhancements

- Voice input / text-to-speech and speech-to-text integration.
- User authentication and per-user persistent profile storage.
- More robust Hinglish detection via a small classifier or LLM-based language tagger.
- Long-term storage in a relational DB for analytics and GDPR-style data controls.
- Multi-agent pipeline (emotion detector, content filter, response generator).
- Autoscaling and production-grade observability (metrics, tracing, log aggregation).

---

## Author

Tausif Rahman  
Assistant Professor – School of Computer Science, UPES Dehradun  
LinkedIn: https://www.linkedin.com/in/tausifrahman  
GitHub: https://github.com/<your-username>

---

## License

This project is released under the MIT License.

---

## Short tagline (for repository summary)

Human-like conversational AI with memory and multilingual support — powered by FastAPI, Gemini, and Redis.
