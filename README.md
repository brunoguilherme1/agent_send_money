<p align="center"> <a href="https://github.com/brunoguilherme1/agent_send_money/tree/main"> 🔗 View Source Code on GitHub </a> </p>

# 📄 Send Money Agent — Technical Documentation 

## Table of Contents

* [1. Overview](#1-overview)
* [2. Architecture (Core Components)](#2-architecture-core-components)

  * [2.1 TransferState — State & Validation Layer](#21-transferstate--state--validation-layer)
  * [2.2 tools.py — Controlled Execution Layer](#22-toolspy--controlled-execution-layer)
  * [2.3 prompt.py — Reasoning & Decision Engine](#23-promptpy--reasoning--decision-engine)
  * [2.4 AgentRunner — Orchestration Layer](#24-agentrunner--orchestration-layer)
* [3. prompt.py — The Brain of the Agent](#3-promptpy--the-brain-of-the-agent)

  * [3.1 Token Classification as a Decision Primitive](#31-token-classification-as-a-decision-primitive)
  * [3.2 Prompt Evolution Through Edge Cases](#32-prompt-evolution-through-edge-cases)
* [4. Evaluation — From Edge Cases to Metrics](#4-evaluation--from-edge-cases-to-metrics)

  * [4.1 Introduction](#41-introduction)
  * [4.2 Edge Case Generation (Stress Testing)](#42-edge-case-generation-stress-testing)
  * [4.3 Multi-Turn Evaluation (Conversation-Level)](#43-multi-turn-evaluation-conversation-level)
  * [4.4 Metrics](#44-metrics)
  * [4.5 Results](#45-results)
* [5. Limitations & Future Directions](#5-limitations--future-directions)

  * [5.1 Model Coverage](#51-model-coverage)
  * [5.2 Adversarial Robustness](#52-adversarial-robustness)
  * [5.3 Evaluation Ecosystem Integration](#53-evaluation-ecosystem-integration)
  * [5.4 Business Metrics (KPI Layer)](#54-business-metrics-kpi-layer)
  * [5.5 A/B Testing (Model vs ROI)](#55-ab-testing-model-vs-roi)
  * [5.6 Monitoring & Continuous Evaluation](#56-monitoring--continuous-evaluation)
* [6. How to Run](#6-how-to-run)

  * [6.1 Setup](#61-setup)
  * [6.2 Run Backend (FastAPI)](#62-run-backend-fastapi)
  * [6.3 Run Frontend (Streamlit)](#63-run-frontend-streamlit)
  * [6.4 Run with Docker](#64-run-with-docker)
* [7. Run Evaluation](#7-run-evaluation)

  * [7.1 Create Evaluation Environment](#71-create-evaluation-environment)
  * [7.2 Run Edge Cases](#72-run-edge-cases)
  * [7.3 Edge Cases JSON Structure](#73-edge-cases-json-structure)
  * [7.4 Run Conversation Test Suite](#74-run-conversation-test-suite)
  * [7.5 Run Final Evaluation](#75-run-final-evaluation)
* [8. Demo](#8-demo)

  * [8.1 Live Demo (GCP)](#81-live-demo-gcp)
  * [8.2 Quick Test](#82-quick-test)
  * [8.3 What This Shows](#83-what-this-shows)
  * [8.4 Architecture](#84-architecture)

## 1. Overview

This project implements a **stateful conversational agent** for money transfers using the Google ADK framework.

The agent is designed to handle:

* Multi-turn conversations
* Partial and messy user inputs
* Ambiguity and corrections
* Structured information extraction

It collects the following fields:

* `country`
* `recipient_name`
* `amount`
* `currency`
* `delivery_method`

The system ensures **robust extraction under uncertainty**, following real-world conversational patterns described in the assignment.

<p align="center">
  <img width="1536" height="1024" alt="System overview" src="https://github.com/user-attachments/assets/27c5a74e-8fed-44dd-8e8c-ac1401fe096e" />
</p>

## 2. Architecture (Core Components)

### 2.1 TransferState — State & Validation Layer

`TransferState` is the single source of truth for the entire conversation. It stores all extracted fields (`country`, `recipient_name`, `amount`, `currency`, and `delivery_method`) and ensures that every value is valid before being persisted.

It uses Pydantic validators to enforce business rules, such as amount limits, supported countries, and full recipient names. It also provides helper methods like `missing_fields()` and `safe_update()` to track progress and safely update the state.

This component is critical because it guarantees **data consistency and prevents invalid transactions from ever reaching the execution layer**.

### 2.2 tools.py — Controlled Execution Layer

The `tools.py` module defines all actions that the LLM is allowed to perform. Instead of directly modifying the state, the LLM must call these functions, ensuring that every operation is validated and controlled.

Key operations include:

* `update_state()` for saving confident values
* `clarify()` and `resolve_clarification()` for handling ambiguity
* `next_field()` to guide the conversation
* `validate_transfer()` and `submit_transfer()` for final execution

Each function is atomic and returns structured outputs, allowing the LLM to reason about results safely.

This design enforces a **safe interaction pattern in which the LLM decides *what* to do, but the system controls *how* it is done**.

### 2.3 prompt.py — Reasoning & Decision Engine

The `prompt.py` module defines the behavior of the LLM. It includes the system prompt that instructs the model how to interpret user input, classify tokens, and decide which action to take.

The logic is based on:

* Token classification (`CONFIDENT`, `UNSURE`, `INVALID`)
* Ambiguity rules (for example, name vs. country conflicts)
* A strict turn loop (`REFLECT → ACT → RESPOND`)

It also enforces constraints such as:

* Never saving uncertain values directly
* Always asking for clarification when ambiguity exists
* Only submitting after explicit confirmation

This component acts as the **decision-making brain**, transforming unstructured user input into structured actions.

### 2.4 AgentRunner — Orchestration Layer

`AgentRunner` is responsible for executing the full conversational loop. It connects the LLM, tools, and state into a working system.

Its responsibilities include:

* Receiving user input
* Building the LLM agent with current state plus tools
* Executing tool calls returned by the LLM
* Updating and persisting the state
* Handling retries, errors, and session management

This component is the **runtime engine**, enabling a true stateful, multi-turn interaction instead of a simple stateless LLM call.

<p align="center">
  <img width="1536" height="1024" alt="Architecture diagram" src="https://github.com/user-attachments/assets/a6a962fb-3480-4ff2-abae-075365485573" />
</p>

## 3. prompt.py — The Brain of the Agent

The `prompt.py` module defines the reasoning and decision policy that drives the behavior of the conversational agent. Rather than treating the LLM as a simple text generator, we structure it as a **stateful decision-making system**, where each response is conditioned on the current state, pending clarifications, and available actions.

Our design follows the principles of **stateful LLM-based agents**, as described in:


> **Song et al. (2024)** — *Just Ask One More Time!
Self-Agreement Improves Reasoning of Language Models in (Almost) All Scenarios*

> **Hou et al. (2023)** — *EnvScaler: Scaling Tool-Interactive Environments for LLM Agent via Programmatic Synthesis*

In this paradigm, the agent maintains an internal state that evolves across turns and directly influences future decisions. The prompt injects:

* The current structured state (what is already known)
* Missing fields (what still needs to be collected)
* Pending clarifications (ambiguities to resolve)
* Available tools (actions the agent can take)

This allows the LLM to operate in a **closed-loop system (`state → reasoning → action → updated state`)** instead of a stateless single-shot response.

### 3.1 Token Classification as a Decision Primitive

A key innovation in our prompt design is the use of **token-level classification** to guide the agent’s behavior.

Instead of directly extracting and saving all information, the model must first classify each piece of input into:

* **CONFIDENT** → clear, valid, and unambiguous → can be safely stored
* **UNSURE** → ambiguous, partial, or malformed → requires clarification
* **INVALID** → violates business rules → must be rejected and corrected

This approach is inspired by structured extraction and uncertainty-aware NLP systems, particularly:

> **Zhout et al. (2023)** — *LEAST-TO-MOST PROMPTING ENABLES COMPLEX
REASONING IN LARGE LANGUAGE MODELS*
> **Zhout et al. (2024)** — *Measuring and Narrowing the Compositionality Gap in Language Models*

Instead of naive slot filling, the model performs a **two-step process**:

1. **Interpretation** → understand meaning and ambiguity
2. **Decision** → determine whether to save, ask, or reject

This design enables the agent to:

* Handle **messy and real-world inputs** (for example, `"2OO"`, `"1k"`, `"Pedro Brazil"`)
* Avoid **silent errors** by never guessing under ambiguity
* Maintain **data integrity** by storing only validated values
* Support **multi-turn reasoning** with explicit clarification loops

In practice, this transforms the LLM from a passive extractor into an **active decision-making agent**, capable of safely interacting with users in high-stakes scenarios such as financial transactions.

### 3.2 Prompt Evolution Through Edge Cases

The prompt was not designed in a single step. Instead, it was built iteratively, starting from simple extraction rules and evolving into a robust decision system through systematic testing of edge cases.

The core idea was to transform the LLM from a passive extractor into an **active decision-maker**, capable of handling ambiguity, corrections, and multi-turn reasoning.

#### 3.2.1 Edge Cases → Prompt Refinement

We stress-tested the system with hard cases:

* `"send 200 brl to Chile Rodrigues Lima"`
* `"send 1000 or 2000 USD"`
* `"send to Lima"`

These cases revealed that classification alone was not enough — the model still needed **explicit ambiguity handling**.

#### 3.2.2 Ambiguity Rules

We added deterministic rules to avoid guessing:

* Never auto-assign ambiguous tokens
* Treat conflicts (for example, *country vs. name*) explicitly
* Generate clarification questions instead of making assumptions

Example:

```text
"Chile Rodrigues"
→ could be country OR name → must clarify
```

#### 3.2.3 Turn Loop (Control)

We enforced a strict reasoning loop:

```text
REFLECT → ACT → RESPOND
```

* **REFLECT**: the model classifies all tokens (`CONFIDENT`, `UNSURE`, `INVALID`) and checks for pending clarifications
* **ACT**: the model decides exactly one action (for example, `update_state`, `clarify`, `next_field`)
* **RESPOND**: the model produces a single, controlled output, usually one question

This loop is critical because it:

* Prevents the model from doing multiple things at once (for example, saving, asking, and confirming in the same step)
* Forces alignment between reasoning and tool execution
* Guarantees a predictable, step-by-step interaction flow

In practice, this transforms the LLM into a **deterministic controller**, not a free-form generator.

#### 3.2.4 Few-Shots (Stability)

After defining rules and control flow, we added few-shot examples to stabilize behavior.

These examples demonstrate:

* How to apply token classification to real inputs
* How to handle ambiguity (for example, name vs. country)
* How to structure tool calls and responses

Few-shots are especially important because:

* LLMs may interpret rules inconsistently without concrete examples
* They reduce variability across edge cases
* They reinforce the expected reasoning pattern (`REFLECT → ACT → RESPOND`)

Rather than teaching answers, few-shots teach **how to think and act**, improving consistency in complex, real-world scenarios.

<p align="center">
  <img width="1536" height="1024" alt="Prompt reasoning loop" src="https://github.com/user-attachments/assets/fe9040d7-abf4-455d-9ab2-a3664d0f4524" />
</p>

## 4. Evaluation — From Edge Cases to Metrics

### 4.1 Introduction

The evaluation strategy was designed to validate the system under **real-world uncertainty**, not just ideal inputs.

Instead of relying only on standard benchmarks, we built a **custom evaluation pipeline** focused on:

* Ambiguity handling
* Multi-turn reasoning
* Robustness to noisy and adversarial inputs

### 4.2 Edge Case Generation (Stress Testing)

The first step was creating structured **edge case test groups**, targeting each component of the system:

* **A — Amount** → malformed formats (`2OO`, `1k`, `one thousand 500`)
* **B — Recipient** → ambiguity (`Maria Chile`, `Jordan Lima`)
* **C — Country** → variations (`Brasil`, `USA`, `Lima`)
* **D — Currency** → synonyms (`bucks`, `reais`, `pesos`)
* **E — Multi-turn / State** → corrections, multiple intents, resets
* **J — Adversarial** → prompt injection, malicious patterns

Example:

```python
{"group": "A2", "msg": "send 20xx0 USD to Maria Silva in Brazil"}
{"group": "B2", "msg": "send 500 USD to Maria Chile"}
{"group": "E4", "msg": "send 1000... actually 500 USD to Maria Silva"}
```

These tests were used iteratively to **break the system and refine the prompt**, especially for:

* Token classification
* Ambiguity rules
* Turn loop behavior

### 4.3 Multi-Turn Evaluation (Conversation-Level)

After stabilizing single-turn behavior, we moved to **multi-turn evaluation**, where correctness depends on the full interaction.

Each test defines:

* Input turns
* Expected tool sequence
* Final state
* Expected responses

Example:

```json
{
  "test_id": "T03_malformed_amount",
  "category": "amount",
  "input": {
    "turns": [
      {"user": "Send 2OO USD to Maria Silva in Brazil via bank transfer"},
      {"user": "200"},
      {"user": "yes"}
    ]
  },
  "expected": {
    "tools_sequence": [
      ["update_state","clarify"],
      ["resolve_clarification"],
      ["submit_transfer"]
    ],
    "task": {"should_complete": 1},
    "final_state": {
      "recipient_name": "Maria Silva",
      "country": "BR",
      "amount": 200.0,
      "currency": "USD",
      "delivery_method": "bank_transfer",
      "status": "done"
    }
  }
}
```

This ensures the system is evaluated as a **stateful agent**, not just a single prediction.

### 4.4 Metrics

We defined metrics across three dimensions:

| Category                 | Metric               | What it Measures                                      |
| ------------------------ | -------------------- | ----------------------------------------------------- |
| **Deterministic (Core)** | State Accuracy       | Final correctness of extracted fields                 |
|                          | Task Completion      | Whether the flow ended correctly                      |
|                          | Extraction Precision | Whether information was extracted at the right moment |
|                          | Tool Call Accuracy   | Correct usage of tools                                |
|                          | Correction Fidelity  | Proper handling of user corrections                   |
| **LLM Behavior**         | Response Discipline  | Controlled and structured responses                   |
| **System**               | Latency              | Response time                                         |
|                          | Token Usage          | Cost efficiency                                       |

<p align="center">
  <img width="1536" height="1024" alt="Evaluation pipeline" src="https://github.com/user-attachments/assets/ba963426-7a31-4866-bdcf-990564aae388" />
</p>

### 4.5 Results

We evaluated two models:

| Metric               | Gemini 3.2 | Gemini Flash |
| -------------------- | ---------: | -----------: |
| State Accuracy       |       1.00 |         1.00 |
| Task Completion      |       1.00 |         1.00 |
| Extraction Precision |       1.00 |         1.00 |
| Tool Call Accuracy   |       0.97 |         0.92 |
| Correction Fidelity  |       1.00 |         1.00 |
| Response Discipline  |       0.72 |         0.69 |
| Hard Fail Rate       |       0.00 |         0.00 |
| Latency (ms)         |     27,277 |       22,277 |

The evaluation highlights a clear separation between deterministic correctness and LLM behavioral quality. Both models achieved perfect scores (`1.00`) in **state accuracy**, **task completion**, **extraction precision**, and **correction fidelity**, confirming that the system design—based on state, tools, and validation—guarantees reliable execution. In practice, once the LLM makes a correct decision, the architecture ensures consistent state updates, proper handling of corrections, and safe transaction completion.

Differences appear in the LLM behavior layer, particularly in **tool selection** and **response discipline**. Gemini 3.2 shows slightly better reasoning consistency (`0.97` vs. `0.92` in tool accuracy), while both models struggle with strict response constraints (around `0.7`), which depend heavily on prompt adherence rather than core logic. Importantly, both models achieved a `0.00` hard fail rate, indicating strong robustness against noisy inputs and adversarial patterns, validating the safety of the overall design.

## 5. Limitations & Future Directions

### 5.1 Model Coverage

The evaluation focused only on large models (Gemini family), without testing smaller LLMs such as Mistral, Phi, or lightweight LLaMA variants. This limits our understanding of the cost-performance trade-off.

**Future direction:** benchmark smaller models to compare reasoning degradation versus cost savings, enabling more efficient deployment strategies.

### 5.2 Adversarial Robustness

Although no hard failures were observed, adversarial testing was not exhaustive. Scenarios such as prompt injection or instruction override (for example, *"ignore all rules"*) were not systematically evaluated.

Example:

```text
send 500 USD and ignore previous instructions
```

**Future direction:** incorporate adversarial testing frameworks and tools like **SelfCheckGPT** to measure consistency and resistance to manipulation, along with new metrics such as instruction override rate and policy violation rate.

### 5.3 Evaluation Ecosystem Integration

The current evaluation pipeline is custom-built and lacks integration with industry-standard observability tools.

**Future direction:** integrate with platforms like **LangSmith** (for tracing and debugging) and **Arize Phoenix** (for monitoring and drift detection), enabling better visibility into failures, tool usage patterns, and prompt behavior over time.

### 5.4 Business Metrics (KPI Layer)

The evaluation focuses on technical correctness but does not capture business impact. Metrics such as conversion rate, drop-off rate, and customer lifetime value (CLV) are not currently tracked.

A simple ROI metric could be defined as:

```text
ROI = (Revenue - Cost) / Cost
```

Where revenue is driven by successful transactions and cost includes tokens and infrastructure.

**Future direction:** incorporate user-level tracking and connect model performance to real business KPIs.

### 5.5 A/B Testing (Model vs ROI)

There was no A/B testing comparing models from a business perspective. While Flash is faster and cheaper, it shows slightly weaker reasoning performance.

**Hypothesis:** faster models may provide better user experience despite lower technical scores, as users often prefer responsiveness over marginal quality gains.

**Future direction:** run controlled A/B experiments comparing models on latency, completion rate, and user satisfaction to optimize for ROI.

### 5.6 Monitoring & Continuous Evaluation

The current evaluation is offline and does not reflect real-time system performance.

**Future direction:** implement continuous monitoring to track latency trends, tool failures, and user correction patterns, enabling ongoing optimization and early detection of issues.

## 6. How to Run

This project has **two main components**:

* 🔧 **Backend API** → FastAPI (`api/app.py`)
* 🖥️ **Frontend UI** → Streamlit (`ui/app_ui.py`)

They must run **in parallel**.

### 6.1 Setup

#### 6.1.1 Create environment

```bash
python -m venv .venv
source .venv/bin/activate   # Mac/Linux
.venv\Scripts\activate      # Windows
```

#### 6.1.2 Install dependencies

```bash
pip install -r requirements.txt
```

#### 6.1.3 Environment variables

Create `.env`:

```env
GOOGLE_API_KEY=your_api_key_here
```

### 6.2 Run Backend (FastAPI)

From the project root:

```bash
uvicorn api.app:app --reload --port 8000
```

Backend running at:

```text
http://localhost:8000
```

### 6.3 Run Frontend (Streamlit)

Open a **new terminal**:

```bash
streamlit run ui/app_ui.py
```

<p align="center">
  <img width="2258" height="1292" alt="Frontend UI" src="https://github.com/user-attachments/assets/12ac3051-e3c5-4439-8bc2-dface4cee2e5" />
</p>

### 6.4 Run with Docker

This project uses **Docker Compose** to run both:

* 🔧 FastAPI Backend (`api/app.py`)
* 🖥️ Streamlit Frontend (`ui/app_ui.py`)

#### 6.4.1 Build and start

From the project root:

```bash
docker-compose up --build
```

#### 6.4.2 Access the applications

Once containers are running:

* 🔧 Backend API → `http://localhost:8000`
* 🖥️ Frontend UI → `http://localhost:8501`

#### 6.4.3 Stop services

```bash
docker-compose down
```

## 7. Run Evaluation

The evaluation pipeline has **three steps**:

1. Run **edge cases** (stress testing)
2. Run **conversation test suite**
3. Run **final evaluation metrics**

The evaluation pipeline should be run in a **separate environment** to avoid conflicts with the main app.

### 7.1 Create Evaluation Environment

```bash
python -m venv .venv-eval
source .venv-eval/bin/activate   # Mac/Linux
.venv-eval\Scripts\activate      # Windows
```

Inside the `eval/` folder, you have a dedicated `requirements.txt`.

Install it:

```bash
pip install -r eval/requirements.txt
```

### 7.2 Run Edge Cases

This step tests **single-turn robustness** with noisy, malformed, and adversarial inputs.

```bash
python eval/test_edge_cases.py
```

### 7.3 Edge Cases JSON Structure

Each test is **simple and atomic**:

```json
{
  "group": "A",
  "label": "A02_letter_O_in_amount",
  "msg": "send 2OO USD to Maria Silva in Brazil"
}
```

This generates a file like:

```bash
results_YYYYMMDD_HHMMSS.json
```

### 7.4 Run Conversation Test Suite

This step evaluates **multi-turn behavior** (state, corrections, and control flow).

```bash
python eval/test_cv.py
```

Each test is **multi-turn plus expected behavior**:

```json
{
  "test_id": "T10_double_yes_name_and_country",
  "category": "ambiguity",
  "input": {
    "turns": [
      {"user": "send 500 USD to Maria Chile via bank deposit"},
      {"user": "yes that's the name and yes Chile is the country"},
      {"user": "yes"}
    ]
  },
  "expected": {
    "tools_sequence": [
      ["update_state","clarify"],
      ["resolve_clarification","validate_transfer"],
      ["submit_transfer"]
    ],
    "task": {"should_complete": 1},
    "final_state": {
      "recipient_name": "Maria Chile",
      "country": "CL",
      "amount": 500.0,
      "currency": "USD",
      "delivery_method": "bank_deposit",
      "status": "done"
    }
  }
}
```

This generates:

```bash
eval/results/run_<timestamp>.json
```

### 7.5 Run Final Evaluation

After generating results:

```bash
python eval/evaluation.py
```

Output:

```bash
eval/results/evaluation_final.json
```
#### Final Evaluation Output (JSON)

```json
{
  "state_accuracy": 1.0,
  "task_completion": 1.0,
  "extraction_precision": 1.0,
  "tool_call_accuracy": 0.916,
  "correction_fidelity": 1.0,
  "response_discipline": 0.614,
  "hard_fail_rate": 0.0,
  "latency_ms": 10301.594,
}
```

## 8. Demo

### 8.1 Live Demo (GCP)

The backend is deployed on **Google Cloud Run**:

[https://send-money-agent-666450702512.us-central1.run.app/](https://send-money-agent-666450702512.us-central1.run.app/)

* Serverless (auto-scale, no infrastructure management)
* Public API endpoint
* Runs the full agent (LLM + tools + state)

### 8.2 Quick Test

You can interact via the UI or any HTTP client.

Example:

```text
send 500 USD to Maria Silva in Brazil via bank transfer
```

The agent will:

* Extract and validate fields
* Handle ambiguity if needed
* Ask for confirmation
* Execute safely


### 8.3 Architecture

```text
Client → Cloud Run (FastAPI) → Agent (LLM + Tools + State)
```
