# Deploy guide — 15 minutes, no credit card

Three services, all on their free tiers:

| Layer    | Service       | Free tier limit                                  |
|----------|---------------|--------------------------------------------------|
| Database | Neo4j Aura    | 1 instance, 200K nodes, 400K relationships       |
| Backend  | Render        | 512 MB RAM, sleeps after 15 min idle             |
| Frontend | Vercel Hobby  | Unlimited static, 100 GB bandwidth/month         |

Do them in this order — backend needs the DB URL, frontend needs the backend URL.

---

## 1. Neo4j Aura (5 minutes)

1. Go to **https://console.neo4j.io/** → sign in with Google.
2. Click **New Instance** → choose **AuraDB Free**.
3. Pick a region close to your Render region (e.g. `europe-west1`).
4. **Save the credentials shown** — you will not see the password again:
   - `NEO4J_URI` — looks like `neo4j+s://abc123.databases.neo4j.io`
   - `NEO4J_USER` — usually `neo4j`
   - `NEO4J_PASSWORD` — random string
5. Wait until status is **Running** (~60 s).

> Note: AuraDB Free pauses after 3 days of inactivity. To wake it, sign in and click Resume.

---

## 2. Backend on Render (5 minutes)

1. Go to **https://dashboard.render.com/select-repo?type=blueprint**.
2. Sign in with GitHub. Authorize Render to read `euzghe/codebase-explainer`.
3. Pick the repo → Render reads `render.yaml` and shows the service.
4. Fill in the env vars when prompted (`sync: false` items):

   | Variable             | Value                                                          |
   |----------------------|----------------------------------------------------------------|
   | `ANTHROPIC_API_KEY`  | Your key from https://console.anthropic.com                    |
   | `NEO4J_URI`          | From step 1                                                    |
   | `NEO4J_USER`         | `neo4j`                                                        |
   | `NEO4J_PASSWORD`     | From step 1                                                    |
   | `FRONTEND_ORIGIN`    | Put a placeholder for now (e.g. `https://placeholder.vercel.app`); update after step 3 |
   | `GITHUB_TOKEN`       | Leave empty (optional, used for higher clone rate limits)     |

5. Click **Apply** → first build takes ~3 min.
6. Copy the URL — looks like `https://codebase-explainer-backend.onrender.com`. Verify:
   ```
   curl https://codebase-explainer-backend.onrender.com/api/health
   # → {"ok":true}
   ```

> Free Render web services sleep after 15 min idle. First request after sleep takes ~30 s to wake up.

---

## 3. Frontend on Vercel (5 minutes)

1. Go to **https://vercel.com/new** → sign in with GitHub.
2. **Import** `euzghe/codebase-explainer`.
3. In the configure step:
   - **Root Directory:** click *Edit* and set to `frontend`
   - **Framework Preset:** Next.js (auto-detected)
   - **Environment Variables:** add one:

     | Name                    | Value                                              |
     |-------------------------|----------------------------------------------------|
     | `NEXT_PUBLIC_API_BASE`  | The backend URL from step 2                        |

4. Click **Deploy** → ~2 min build.
5. Copy the deployed URL — looks like `https://codebase-explainer.vercel.app`.

---

## 4. Wire CORS (30 seconds)

The backend's `FRONTEND_ORIGIN` env still has the placeholder from step 2. Fix it:

1. Render → your backend service → **Environment** tab.
2. Update `FRONTEND_ORIGIN` to your Vercel URL (e.g. `https://codebase-explainer.vercel.app`).
3. Click **Save Changes** — Render auto-redeploys (~1 min).

---

## Done

Open your Vercel URL → paste any public GitHub repo (try `https://github.com/pallets/flask` first — small, well-structured) → wait ~30 s for ingest → ask a question.

## Troubleshooting

- **Render build fails on `pip install`** — check the build log for which package failed. The `tree-sitter-language-pack` wheel needs Python 3.11; if Render picks a different Python, set `PYTHON_VERSION=3.11` in env vars.
- **Backend 503s on first request** — Render free tier was sleeping. Hit it once with curl, then retry from the UI.
- **"Repo not ingested yet" error** — overview was requested before ingest finished. Wait until status badge shows `Ready`.
- **CORS error in browser console** — `FRONTEND_ORIGIN` on the backend doesn't match your Vercel URL exactly. Must include `https://` and no trailing slash.
- **Neo4j connection error** — Aura URI must use `neo4j+s://` (the secure variant), not `bolt://`.
