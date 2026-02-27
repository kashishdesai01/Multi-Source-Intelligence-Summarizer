# Agentic Multi-Document Summarization System

> **Classify → Score Credibility → Resolve Conflicts → Summarize**
> Type-specific routing for research papers, news articles, blog posts, and legal documents.

---

## Features

- 🤖 **Agentic orchestration** — LangChain-style async agent dispatches type-specific sub-agents
- 🔬 **Research papers** — scored by journal tier, citations, h-index, recency via Semantic Scholar
- 📰 **News articles** — scored by Media Bias/Fact Check trust DB, corroboration, byline, recency
- ✍️ **Blog posts** — scored by domain authority, author credentials (LLM), external references
- ⚖️ **Legal documents** — scored by official source, jurisdiction, statute citations
- ⚡ **Conflict resolution** — pluggable strategies: Weighted Vote, Majority Vote, Highest Credibility, Conservative
- 📚 **RAG summarizer** — FAISS retrieval + GPT-4o-mini (or BART offline fallback)
- 🗄️ **MongoDB** — async Beanie ODM for jobs, documents, reports
- ⚛️ **React + Vite** — premium dark-mode glassmorphism UI with credibility rings and conflict cards
- ☁️ **AWS** — ECS Fargate (backend) + S3/CloudFront (frontend) + Terraform IaC + GitHub Actions CI/CD

---

## Quick Start (Local)

### 1. Clone & configure

```bash
git clone https://github.com/<you>/multidoc-summarizer.git
cd multidoc-summarizer
cp .env.example .env
# Fill in your OPENAI_API_KEY in .env
```

### 2. Start MongoDB + Backend

```bash
# Requires Docker
docker compose up -d          # starts MongoDB on 27017

# Or run backend standalone:
pip install -e ".[dev]"
uvicorn api.main:app --reload --port 8000
```

### 3. Start Frontend

```bash
cd frontend
npm install
npm run dev                   # opens http://localhost:5173
```

### 4. Run Tests

```bash
pytest tests/ -v --tb=short
```

---

## AWS Deployment Guide

### Prerequisites

You'll need:
- An [AWS account](https://aws.amazon.com/free/) (free tier covers much of this)
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)
- [Terraform ≥ 1.6](https://developer.hashicorp.com/terraform/install)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- A [MongoDB Atlas](https://www.mongodb.com/atlas) account (free M0 cluster)

---

### Step 1 — Create an AWS account & IAM user

1. Go to [aws.amazon.com](https://aws.amazon.com) → **Create an AWS Account**.
2. Sign in to the AWS Console → search **IAM** → **Users** → **Create user**.
3. Name it `multidoc-deployer`, select **Programmatic access**.
4. Attach policy: `AdministratorAccess` (for initial setup; scope down later).
5. Download the **Access Key ID** and **Secret Access Key**.

### Step 2 — Configure AWS CLI

```bash
aws configure
# AWS Access Key ID:     <paste key id>
# AWS Secret Access Key: <paste secret>
# Default region:        us-east-1
# Default output format: json
```

### Step 3 — Create MongoDB Atlas cluster (free)

1. Sign up at [mongodb.com/atlas](https://www.mongodb.com/atlas/database).
2. Create a **Shared (M0 Free)** cluster in `us-east-1`.
3. Add a database user: **Database Access** → Add New User.
4. Allow access from anywhere (or your ECS CIDR): **Network Access** → `0.0.0.0/0`.
5. Get your connection string: **Connect** → **Drivers** → copy the `mongodb+srv://...` URI.

### Step 4 — Create Terraform state bucket

```bash
aws s3 mb s3://multidoc-terraform-state --region us-east-1
aws s3api put-bucket-versioning \
  --bucket multidoc-terraform-state \
  --versioning-configuration Status=Enabled
```

### Step 5 — Deploy infrastructure

```bash
cd infra
terraform init
terraform apply \
  -var="openai_api_key=sk-your-key" \
  -var="mongodb_uri=mongodb+srv://user:pass@cluster.mongodb.net/multidoc"
```

This provisions:
- **ECR** repository for the Docker image
- **VPC** with public/private subnets
- **ALB** (Application Load Balancer)
- **ECS Fargate** cluster + task + service
- **AWS Secrets Manager** for API keys
- **S3 bucket** + **CloudFront** distribution for the React app

### Step 6 — Set GitHub Actions secrets

In your GitHub repo → **Settings → Secrets and variables → Actions**, add:

| Secret | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | Your IAM user key |
| `AWS_SECRET_ACCESS_KEY` | Your IAM user secret |
| `VITE_API_URL` | `https://<your-alb-dns>` |
| `FRONTEND_BUCKET` | S3 bucket name (from Terraform output) |
| `CLOUDFRONT_DIST_ID` | CloudFront distribution ID (from Terraform output) |

### Step 7 — Push to deploy

```bash
git push origin main
# GitHub Actions will: test → build Docker → push ECR → deploy ECS → build React → sync S3 → invalidate CloudFront
```

Your app will be live at the **CloudFront URL** printed by Terraform.

---

## Architecture

```
Users ──→ CloudFront ──→ S3 (React SPA)
                    ↓ /api calls
            ALB ──→ ECS Fargate (FastAPI) ──→ MongoDB Atlas
                         ↓
              Semantic Scholar API (research)
              OpenAI API (RAG summarizer)
```

### Agent Pipeline

```
Submit Docs
    │
    ▼
┌─────────────────────────────────────────┐
│            Orchestrator Agent            │
│  1. Classify (BART zero-shot + GPT)     │
│  2. Dispatch to type-specific agent     │
│     ├── ResearchAgent (Scholar API)     │
│     ├── NewsAgent (trust DB)            │
│     ├── BlogAgent (domain DB + LLM)     │
│     └── LegalAgent (gov source check)  │
│  3. ConflictResolver (cosine clusters) │
│  4. Summarizer (RAG / BART)            │
│  5. Persist SummaryReport → MongoDB    │
└─────────────────────────────────────────┘
    │
    ▼
 SummaryReport (sections, conflicts, claims)
```

---

## Conflict Resolution Strategies

| Strategy | Best For | Logic |
|---|---|---|
| `weighted_vote` | Research papers | Highest credibility score wins; ties flagged |
| `majority_vote` | News articles | ≥2 high-trust sources agreement wins |
| `highest_credibility_wins` | Legal docs | Always take the top-scored source |
| `conservative` | Unknown / sensitive | All disagreements flagged as unresolved |

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | For RAG mode | GPT-4o-mini for RAG summarization + claim extraction |
| `MONGODB_URI` | Yes | MongoDB connection string |
| `SUMMARIZER_BACKEND` | No (default: `rag`) | `rag` or `bart` |
| `SEMANTIC_SCHOLAR_KEY` | No | Increases Semantic Scholar rate limits |
| `NEWSAPI_KEY` | No | Optional NewsAPI for article fetching |

---

## Project Structure

```
multidoc-summarizer/
├── agents/
│   ├── orchestrator.py      # Master agent coordinator
│   ├── classifier.py        # BART zero-shot + GPT fallback
│   ├── base_agent.py        # Abstract DocumentAgent
│   ├── research_agent.py    # Journal tier, citations, h-index
│   ├── news_agent.py        # Trust DB, corroboration
│   ├── blog_agent.py        # Domain authority, LLM credentials
│   └── legal_agent.py       # Official source, jurisdiction
├── conflict/
│   ├── resolver.py          # Semantic clustering + strategy dispatch
│   └── strategies.py        # 4 pluggable resolution strategies
├── summarizer/
│   ├── bart_summarizer.py   # Offline BART
│   ├── rag_summarizer.py    # FAISS + GPT-4o-mini
│   └── factory.py
├── db/
│   ├── models.py            # Beanie ODM documents
│   └── connection.py
├── api/
│   ├── main.py              # FastAPI endpoints
│   └── schemas.py
├── data/
│   ├── news_trust_db.json   # Media trust scores
│   └── domain_authority_db.json
├── frontend/                # React + Vite TypeScript SPA
├── infra/                   # Terraform AWS modules
├── tests/                   # pytest suite
├── Dockerfile
├── docker-compose.yml
└── .github/workflows/deploy.yml
```
