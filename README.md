**Creator & Lead Architect:** **GENIUS NISHCHAL**

# AgentGit — Transactional Rollback, Speculative Sandbox & Time-Travel Kernel for AI Agents

> **Databases have ACID transactions. Developers have Git. Documents have `Ctrl+Z`. AI agents had no Undo button—until now.**

**AgentGit** is a lightweight, framework-agnostic transactional kernel in Python that wraps any AI agent (`google-genai`, LangGraph, CrewAI, OpenAI SDK) in a **SHA-256 Content-Addressable Storage (CAS)** and **reversible SQLite + filesystem shadow layer**. Every tool invocation becomes an atomic, hashable node in a **Directed Acyclic Graph (DAG)**—enabling deterministic time-travel rollback, runtime invariant guardrails, and speculative multi-branch racing.

---

## Key Capabilities

1. **Atomic File & SQLite Snapshots (`@repo.atomic_tool`):** Captures content-addressable file manifests and deterministic SQL dumps before and after every agent tool execution with line-level unified diffs.
2. **Invariant Circuit Breaker:** Evaluates post-condition safety rules (maximum file deletions, maximum database row drops) *before* advancing `HEAD`. Destructive hallucinations are blocked mid-flight and auto-reverted in milliseconds.
3. **Speculative Parallel Branching ("What-If" Arena):** Forks competing agent strategies onto isolated shadow branches (`branch_A_aggressive` vs. `branch_B_safe`), scores safety invariants, auto-merges the winning branch into `main`, and discards unsafe paths.
4. **Deterministic Time-Travel (`revert_to(commit_id)`):** Rewinds both workspace files and database tables to any historical commit node in one click or API call.

---

## Verified Benchmark Results (25-Scenario Stress Suite)

| Metric | Measured Result |
| :--- | :--- |
| **Total Agent Operations Tested** | 25 (13 Safe Mutations + 12 Destructive Attacks) |
| **Catastrophic Attacks Intercepted** | **12 / 12 (100.0% Catch Rate)** |
| **Unrecovered Data Corruption** | **0 Files Lost / 0 Rows Lost (0.0%)** |
| **Mean Snapshot + Diff Overhead** | **8.8 – 34.9 ms per tool call** |
| **CAS Storage Deduplication Savings** | **87.5% – 94.2%** |

---

## Quickstart

```bash
git clone [https://github.com/Genius-Nishchal/AgentGit.git](https://github.com/Genius-Nishchal/AgentGit.git)
cd AgentGit
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Run the 25-scenario reliability benchmark
python benchmark.py

# Launch the interactive Time-Travel & Speculative Studio
uvicorn server:app --host 127.0.0.1 --port 8899

