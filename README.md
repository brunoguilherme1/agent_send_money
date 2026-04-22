
# 📄 Send Money Agent — Technical Documentation

## 1. Overview

This project implements a **Stateful conversational agent [1]** for money transfers using the Google ADK framework.

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

The system ensures **robust extraction under uncertainty**, following real-world conversational patterns described in the assignment .

---

## 2. Architecture

### Core Components

| Component       | Responsibility                                        |
| --------------- | ----------------------------------------------------- |
| `TransferState` | State management + validation                         |
| `tools.py`      | Atomic operations (update, clarify, validate, submit) |
| `prompt.py`     | Reasoning + decision policy                           |
| `AgentRunner`   | Orchestration + execution loop                        |

### Flow

```text
User Input
   ↓
LLM (Prompt + Tools)
   ↓
Tool Calls (update / clarify / next_field)
   ↓
State Update
   ↓
Next Question / Confirmation
```

---

## 3. State Management

The system uses a **strongly validated state object**:

```python
class TransferState(BaseModel):
```

Key properties:

* Strict validation (country, amount, currency, etc.)
* Missing field tracking
* Clarification queue

Example:

```python
def missing_fields(self) -> List[str]:
```

This enables:

* Deterministic control flow
* Safe updates (`safe_update`)
* Clear progression to confirmation

📌 This is a classic **slot-filling architecture**, extended with:

* validation
* correction handling
* ambiguity resolution

---

## 4. Core Techniques Used

This system is NOT just a chatbot — it combines multiple **NLP + LLM reasoning techniques**.

---

### 4.1 Slot Filling (Structured Extraction)

**Idea:** Extract structured fields from free text.

Used via:

```python
update_state(field, value)
```

---

### 4.2 Clarification Queue (Uncertainty Handling)

Instead of guessing, the system explicitly models uncertainty:

```python
clarify(items=[...])
```

Key design:

* Multiple ambiguities handled sequentially
* Never overwrite uncertain values
* Always ask 1 question per turn

---

### 4.3 Self-Ask Reasoning (Core LLM Strategy)

📌 Based on:

Self-Ask With Search

**Concept:**
Break reasoning into intermediate questions.

In your system:

```text
STEP 0 — Pending clarifications?
STEP 1 — REFLECT
STEP 2 — ACT
```

This is essentially **Self-Ask applied to structured extraction**:

| Self-Ask Step      | Your Agent              |
| ------------------ | ----------------------- |
| Ask sub-question   | clarify()               |
| Answer it          | resolve_clarification() |
| Continue reasoning | next_field()            |

💡 Example:

User:

> "Send 100 USD to Maria Ecuador"

Agent reasoning:

1. Is "Maria Ecuador" a name?
2. Is "Ecuador" the country?

→ Ask sequentially instead of guessing.

---

### 4.4 Confidence-Based Extraction

📌 Inspired by:

Calibrating Model Confidence for Reliable AI Systems

Your system explicitly defines:

```text
CONFIDENT → update_state()
UNSURE → clarify()
INVALID → reject
```

This is a **practical confidence calibration layer**, even without probabilities.

| Level           | Action |
| --------------- | ------ |
| High confidence | Save   |
| Medium          | Ask    |
| Low / invalid   | Reject |

💡 This avoids:

* hallucinations
* silent errors
* wrong assumptions

---

### 4.5 Rule-Based Disambiguation Layer

You implemented **deterministic rules on top of LLM reasoning**:

Example:

```text
Rule 1 — Country vs surname ambiguity
```

This is critical in production systems:

* LLM = flexible understanding
* Rules = safety constraints

---

### 4.6 Incremental State Update (Streaming Understanding)

The agent supports:

* partial inputs
* corrections
* late information

Example:

```text
"Send 200 USD"
→ later: "to Maria"
→ later: "in Brazil"
```

This is similar to:

📌 **Incremental parsing systems** in NLP

---

### 4.7 Tool-Augmented LLM (Agent Pattern)

📌 Based on:

ReAct: Synergizing Reasoning and Acting

Your system follows:

```text
THINK → ACT → OBSERVE
```

Example:

```text
REFLECT → ACT → Tool result → Next step
```

Tools:

* `update_state`
* `clarify`
* `resolve_clarification`
* `next_field`

This is a **controlled agent loop**, not free-form generation.

---

## 5. Ambiguity Handling (Key Innovation)

The system explicitly models **real-world ambiguity cases**:

### Example: Country vs Name

```text
"Maria Ecuador"
```

Handled as:

```python
clarify([
  {field:"recipient_name", ...},
  {field:"country", ...}
])
```

---

### Example: Malformed Amount

```text
"2OO"
```

Handled as:

```text
Did you mean 200?
```

---

### Example: Multiple Transfers

```text
"send 200 to Marcos and 300 to Maria"
```

→ system refuses and clarifies

---

## 6. Validation Layer

All values pass through strict validators:

```python
@field_validator("amount")
```

Ensures:

* amount > 0
* amount ≤ 10,000
* valid currency
* valid country

---

## 7. Conversation Control

The system enforces:

* **One question per turn**
* No hidden reasoning exposed
* Deterministic flow

From prompt:

```text
- One question per turn. Always.
- 1–2 sentences.
```

---

## 8. Agent Execution Loop

From `AgentRunner` :

### Key features:

* Retry logic (503 / 429)
* Loop breaker for tool misuse
* Session persistence
* Tool tracing

---

## 9. Strengths of This Design

### ✅ Production-ready characteristics

* Deterministic + LLM hybrid
* Explicit uncertainty handling
* Safe updates (no silent overwrites)
* Robust to messy inputs
* Modular tools

---

Got it — here is exactly what you need: **clean `.md`, interview-ready, focused, didactic, and structured like a story**.

---

# 📄 Evaluation Strategy — Send Money Agent

## 🎯 How we evaluate the agent

To evaluate the agent, we use the following metrics:

---

## 📊 Metrics Used

| Category                 | Metric               | What it Measures                                 |
| ------------------------ | -------------------- | ------------------------------------------------ |
| **Deterministic (Core)** | State Accuracy       | Final correctness of extracted fields            |
|                          | Task Completion      | Whether the flow ended correctly                 |
|                          | Extraction Precision | If information was extracted at the right moment |
|                          | Tool Call Accuracy   | Correct usage of tools (update, clarify, etc.)   |
|                          | Correction Fidelity  | Proper handling of user corrections              |
| **LLM Behavior**         | Response Discipline  | Quality and control of responses                 |
|                          | Robustness           | Resistance to noisy/adversarial inputs           |
| **System**               | Latency              | Response time                                    |
|                          | Token Usage          | Cost efficiency                                  |

---

## 🧠 Why we chose these metrics

We chose these metrics because they reflect **real-world requirements of an agent system**, not just NLP quality.

### 1. Deterministic metrics → Business safety

Metrics like:

* State Accuracy
* Task Completion
* Correction Fidelity

are critical because this is a **transactional system**.

👉 In this context:

```text
A small mistake = a financial error
```

So we need **strict, binary guarantees**, not probabilistic ones.

---

### 2. Temporal + behavioral metrics → UX quality

Metrics like:

* Extraction Precision
* Tool Call Accuracy

capture something more subtle:

```text
“How efficiently and correctly the agent understands and acts”
```

👉 Example:

* Extracting "USD" late = bad UX
* Asking unnecessary questions = friction

These metrics ensure the agent behaves like a **smart assistant, not a form**

---

### 3. LLM-as-Judge metrics → Conversational control

Metrics like:

* Response Discipline
* Robustness

are evaluated using an LLM-as-judge approach (similar to AgentBench).

👉 Why?

Because some properties cannot be measured deterministically:

* Is the response concise?
* Did it follow the “one question” rule?
* Did it leak internal reasoning?

These require **semantic evaluation**, not rules.

---

### 4. Inspired by modern evaluation frameworks

This evaluation design is inspired by:

* AgentBench → evaluating agents across reasoning + action
* On Calibration of Modern Neural Networks → importance of controlling overconfident generation

👉 Key idea:

```text
We separate “correctness” from “behavior”
```

---

## 🚀 How we evaluated the agent

We built a **multi-turn test suite** covering:

* ambiguity cases
* corrections
* missing information
* control flows (cancel, restart)

Then we:

1. Ran the agent across all test cases
2. Logged full traces (state + tool calls) 
3. Computed metrics using a two-layer evaluator 

---

## 📊 Results

### 🌍 Global Metrics

| Metric                   | Value      |
| ------------------------ | ---------- |
| **State Accuracy**       | **1.00**   |
| **Task Completion**      | **1.00**   |
| **Extraction Precision** | **1.00**   |
| **Tool Call Accuracy**   | **0.97**   |
| **Correction Fidelity**  | **1.00**   |
| **Response Discipline**  | **0.69**   |
| **Hard Fail Rate**       | **0.00**   |
| **Latency (ms)**         | **22,277** |

---

### 🧪 Key Observations

#### ✅ Strengths

* **Perfect correctness (1.0 across all core metrics)**
* No hard failures → system is **production-safe**
* Strong handling of:

  * ambiguity
  * corrections
  * multi-turn flows

---

#### ⚠️ Weakness

* **Response Discipline = 0.69**

👉 This means:

* Sometimes asks more than one question
* Slight verbosity
* Minor deviations from prompt rules

---

## 🧠 Final Insight (What this shows)

This evaluation proves that:

```text
The agent is structurally correct and robust,
but still behaves like a typical LLM in generation.
```

👉 In other words:

* ✅ Logic layer = strong (deterministic + tools)
* ⚠️ Language layer = needs refinement

---

## 🏁 Final Takeaway (Interview-ready)

> We designed the evaluation to separate **hard correctness (must be perfect)** from **LLM behavior (can be optimized)**.
>
> This allows us to ensure the system is **safe for production**, while still improving the conversational quality over time.

---

## 11. References

* Self-Ask With Search
* ReAct: Synergizing Reasoning and Acting
* Calibrating Model Confidence for Reliable AI Systems

---

If you want next step, I can:

👉 turn this into **interview-ready explanation (5 min pitch)**
👉 or map each part to **AgentBench / RAGAS evaluation metrics**
👉 or generate a **diagram (system design style)**
