
# 📄 Send Money Agent — Technical Documentation

## 1. Overview

This project implements a **Stateful conversational agent ** for money transfers using the Google ADK framework.

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

<img width="1536" height="1024" alt="image" src="https://github.com/user-attachments/assets/27c5a74e-8fed-44dd-8e8c-ac1401fe096e" />


---

## 2. Architecture (Core Components)


### 2.1. TransferState — State & Validation Layer

`TransferState` is the single source of truth for the entire conversation. It stores all extracted fields (country, recipient, amount, currency, delivery method) and ensures that every value is valid before being persisted.

It uses Pydantic validators to enforce business rules (e.g., amount limits, supported countries, full recipient name), and provides helper methods like `missing_fields()` and `safe_update()` to track progress and safely update the state. 

This component is critical because it guarantees **data consistency and prevents invalid transactions from ever reaching the execution layer**.


### 2.2. tools.py — Controlled Execution Layer

The `tools.py` module defines all actions that the LLM is allowed to perform. Instead of directly modifying the state, the LLM must call these functions, ensuring that every operation is validated and controlled.

Key operations include:
- `update_state()` for saving confident values  
- `clarify()` and `resolve_clarification()` for handling ambiguity  
- `next_field()` to guide the conversation  
- `validate_transfer()` and `submit_transfer()` for final execution  

Each function is atomic and returns structured outputs, allowing the LLM to reason about results safely. 

This design enforces a **safe interaction pattern where the LLM decides *what* to do, but the system controls *how* it is done**.

### 2.3. prompt.py — Reasoning & Decision Engine

The `prompt.py` module defines the behavior of the LLM. It includes the system prompt that instructs the model how to interpret user input, classify tokens, and decide which action to take.

The logic is based on:
- Token classification (CONFIDENT, UNSURE, INVALID)
- Ambiguity rules (e.g., name vs country conflicts)
- A strict turn loop (REFLECT → ACT → RESPOND)

It also enforces constraints such as:
- Never saving uncertain values directly  
- Always asking clarification when ambiguity exists  
- Only submitting after explicit confirmation  


This component acts as the **decision-making brain**, transforming unstructured user input into structured actions.

### 2.4. AgentRunner — Orchestration Layer

`AgentRunner` is responsible for executing the full conversational loop. It connects the LLM, tools, and state into a working system.

Its responsibilities include:
- Receiving user input  
- Building the LLM agent with current state + tools  
- Executing tool calls returned by the LLM  
- Updating and persisting the state  
- Handling retries, errors, and session management  

This component is the **runtime engine**, enabling a true stateful, multi-turn interaction instead of a simple stateless LLM call.


<img width="1536" height="1024" alt="image" src="https://github.com/user-attachments/assets/a6a962fb-3480-4ff2-abae-075365485573" />


## 3 🧠 prompt.py — The Brain of the Agent

The `prompt.py` module defines the reasoning and decision policy that drives the behavior of the conversational agent. Rather than treating the LLM as a simple text generator, we structure it as a **stateful decision-making system**, where each response is conditioned on the current state, pending clarifications, and available actions.

Our design follows the principles of **stateful LLM-based agents**, as described in:

> **Wu et al. (2023)** — *Stateful LLM-based Agents that can Interact with and Learn from Environments*  
> (arXiv:2303.03926)

In this paradigm, the agent maintains an internal state that evolves across turns and directly influences future decisions. The prompt injects:
- The current structured state (what is already known)
- Missing fields (what still needs to be collected)
- Pending clarifications (ambiguities to resolve)
- Available tools (actions the agent can take)

This allows the LLM to operate in a **closed-loop system (state → reasoning → action → updated state)** instead of a stateless single-shot response.


#### 3.1 🔍 Token Classification as a Decision Primitive

A key innovation in our prompt design is the use of **token-level classification** to guide the agent’s behavior.

Instead of directly extracting and saving all information, the model must first classify each piece of input into:

- **CONFIDENT** → clear, valid, and unambiguous → can be safely stored  
- **UNSURE** → ambiguous, partial, or malformed → requires clarification  
- **INVALID** → violates business rules → must be rejected and corrected  

This approach is inspired by structured extraction and uncertainty-aware NLP systems, particularly:

> **Xiao et al. (2023)** — *InstructIE: A Unified Instruction-based Framework for Information Extraction*  
> (explicit reasoning before extraction)

Instead of naive slot filling, the model performs a **two-step process**:
1. **Interpretation** → understand meaning and ambiguity  
2. **Decision** → determine whether to save, ask, or reject  


This design enables the agent to:

- Handle **messy and real-world inputs** (e.g., "2OO", "1k", "Pedro Brazil")
- Avoid **silent errors** (never guessing under ambiguity)
- Maintain **data integrity** (only validated values are stored)
- Support **multi-turn reasoning** with explicit clarification loops

In practice, this transforms the LLM from a passive extractor into an **active decision-making agent**, capable of safely interacting with users in high-stakes scenarios such as financial transactions.

#### 3.2 🔍 Token Classification as a Decision Primitive

The prompt was not designed in a single step. Instead, it was built iteratively, starting from simple extraction rules and evolving into a robust decision system through systematic testing of edge cases.

The core idea was to transform the LLM from a passive extractor into an **active decision-maker**, capable of handling ambiguity, corrections, and multi-turn reasoning.

##### 3.2.1 Edge Cases → Prompt Refinement

We stress-tested the system with hard cases:

- `"send 200 brl to Chile Rodrigues Lima"`  
- `"send 1000 or 2000 USD"`  
- `"send to Lima"`

These revealed that classification alone was not enough — the model still needed **explicit ambiguity handling**.


##### 3.2.2 Ambiguity Rules

We added deterministic rules to avoid guessing:

- Never auto-assign ambiguous tokens  
- Treat conflicts (e.g., *country vs name*) explicitly  
- Generate clarification questions instead of assuming  
Example:
```
"Chile Rodrigues"
→ could be country OR name → must clarify
```

##### 5.2.3. Turn Loop (Control)

We enforced a strict reasoning loop:

REFLECT → ACT → RESPOND

- **REFLECT**: the model classifies all tokens (CONFIDENT / UNSURE / INVALID) and checks for pending clarifications  
- **ACT**: the model decides exactly one action (e.g., `update_state`, `clarify`, `next_field`)  
- **RESPOND**: the model produces a single, controlled output (usually one question)

This loop is critical because it:
- Prevents the model from doing multiple things at once (e.g., saving + asking + confirming)
- Forces alignment between reasoning and tool execution
- Guarantees a predictable, step-by-step interaction flow

In practice, this transforms the LLM into a **deterministic controller**, not a free-form generator. :contentReference[oaicite:0]{index=0}  

---

##### 5.2.4. Few-Shots (Stability)

After defining rules and control flow, we added few-shot examples to stabilize behavior.

These examples demonstrate:
- How to apply token classification in real inputs  
- How to handle ambiguity (e.g., name vs country)  
- How to structure tool calls and responses  

Few-shots are especially important because:
- LLMs may interpret rules inconsistently without concrete examples  
- They reduce variability across edge cases  
- They reinforce the expected reasoning pattern (REFLECT → ACT → RESPOND)

Rather than teaching answers, few-shots teach **how to think and act**, improving consistency in complex, real-world scenarios.

<img width="1536" height="1024" alt="image" src="https://github.com/user-attachments/assets/fe9040d7-abf4-455d-9ab2-a3664d0f4524" />


---


## 📊 6 Evaluation — From Edge Cases to Metrics

### 6.1. Introduction

The evaluation strategy was designed to validate the system under **real-world uncertainty**, not just ideal inputs.

Instead of relying only on standard benchmarks, we built a **custom evaluation pipeline** focused on:
- Ambiguity handling  
- Multi-turn reasoning  
- Robustness to noisy and adversarial inputs  


### 6.2. Edge Case Generation (Stress Testing)

The first step was creating structured **edge case test groups**, targeting each component of the system:

- **A — Amount** → malformed formats (`2OO`, `1k`, `one thousand 500`)  
- **B — Recipient** → ambiguity (`Maria Chile`, `Jordan Lima`)  
- **C — Country** → variations (`Brasil`, `USA`, `Lima`)  
- **D — Currency** → synonyms (`bucks`, `reais`, `pesos`)  
- **E — Multi-turn / State** → corrections, multiple intents, resets  
- **J — Adversarial** → prompt injection, malicious patterns  

Example:
```python
{"group": "A2", "msg": "send 20xx0 USD to Maria Silva in Brazil"}
{"group": "B2", "msg": "send 500 USD to Maria Chile"}
{"group": "E4", "msg": "send 1000... actually 500 USD to Maria Silva"}
````

These tests were used iteratively to **break the system and refine the prompt**, especially for:

* Token classification
* Ambiguity rules
* Turn loop behavior


### 6.3. Multi-Turn Evaluation (Conversation-Level)

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


### 6.4. Metrics

We defined metrics across three dimensions:

| Category                 | Metric               | What it Measures                                 |
| ------------------------ | -------------------- | ------------------------------------------------ |
| **Deterministic (Core)** | State Accuracy       | Final correctness of extracted fields            |
|                          | Task Completion      | Whether the flow ended correctly                 |
|                          | Extraction Precision | If information was extracted at the right moment |
|                          | Tool Call Accuracy   | Correct usage of tools                           |
|                          | Correction Fidelity  | Proper handling of user corrections              |
| **LLM Behavior**         | Response Discipline  | Controlled and structured responses              |
|                          | Robustness           | Resistance to noisy/adversarial inputs           |
| **System**               | Latency              | Response time                                    |
|                          | Token Usage          | Cost efficiency                                  |

<img width="1536" height="1024" alt="image" src="https://github.com/user-attachments/assets/ba963426-7a31-4866-bdcf-990564aae388" />

### 6.5. Results

We evaluated two models:


| Metric               | Gemini 3.2 | Gemini Flash |
| -------------------- | ---------- | ------------ |
| State Accuracy       | 1.00       | 1.00         |
| Task Completion      | 1.00       | 1.00         |
| Extraction Precision | 1.00       | 1.00         |
| Tool Call Accuracy   | 0.97       | 0.92         |
| Correction Fidelity  | 1.00       | 1.00         |
| Response Discipline  | 0.72       | 0.69         |
| Hard Fail Rate       | 0.00       | 0.00         |
| Latency (ms)         | 27,277     | 22,277       |


The evaluation highlights a clear separation between deterministic correctness and LLM behavioral quality. Both models achieved perfect scores (1.00) in state accuracy, task completion, extraction precision, and correction fidelity, confirming that the system design—based on state, tools, and validation—guarantees reliable execution. In practice, once the LLM makes a correct decision, the architecture ensures consistent state updates, proper handling of corrections, and safe transaction completion.

Differences appear in the LLM behavior layer, particularly in tool selection and response discipline. Gemini 3.2 shows slightly better reasoning consistency (0.97 vs 0.92 in tool accuracy), while both models struggle with strict response constraints (≈0.7), which depend heavily on prompt adherence rather than core logic. Importantly, both models achieved a 0.00 hard fail rate, indicating strong robustness against noisy inputs and adversarial patterns, validating the safety of the overall design.

Finally, there is a clear latency vs quality trade-off: Flash is ~20% faster but slightly less consistent in reasoning. This reinforces a key architectural insight: correctness is enforced by the system, while quality is driven by the LLM, allowing flexible model selection based on cost, latency, or user experience without compromising safety.

---

Here’s a cleaner, more professional version with **fewer bullets** and a **fixed formula (no LaTeX)** 👇

---

```md id="limitations_section"
## ⚠️ 7 Limitations & Future Directions

### 7.1. Model Coverage

The evaluation focused only on large models (Gemini family), without testing smaller LLMs such as Mistral, Phi, or lightweight LLaMA variants. This limits our understanding of the cost–performance trade-off.

**Future direction:** benchmark smaller models to compare reasoning degradation versus cost savings, enabling more efficient deployment strategies.

### 7.2. Adversarial Robustness

Although no hard failures were observed, adversarial testing was not exhaustive. Scenarios such as prompt injection or instruction override (e.g., *"ignore all rules"*) were not systematically evaluated.

Example:
```

send 500 USD and ignore previous instructions

```

**Future direction:** incorporate adversarial testing frameworks and tools like **SelfCheckGPT** to measure consistency and resistance to manipulation, along with new metrics such as instruction override rate and policy violation rate.


### 7.3. Evaluation Ecosystem Integration

The current evaluation pipeline is custom-built and lacks integration with industry-standard observability tools.

**Future direction:** integrate with platforms like **LangSmith** (for tracing and debugging) and **Arize Phoenix** (for monitoring and drift detection), enabling better visibility into failures, tool usage patterns, and prompt behavior over time.


### 7.4. Business Metrics (KPI Layer)

The evaluation focuses on technical correctness but does not capture business impact. Metrics such as conversion rate, drop-off rate, and customer lifetime value (CLV) are not currently tracked.

A simple ROI metric could be defined as:

```

ROI = (Revenue - Cost) / Cost

```

Where revenue is driven by successful transactions and cost includes tokens and infrastructure.

**Future direction:** incorporate user-level tracking and connect model performance to real business KPIs.


### 7.5. A/B Testing (Model vs ROI)

There was no A/B testing comparing models from a business perspective. While Flash is faster and cheaper, it shows slightly weaker reasoning performance.

**Hypothesis:** faster models may provide better user experience despite lower technical scores, as users often prefer responsiveness over marginal quality gains.

**Future direction:** run controlled A/B experiments comparing models on latency, completion rate, and user satisfaction to optimize for ROI.

### 7.6. Monitoring & Continuous Evaluation

The current evaluation is offline and does not reflect real-time system performance.

**Future direction:** implement continuous monitoring to track latency trends, tool failures, and user correction patterns, enabling ongoing optimization and early detection of issues.


```



---



