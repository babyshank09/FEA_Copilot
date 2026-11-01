<p align="center">
  <img src="src/frontend/assets/fea_copilot_logo_gold.png" alt="FEA Copilot" width="320">
</p>

<p align="center">
  A multi-agent AI assistant for Abaqus CAE. It reads your simulation files, answers FEA questions,<br>
  and writes, runs and debugs Abaqus Python scripts for you.
</p>

---

## What it does

Abaqus workflows involve a lot of manual work: digging through `.inp` keywords, scripting the CAE kernel by hand, and chasing errors in the `.msg` and `.dat` files. FEA Copilot is a chat interface that does that work for you. You talk to it in plain English, and a team of specialised agents plans the task, consults Abaqus documentation, writes the script, runs it in Abaqus, and fixes it if it fails.

- **Understands your model files.** Upload `.inp`, `.odb` or `.step`/`.stp` files. They are parsed (in Abaqus itself, where needed) into a structured summary the agents can reason about.
- **Answers engineering questions.** Questions about results, loads, boundary conditions, mesh quality and similar topics are answered from your actual files. A senior reviewer agent checks every quantitative claim.
- **Writes and runs Abaqus scripts.** The coding agent generates Abaqus Python. It is syntax-checked and run headless through `abaqus cae noGUI=...`. Errors go back to the agents for diagnosis and retry.
- **Captures images of models and results.** Contour plots and model views are rendered from `.inp` and `.odb` files.
- **Asks for missing inputs.** When a task needs parameters you haven't given, the app shows form widgets so you can fill them in.
- **Uses retrieval (RAG) over Abaqus documentation.** It runs a hybrid search over the Abaqus Scripting Reference and a procedural workflow guide. You can also upload your own PDFs to extend the knowledge base.
- **Supports multiple users.** Accounts, login and saved conversation threads are handled by a FastAPI and PostgreSQL backend.

## Architecture

```
┌──────────────────────┐      REST (JWT)      ┌───────────────────────────┐
│  Streamlit frontend  │ ───────────────────▶ │  FastAPI backend          │
│  chat · uploads ·    │                      │  auth · users · threads · │
│  dynamic widgets     │                      │  admin    ──▶ PostgreSQL  │
└──────────┬───────────┘                      └───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         LangGraph agent workflow                         │
│                                                                          │
│                         ┌──────────────┐                                 │
│      ┌─────────────────▶│ FEA Planner  │◀─────────────────┐              │
│      │                  │  ("Friday")  │                  │              │
│      │                  └──────┬───────┘                  │              │
│      │        ┌──────────┬─────┴─────┬──────────┐         │              │
│      │        ▼          ▼           ▼          ▼         │              │
│  File upload  Consultant  SME ◀──▶ Senior SME  Coding ◀──▶ Execution     │
│  + relevance                                   Agent       Agent         │
│  checker                Interface Agent (input widgets)       │          │
│                                                               ▼          │
│                                                    abaqus cae noGUI=...  │
└──────────────────────────────────────────────────────────────────────────┘
           │
           ▼
   Hybrid RAG: Chroma (OpenAI embeddings) + BM25 → RRF → Cohere rerank
```

### The agents

| Agent | Role |
|---|---|
| **FEA Planner** | Project manager and the only agent that talks to the user. It breaks requests into plans and sends work to the other agents. |
| **File Relevance Checker** | Checks that uploaded files are valid Abaqus or CAD files and relevant to the request. |
| **Consultant** | Engineering and scripting advisor for open-ended "how should I approach this?" questions. |
| **SME** | Subject-matter expert. It answers FEA questions using the parsed file data and the documentation RAG. |
| **Senior SME** | Reviewer that checks the SME's quantitative claims before they reach the user. |
| **Coding Agent** | Writes Abaqus Python scripts, using the scripting-reference RAG and a syntax-check tool. |
| **Execution Agent** | Runs scripts in Abaqus, detects new and changed output files, and diagnoses failures for the Coding Agent. |
| **Interface Agent** | Turns the Planner's parameter requests into Streamlit input widgets. |

### Retrieval pipeline

Documents are split into chunks and stored in two Chroma collections, `abaqus_scripting_docs` and `procedural_docs`. At query time an LLM rewrites the question into several variations. Each variation is searched with both vector similarity and BM25. The results are merged with Reciprocal Rank Fusion and reranked with Cohere `rerank-english-v3.0`.

## Tech stack

- **Agents:** LangGraph, LangChain
- **LLMs:** OpenAI and Azure OpenAI
- **Retrieval:** ChromaDB, BM25 (`rank_bm25`), Cohere Rerank, OpenAI `text-embedding-3-small`
- **Frontend:** Streamlit, packaged as a desktop app with `streamlit-desktop-app`
- **Backend:** FastAPI, SQLAlchemy, PostgreSQL, JWT auth (`python-jose`, `passlib`/`bcrypt`)
- **Simulation:** Abaqus CAE (SIMULIA), driven through its Python scripting interface

## Project structure

```
src/
├── app.py                      # Streamlit entry point
├── frontend/
│   ├── streamlit/              # UI, auth screens, styling
│   ├── utils/api_client.py     # Calls to the FastAPI backend
│   └── config/                 # Frontend settings (API URL, timeouts)
└── backend/
    ├── main.py                 # FastAPI app
    ├── routers/                # auth, users, threads, admin endpoints
    ├── models.py, database.py  # SQLAlchemy models and engine
    ├── graph/graph.py          # LangGraph workflow definition
    ├── nodes/nodes.py          # Agent node implementations
    ├── state/state.py          # Graph state and structured-output schemas
    ├── prompts/                # Agent system prompts
    ├── tools/tools.py          # RAG, file-reading, syntax-check, screenshot tools
    ├── rag/                    # Ingestion and hybrid retrieval pipelines
    ├── llm/                    # LLM client configuration
    ├── abaqus_scripts/         # Scripts run inside Abaqus (parsing, rendering)
    ├── script_templates/       # Script templates and the Abaqus runner
    └── vectorstore/            # Chroma DB and BM25 indexes
```

## Getting started

### Prerequisites

- Python 3.12
- **Abaqus CAE** installed and licensed, with the `abaqus` command on your `PATH` (on Windows this is usually `C:\SIMULIA\Commands`)
- PostgreSQL
- API keys for OpenAI, Azure OpenAI and Cohere

### 1. Install

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
# OpenAI
OPENAI_API_KEY=

# Azure OpenAI
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_VERSION=

# Cohere (reranking)
CO_API_KEY=

# PostgreSQL
DB_USER=
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432
DB_NAME=

# Frontend (optional)
API_BASE_URL=http://127.0.0.1:8000
```

Create an empty database with the name you set in `DB_NAME`. The tables are created automatically the first time the backend starts.

### 3. Run

Start the backend from the project root:

```bash
uvicorn src.backend.main:app --reload
```

In a second terminal, start the frontend:

```bash
python -m streamlit run src/app.py
```

Then open the URL Streamlit prints, create an account, and start a conversation.

## Usage examples

- *"Here's my bracket model. What loads and boundary conditions are applied?"* (with a `.inp` file attached)
- *"What's the peak von Mises stress in the last frame, and where does it occur?"* (with a `.odb` file attached)
- *"Write a script to mesh this part with a global seed of 2 mm and submit the job."*
- *"Show me a contour plot of displacement magnitude."*
- *"Why did my job abort with excessive distortion?"*

## Limitations

- Script execution needs a local Abaqus installation and licence. Without one, the app can still answer questions from the documentation, but it cannot parse `.odb` files or run scripts.
- Generated scripts run on your machine with your user's permissions. Review them before running the app against important data.

## Author

**Sivashankar Subramaniam**
