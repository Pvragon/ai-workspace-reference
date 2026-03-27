---
template: framework-reference
version: 1.0.1
summary: "Nick Saraev's DOE (Directive-Orchestration-Execution) framework for reliable AI agent systems: 3-layer architecture, self-annealing, error compounding math, and implementation patterns. Load for DOE theory and design rationale."
created: 2026-02-18
last_updated: 2026-02-18
maintainer: pvragon
tags:
  - agentic-workflows
  - ai-architecture
  - automation
  - framework
sources:
  - title: "the n8n killer? AGENTIC WORKFLOWS: Full Beginner's Guide"
    url: https://www.youtube.com/watch?v=bA-WmidVSGo
    type: youtube
    date: 2025-11-25
  - title: "DON'T build AI automations, build agentic workflows! (Google Antigravity)"
    url: https://www.youtube.com/watch?v=MxyRjL7NG18
    type: youtube
    date: 2026-01-08
  - title: "Agents vs Workflows - Pick the Right Tool or Pay the Price"
    url: https://www.youtube.com/watch?v=5rNu19PfgFg
    type: youtube
  - title: "Nick Saraev's DOE Framework for AI Agentic Systems (Bob Mwathu)"
    url: https://www.linkedin.com/posts/bob-mwathu_theres-a-new-way-to-build-ai-agentic-systems-activity-7413147110675750912-cRU4
    type: linkedin
  - title: "Agentic AI Workflows for Business (Course)"
    url: https://completeaitraining.com/course/agentic-ai-workflows-for-business-build-deploy-scale-video-course/
    type: course
  - title: "Automation -> Agentic Transition Folder"
    url: https://nick-saraev.kit.com/aaa09595c6
    type: resource-download
---

# Nick Saraev's DOE Framework

DOE (Directive, Orchestration, Execution) is a 3-layer architecture for building reliable AI agent systems. It separates concerns so that LLMs handle decision-making while deterministic code handles execution, solving the fundamental mismatch between probabilistic AI and deterministic business requirements.

## Who Is Nick Saraev

Canadian entrepreneur (b. 1996, Vancouver). Background in psychology and neuroscience research before pivoting to entrepreneurship. Key ventures:

- **LeftClick** - AI consulting firm for B2B companies (current, CEO)
- **Maker School** - No-code/automation community on Skool; 1,900+ members, ~$300K/month profit; 5,000+ students trained
- **1SecondCopy** - AI content writing marketplace, scaled to ~$100K/month
- Scaled two agencies to $160K+ combined revenue

Featured in Popular Mechanics, Apple News, Bloomberg. His early automation business was built on the arbitrage of knowing technical things (APIs, webhooks, JSON) that most business owners didn't. He now teaches the DOE framework as the evolution beyond that model.

## The Core Problem DOE Solves

### Probabilistic vs. Deterministic

AI models are inherently probabilistic — they predict what comes next, producing varied outputs. Business logic demands deterministic results: the exact same output format, every time, reliably. DOE bridges this gap by limiting AI to the role it's best at (reasoning, routing, decision-making) and delegating actual work to deterministic code.

### Error Compounding

If each step in a workflow has a 90% success rate, a five-step task compounds to:

```
0.9^5 = 0.59 (59% overall success rate)
```

This is unacceptable for revenue-critical operations. Saraev's framing: "You cannot run a million dollar a month operation on a system that only works most of the time." And: "In business, even a 1% rate of inaccuracy can lead to a revenue reduction of 50% or more."

DOE mitigates this by minimizing the number of probabilistic decision points. The agent handles routing and conditional branching; everything else is deterministic code.

### Why Traditional No-Code Falls Short

Tools like n8n, Make.com, and Zapier put the human in the orchestrator role — you manually configure every node, map every route, and maintain the whole workflow yourself. This doesn't scale, requires constant maintenance, and fails to leverage AI's core capability (reasoning). DOE replaces the human orchestrator with an AI one.

## The Three Layers

### Layer 1: Directive — "The What"

High-level instructions written in natural language Markdown. No executable code lives here. Stored in a `/directives` folder.

**Analogy**: Like a recipe — specifies ingredients and general steps without constraining exact methodology.

**What a directive contains**:

- The goal/objective of the task
- Inputs the agent will receive
- Process steps (sequence and logic)
- Which tools/scripts to use
- Edge cases and how to handle them
- Definition of Done (explicit success criteria)
- Guardrails (what the agent must NOT do)

**Key properties**:

- Human-readable and version-controllable
- Can be updated by the agent during self-annealing
- Non-technical stakeholders can contribute
- Living documents that improve over time

### Layer 2: Orchestration — "The Who / When"

The AI agent itself. This is not a file in the folder structure — it is the ambient intelligence processing directives and invoking execution scripts. The LLM is the orchestration layer.

**What the orchestrator does** (the reasoning loop):

1. **Read** — Process the relevant directive
2. **Choose** — Select the appropriate action or execution script
3. **Execute** — Invoke the selected tool/script
4. **Evaluate** — Assess the result; decide whether to loop, escalate, or complete

This is also described as the **PTMRO Loop**: Planning, Tools, Memory, Reflection, Orchestration — "the agent's operational heartbeat."

**Key distinction**: "Unlike n8n or Make, you're no longer the orchestrator. The agent handles routing and decision-making autonomously."

**Organizational analogy**: A mid-level manager — receives strategy from directives, interprets it, deploys available tools (execution layer), and reports back.

**Memory management**: The orchestrator decides when to use sub-agents to prevent context pollution, when to compress via summaries, and when to rely on long-term memory.

### Layer 3: Execution — "The How"

Deterministic Python scripts that actually perform the work. Given the same inputs, they always produce the same outputs. Stored in an `/execution` (or `/executions`) folder.

**Why Python over LLM-only**:

- "A Python script does not hallucinate. It either works or errors out."
- Binary nature (works/fails) provides reliability guarantees
- Speed: Python performs operations "10,000 times, if not 100,000 times faster" than token-based LLM computation
- Eliminates token consumption for deterministic operations

**Script conventions**:

- **Single responsibility** — Each script handles one discrete task
- **Standard I/O** — Structured inputs, consistent output formats
- **Error handling** — Built-in exception catching with meaningful messages the agent can interpret
- **Logging** — Verbose, so agents understand execution flow and failure points
- **API encapsulation** — All API calls, rate limiting, and auth live in execution scripts

**The Minecraft/Spear analogy**: Agents generate temporary scripts for tasks. The ones that work get retained and progressively improved — like a primitive spear refined through use into a better tool. You start with wooden tools, improve them, and build up capability over time.

## Folder Structure

```
workspace/
├── directives/
│   ├── SOP1.md
│   ├── SOP2.md
│   └── [workflow instruction files]
├── execution/
│   ├── scrape_leads.py
│   ├── enrich_leads.py
│   ├── format_output.py
│   └── [deterministic scripts]
├── logs/
├── agents.md          # System prompt / framework config
└── .env               # Environment variables
```

There is deliberately no `/orchestration` folder because the orchestrator is the LLM itself, not a file.

## System Prompt File (agents.md)

The initial configuration file injected at conversation start. Named `agents.md`, `claude.md`, or `gemini.md` depending on the model/IDE.

**Contains**:

- DOE framework explanation and conventions
- Self-annealing philosophy and permissions
- Folder structure context
- Behavioral expectations and constraints
- Links to the directives folder

**The ship-steering metaphor**: "If I give myself even a slight range of possible outcomes, I might greatly overshoot." Tight initial guardrails are essential — the system prompt constrains the agent's initial trajectory, preventing significant deviations from the DOE pattern.

Saraev provides a starter version for free at [nick-saraev.kit.com/aaa09595c6](https://nick-saraev.kit.com/aaa09595c6).

## Self-Annealing

Borrowed from metallurgy (heating and cooling metal to remove stress and strengthen it). This is DOE's anti-fragility mechanism.

### The Loop

When an error occurs anywhere in the workflow:

1. **Catch** — The agent captures the error rather than crashing
2. **Read** — Processes the error message and stack trace
3. **Diagnose** — Identifies root cause
4. **Fix** — Updates the execution script to handle the edge case
5. **Rewrite** — Updates the corresponding directive to warn future instances
6. **Retry** — Re-executes with the corrected logic

### Why It Matters

"These systems are anti-fragile — they benefit from shocks rather than breaking under them." Each failure mode encountered and corrected makes the system more robust. Unlike traditional automation that requires constant human maintenance, DOE systems improve through use.

**Practical example**: When an API rate limit is hit, the agent updates the execution script to include retry logic with exponential backoff, and modifies the directive to note the rate limit so future runs plan around it.

## Advanced Concepts

### DOE Library (Reusable Script Collection)

Rather than writing bespoke scripts for each client/project, build a reusable library of atomic execution scripts: scraping tools, formatting tools, CRM integrations, email tools. Each new workflow reuses the library, cutting build times dramatically.

"Atomic" means each script does exactly one thing, takes defined inputs, and produces defined outputs. The same scraping tool used in sales prospecting also appears in market research and competitive analysis workflows.

### Horizontal Leverage

Rather than automating 100% of one role (hard and often not worth pursuing), automate 80-90% of tasks across many roles. "Cumulative time recovery across teams dwarfs the savings from replacing one role."

### Sub-Agents and Context Pollution

When a single agent's context window fills with unrelated information, its performance degrades. This is "context pollution."

Solutions:

- **Sub-agents** — Specialized instances spun up for isolated sub-tasks (research, code review, documentation) with clean, scoped context
- **Compression** — Summarizing completed work rather than keeping raw output
- **Long-term memory** — Offloading reference documents from active context

### Performance Optimization

Once scripts are built, agents can iterate to improve efficiency:

- Replace one-off endpoints with batch endpoints
- Reduce algorithmic complexity (O(N^2) to O(N))
- Economize token usage by delegating more work to Python
- Parallelize independent tasks

### Deployment Strategy

Execution scripts deploy to cloud via webhooks and scheduled triggers. The orchestration layer stays local during development for human oversight and rapid iteration. As workflows stabilize, they move to fully automated cloud execution.

## The CLEAR Framework (Effective AI Communication)

Saraev's framework for writing effective prompts and directives:

| Letter | Component | Description |
| :--- | :--- | :--- |
| **C** | Clarity | Precise problem definition with measurable outcomes |
| **L** | Logic | Structured thinking AI can follow |
| **E** | Examples | Specific scenarios and edge cases |
| **A** | Adaptation | Iterative refinement based on feedback |
| **R** | Results | Validation that output matches business needs |

## Broader Philosophy

### On Skills in the AI Era

"The people making the most money in 2026 probably won't be the best at automation tools. They'll be the best at identifying business problems, translating those problems into prompts, and then orchestrating AI to solve them."

Technical automation skills are increasingly commoditized. The scarce skill is identifying high-value problems worth solving and orchestrating AI systems to solve them — the strategic layer, not the implementation layer.

### On the AI Overhang

There is currently a gap between what AI can do and how most people/businesses are using it. This gap represents an arbitrage opportunity. DOE is the architecture for accessing that overhang — making AI systems reliable enough for real business operations.

### Core Insight

"AI is the decision maker, but reliable code does the actual work."

## Relationship to Pvragon's Architecture

The Pvragon workspace (AGENTS.md) implements a DOE-aligned architecture:

| DOE Layer | Pvragon Equivalent | Location |
| :--- | :--- | :--- |
| Directive | Directives (SOPs in Markdown) | `directives/` |
| Orchestration | The AI agent (Layer 2) | The LLM itself |
| Execution | Deterministic Python scripts | `executions/` |

Additional Pvragon enhancements beyond base DOE:

- **Context system** (`context/`) for indexed and global knowledge
- **Skills** (`skills/`) for reusable procedures
- **Runtime structure** (`runtime/`) for deliverables and intermediates
- **Artifact Mirroring Rule** for anti-data-loss in ephemeral environments
- **File Metadata Standards** (YAML frontmatter) for version tracking
