Here’s a **clean, production-style `.md` documentation** for your agent, grounded in your codebase and explicitly connecting to **practical LLM techniques**, including **Self-Ask** and **Confidence-based reasoning** (with proper citations).

---

# 📄 Send Money Agent — Technical Documentation

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

### ✅ Compared to naive LLM

| Naive LLM            | Your System        |
| -------------------- | ------------------ |
| Guesses missing info | Asks clarification |
| Stateless            | Stateful           |
| Hallucinates         | Validates          |
| Single-shot          | Multi-turn         |

---

## 10. Key Takeaways

This system combines:

1. **Slot Filling**
2. **Self-Ask reasoning**
3. **Confidence-based decisions**
4. **Tool-augmented LLM (ReAct)**
5. **Rule-based safety layer**

👉 This is exactly how **real-world LLM agents are built in production**.

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
