# Prism Framework

**Prism Framework** — a modular, multi-stage LLM pipeline for reproducible long-form story generation.
This repository contains the Plan and Write modules, database logging routines, example outputs, and scripts for running experiments and saving results for auditing and analysis.

---

## Table of Contents

1. [Overview](#overview)
2. [Key Features](#key-features)
3. [Repository Structure](#repository-structure)
4. [Requirements](#requirements)
5. [Quick Start (Local)](#quick-start-local)
6. [Detailed Setup](#detailed-setup)

   * [Python environment](#python-environment)
   * [MySQL database](#mysql-database)
   * [ZhipuAI / LLM client configuration](#zhipuai--llm-client-configuration)
7. [How to run](#how-to-run)

   * [Run Plan module](#run-plan-module)
   * [Run Write module (using plan)](#run-write-module-using-plan)
   * [Run as script / subprocess (batch runner)](#run-as-script--subprocess-batch-runner)
8. [Outputs & Logging](#outputs--logging)
9. [Database schema (example)](#database-schema-example)
10. [Recommended `.gitignore`](#recommended-gitignore)
11. [Security & Privacy](#security--privacy)
12. [Troubleshooting](#troubleshooting)
13. [Contributing](#contributing)
14. [License & Citation](#license--citation)

---

# Overview

Prism Framework splits creative generation into two main stages:

* **Plan** (`Plan.py`) — constructs a structured plan (central conflict, characters, setting, key plot points) and runs multi-agent style analysis (Beam Focusing, Spectrum Conference, Spectral Analysis, Focal Decision, optional Beam Reforging). All prompts, responses and intermediate logs are saved to a MySQL table for reproducibility and audit.

* **Write** (`Write.py`) — consumes a plan and iteratively generates the story across five canonical sections (Exposition → Rising Action → Climax → Falling Action → Resolution). Each section includes local beam-focusing, spectral analysis, potential refinements, and a final synthesis into a `Full Story`.

Both modules are written to be modular, easy to call from other orchestration code, and friendly to batch / subprocess invocation.

---

# Key Features

* Structured plan generation with multi-step LLM interactions
* Multi-agent-inspired evaluation passes (conferencing + parallel critiques)
* Automatic logging of requests and responses to MySQL for auditability
* CLI/script `main(...)` entrypoints for easy batch integration
* Outputs written as `.json` and `.txt` for downstream consumption and evaluation
* Flexible — supports running Plan-only, Write-only (accepting precomputed plan), or full pipeline

---

# Repository Structure

```
Prism-Framework/
├─ Plan.py                # Plan module (generate structured plan)
├─ Write.py               # Write module (generate story from plan)
├─ outputs/               # Example output files (plan, write JSON, story texts)
├─ README.md              # <-- this file
├─ .gitignore             # recommended (see section)
└─ docs/                  # (optional) extra docs, diagrams, example prompts
```

---

# Requirements

* Python 3.8+
* `mysql-connector-python` (or `mysql-connector`)
* `zhipuai` client Python package (used in the example code; replace with your LLM client if needed)
* MySQL server (local or remote) with a database for `story_logs`
* Git (for repository management)

Install typical Python deps:

```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
# .\venv\Scripts\Activate.ps1   # Windows PowerShell
pip install -r requirements.txt
```

If you don't have `requirements.txt`, at minimum:

```bash
pip install mysql-connector-python zhipuai
```

---

# Quick Start (Local)

1. Clone this repo (or create it and push your project):

   ```bash
   git clone https://github.com/Celestial-Being-00/Prism-Framework.git
   cd Prism-Framework
   ```

2. Configure environment variables (see next section). Example using PowerShell:

   ```powershell
   setx ZHIPUAI_API_KEY "your_api_key_here"
   ```

3. Start MySQL and ensure the `agent_room` database and `story_logs` table exist (example schema below).

4. Run Plan for a quick test:

   ```bash
   python Plan.py --example_id test1 --creative_input "Write a short fantasy about a clockmaker who discovers time-travel." --output_dir outputs/
   ```

   (The code also supports calling `main(...)` with kwargs, or relying on environment variables.)

5. Run Write using the produced plan:

   ```bash
   python Write.py --example_id test1 --plan_path outputs/story_plan.json --output_dir outputs/
   ```

---

# Detailed Setup

## Python environment

* Create and activate a virtual environment.
* Install dependencies:

  ```bash
  pip install mysql-connector-python zhipuai
  ```
* (Optional) freeze versions:

  ```bash
  pip freeze > requirements.txt
  ```

## MySQL database

Create a MySQL database and a logging table used by the Plan/Write modules:

```sql
CREATE DATABASE agent_room CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE agent_room;

CREATE TABLE story_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  story_id VARCHAR(255),
  request_message LONGTEXT,
  response_message LONGTEXT,
  timestamp DATETIME,
  type VARCHAR(255)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Adjust `db_config` in `Plan.py` and `Write.py` if you use different credentials or host.

## ZhipuAI / LLM client configuration

The example code reads `ZHIPUAI_API_KEY` from the environment (with a fallback default in the script for debug). **Do not commit real API keys to git.**

Set it in your shell:

* PowerShell:

  ```powershell
  setx ZHIPUAI_API_KEY "your_real_key_here"
  ```

  Then restart your terminal.

* Linux / macOS:

  ```bash
  export ZHIPUAI_API_KEY="your_real_key_here"
  ```

If you use a different API provider, replace the `ZhipuAI` client calls in the code with your client’s API call wrapper; keep the same `messages` structure if possible.

---

# How to run

> Both `Plan.py` and `Write.py` expose `main(...)` functions and also support being run as scripts reading environment variables. This makes them easy to plug into batch runners or subprocess orchestration.

### Run Plan module

Example (script mode):

```bash
python Plan.py
# or (recommended explicit):
python -c "import Plan; Plan.main(example_id='ex1', creative_input='A detective in a floating city must solve a forgotten murder', output_dir='outputs/')"
```

Common `main` kwargs:

* `example_id` / `story_id` — identifier for the run
* `creative_input` / `task` — the original writing prompt/task
* `output_dir` — directory where `story_plan.json` will be written
* `plan_output_file` / `plan_file` — optional path to write the plan JSON

### Run Write module (using plan)

```bash
python Write.py
# or explicit:
python -c "import Write; Write.main(example_id='ex1', plan_path='outputs/story_plan.json', output_dir='outputs/')"
```

`Write.main` will read the plan JSON and generate `story_write.json` and `story_text.txt` by default.

---

# Outputs & Logging

* **JSON outputs** (`story_plan.json`, `story_write.json`) contain structured results and intermediate metadata.
* **Text output** (`story_text.txt`) contains the final synthesized story.
* **Database logs** record every LLM request and response with a `type` tag for auditability.

Example `outputs/` structure:

```
outputs/
├─ story_plan.json
├─ story_write.json
├─ story_text.txt
└─ logs/ (optional)
```

---

# Database schema (example)

A minimal `story_logs` table schema is shown above. You can extend this with indexes, user/run metadata, or a separate `runs` table that aggregates multiple log rows into a single experiment run.

---

# Recommended `.gitignore`

Create `.gitignore` at repo root:

```
venv/
__pycache__/
*.pyc
*.pyo
*.pyd
.env
.env.*
outputs/
*.sqlite3
.DS_Store
.idea/
.vscode/
*.log
secrets.json
```

This avoids committing virtual environments, secrets, large outputs, and IDE configs.

---

# Security & Privacy

* **Never commit API keys** or database passwords to Git. Use environment variables or a secrets manager.
* The example code contains a debug default API key string for convenience; replace and remove before publishing.
* Be cautious storing sensitive user data in database logs. If you log prompts/responses with user data, treat the database as sensitive and secure it (encryption, ACLs).

---

# Troubleshooting

**Cannot push to GitHub (connection reset / proxy errors):**

* If you see `Failed to connect to 127.0.0.1:xxxxx`, remove Git proxy settings:

  ```bash
  git config --global --unset http.proxy
  git config --global --unset https.proxy
  ```
* If `Recv failure: Connection was reset`, try:

  1. Use SSH remote instead of HTTPS:

     ```bash
     git remote set-url origin git@github.com:Celestial-Being-00/Prism-Framework.git
     ```

     Then set up your `~/.ssh/id_rsa.pub` on GitHub and `git push`.
  2. Configure Git to use your local VPN proxy (if you use Clash/V2Ray):

     ```bash
     git config --global http.proxy http://127.0.0.1:7890
     git config --global https.proxy http://127.0.0.1:7890
     ```
  3. Use a mirror proxy:

     ```bash
     git remote set-url origin https://ghproxy.com/https://github.com/Celestial-Being-00/Prism-Framework.git
     ```

**Renaming folders with spaces:**

```bash
git mv "Prisma Framework" "Prism Framework"
git commit -m "Rename folder: Prisma Framework -> Prism Framework"
git push
```

**LLM call fails / timeouts:**

* Check API key validity and network access to the LLM endpoint.
* Inspect `story_logs` table for the raw request/response error message.

---

# Contributing

Contributions and bug reports are welcome.

* Fork the repo
* Create a feature branch (`git checkout -b feat/your-feature`)
* Commit with clear messages
* Create a pull request describing the change and its rationale

If you plan to extend integration to other LLM providers, please add adapter wrappers and unit tests.

---

# License & Citation

Choose a license appropriate for your project (MIT, Apache-2.0, etc.). Add `LICENSE` file to the repository root.

If you use this framework in academic work, please cite your repo and any foundational papers that inspired the design (Agent Room, multi-agent LLM frameworks, etc.).
