# Curriculum audit

This document records how the curriculum graph was derived, which topics were added beyond the initial brief, the
coverage of each domain today, and what is deliberately deferred. The coverage numbers below were recalculated directly from the current YAML files. The project coverage command could not run because the supplied dependency tree contains a Windows-only esbuild binary; all figures below were independently counted from the structured content.

## Method

1. **Start from the learning outcome**, not the topic list: an absolute beginner should become an engineer who can
   build, test, deploy, secure and evaluate Python, data, ML, GenAI, RAG and agent systems.
2. **Audit 15 prerequisite layers** for every domain: computer literacy and OS; programming and computational
   thinking; data structures and algorithms; CS fundamentals; software practice; maths and statistics; data
   management and engineering; networking and distributed systems; backend and architecture; ML and DL; AI
   frameworks and model integration; infrastructure and operations; security, privacy and governance; testing,
   evaluation, debugging and reliability; communication and interviews.
3. **Recurse on every concept** with the same questions: what must a beginner know first? what maths or programming
   does it need? what adjacent tools are needed to use it? what security, testing or deployment knowledge? what is
   commonly misunderstood? what is needed to debug it, to run it in production, to explain it in an interview?
   Each "yes" became either an existing node or a new concept with a `requires` edge.
4. **Encode everything as data** (`content/stages/*.yaml`): 21 stages, modules, concepts with level, priority,
   prerequisites, key ideas, misconceptions, tools, interview and production notes and official sources. The build
   rejects cycles, unknown references and broken links.
5. **Verify sources**: concept and lesson sources are official documentation, specifications, standards, original
   papers or well-known free books. `npm run check:links` checks that each URL resolves and records the date
   (`content/link-report.json`); the UI shows that status next to each source. A resolving link is not proof that
   the page still supports the claim — prose carries its own `reviewedOn` date.

## Topics added beyond the initial brief

The brief's lists were treated as a starting point. The audit added these concepts because a learner cannot reach
the goal reliably without them:

| Layer | Added concepts (ids abbreviated) | Why |
|---|---|---|
| Computer literacy | binary-and-data, text-encoding, reading-docs, troubleshooting, learning-to-learn | Encoding bugs, unread error messages and poor study habits block beginners more than syntax does. |
| Python | pattern-matching, slicing, copying, scope, higher-order-functions, closures, data-model, regex, pathlib, csv-json, cli-apps, configuration, mocking, secure-coding, memory-model | Needed for idiomatic code, debugging aliasing bugs, real file/data work and safe programs. |
| CS | two-pointers/sliding-window, greedy, dynamic-programming, shortest-paths, bit-manipulation, dynamic-arrays, concurrency-fundamentals, dependency-management | Interview patterns and the mechanics behind list/dict performance and race conditions. |
| Tooling | git-undo, git-internals, gitignore-hygiene, branching-strategies, shell-pipes, ssh, package-managers | Recovering from mistakes and keeping secrets out of history are day-one professional skills. |
| Networking | network-layers, sockets, urls, cookies-sessions, cors, web-browser, http-clients, api-styles (GraphQL/gRPC/WebSockets/SSE), debugging-network | LLM APIs stream over SSE; CORS and TLS failures are common blockers; timeouts and retries need understanding. |
| Backend | web-frameworks (what they do), error-handling (RFC 9457), async-endpoints, rate-limiting, event-driven, caching-strategies, secrets-management | Production APIs fail at these seams, not at routing. |
| Databases | sql-advanced (CTEs, window functions), sqlite-python (SQL injection), connection-pooling, backup-replication, nosql-overview | Safe parameterised queries and transaction semantics are prerequisites for every data system. |
| Maths | summation-notation, information-theory (cross-entropy), numerical-computing, linear-transformations, eigen-svd | Cross-entropy is the loss of every classifier and LLM; numerical stability explains softmax tricks. |
| Data | notebooks, data-quality, time-series | Reproducibility pitfalls and time-ordered splits cause silent leakage. |
| Data engineering | idempotency-incremental, schema-evolution, dbt, pipeline-quality, lineage-governance, cloud-data-platforms | Re-runnable, observable pipelines are what make data trustworthy. |
| ML | imbalanced-data, reproducibility, fairness, interpretability, reinforcement-learning (basics) | Required to evaluate honestly and to understand RLHF at a conceptual level. |
| Deep learning | tokenization, positional-encoding, gpu-fundamentals, inference-performance | Explain context windows, cost, latency and quantisation of LLMs. |
| GenAI | hallucinations, model-licensing (open weights vs open source), local-inference, guardrails, cost-latency, llm-architecture | Dependable LLM software is mostly about limits, licences and budgets. |
| RAG | keyword-search before vectors, metadata-filtering, access-control, failure-analysis, performance, observability | Most RAG failures are retrieval or permission failures. |
| Frameworks | why-frameworks, tradeoffs, other-sdks | Use frameworks deliberately — or not at all. |
| Agents | workflows-vs-agents, tool-design, permissions-sandboxing, failure-recovery, security, observability, other-frameworks | Agents multiply risk; deterministic workflows are often the better design. |
| Graphs | relational-vs-graph, graph-modeling, kg-construction, graph-algorithms, GQL standard | GraphRAG depends on construction quality and modelling decisions. |
| Production | environment-config, release-strategies, incident-response, reliability-engineering, infrastructure-as-code, cost-estimation, production-evaluation | Operating systems is a discipline of its own. |
| **New stage** | Security, Privacy and Responsible AI (11 concepts) | Cross-cutting prerequisite for TLS, authentication, prompt injection, agent security and governance. |
| **New stage** | System Design, Distributed Systems and Cloud (9 concepts) | Senior-level design, consistency, cloud fundamentals and end-to-end AI system design. |

## Cross-domain prerequisite chains (examples)

* **RAG retrieval** ← vector similarity ← embeddings ← vectors and dot products ← functions and lists. Keyword search
  (BM25) needs only dictionaries and summation notation, so it is taught first.
* **HTTPS / authentication** ← TLS ← cryptography basics (security stage) ← binary data; authentication also needs
  cookies/sessions and FastAPI.
* **Prompt injection** ← tool calling ← structured outputs ← Pydantic validation; and ← threat modelling.
* **LLMOps** ← LLM evaluation (← ML evaluation metrics) + observability (← structured logging ← Python logging) + CI/CD
  (← pull requests ← Git).
* **Agent security** ← permissions and sandboxing ← tool design ← API design ← REST ← HTTP semantics.
* **GraphRAG** ← knowledge-graph construction (← LLM structured outputs) + graph algorithms + RAG context assembly.

## Coverage matrix

<!-- coverage:start -->
| # | Domain | Concepts | Essential | Full lessons | Lesson coverage | Assessment items | Sources (checked OK) |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | Foundations | 16 | 12 | 13 | 81% | 90 | 16 (16) |
| 2 | Python | 61 | 42 | 48 | 79% | 571 | 72 (64) |
| 3 | CS & Engineering | 34 | 20 | 22 | 65% | 162 | 68 (68) |
| 4 | Git & Linux | 21 | 14 | 14 | 67% | 63 | 54 (54) |
| 5 | Networking & HTTP | 20 | 14 | 14 | 70% | 66 | 54 (54) |
| 6 | Backend | 18 | 14 | 14 | 78% | 66 | 53 (53) |
| 7 | Databases | 19 | 13 | 13 | 68% | 81 | 54 (54) |
| 8 | Maths & Stats | 19 | 14 | 14 | 74% | 83 | 53 (53) |
| 9 | Data Analysis | 11 | 8 | 8 | 73% | 32 | 33 (33) |
| 10 | Data Engineering | 17 | 9 | 9 | 53% | 36 | 46 (46) |
| 11 | Machine Learning | 25 | 16 | 16 | 64% | 101 | 56 (56) |
| 12 | Deep Learning | 20 | 13 | 13 | 65% | 69 | 55 (55) |
| 13 | GenAI & LLMs | 19 | 14 | 14 | 74% | 94 | 53 (53) |
| 14 | RAG | 19 | 14 | 14 | 74% | 75 | 46 (46) |
| 15 | LLM Frameworks | 12 | 2 | 2 | 17% | 8 | 28 (28) |
| 16 | Agentic AI | 21 | 11 | 11 | 52% | 66 | 55 (55) |
| 17 | Graphs & Knowledge | 11 | 5 | 5 | 45% | 20 | 26 (26) |
| 18 | MLOps & Production | 23 | 15 | 15 | 65% | 60 | 63 (63) |
| 19 | Security & Responsible AI | 11 | 10 | 10 | 91% | 63 | 32 (32) |
| 20 | System Design | 9 | 6 | 6 | 67% | 24 | 26 (26) |
| 21 | Interviews | 8 | 5 | 5 | 62% | 20 | 18 (18) |
| | **Total** | **414** | **271** | **280** | **67.6%** | **1850** | **961 (953)** |
<!-- coverage:end -->

## Priority classification

Every concept carries one of: *essential foundation*, *supporting knowledge*, *advanced specialisation*, *optional
enrichment*, *technology-specific implementation*. Recommendations walk essential concepts in prerequisite order;
optional and technology-specific concepts appear in paths only when a target needs them (e.g. Databricks for the
Data Engineer path, CrewAI/AutoGen only as optional nodes).

## Latest implementation update — 4 November 2026

The current inventory is **280 full lessons / 414 concepts (67.6%)**. The essential curriculum has **271/271 full lessons**, leaving **0 essential concepts**. All 271 essential concepts across all 21 stages now have full lessons.

This implementation sequence expanded the curriculum from 114 to 280 full lessons, adding 166 lessons across foundations, engineering, data, ML, GenAI, RAG, agents, graph systems, MLOps, security, system design and interviews. Each new lesson includes structured objectives, explanations grounded in its concept metadata and sources, a runnable Python teaching example, misconception guidance, recognition and transfer assessments, a coding exercise with tests, and a mastery check. The original SQL joins lesson was restored and preserved.

The current structured inventory contains 1,916 lesson sections, 1,850 assessment items, 1,258 code blocks (1,153 marked runnable), 507 glossary terms, 212 interview questions, 28 projects and 10 learning paths.

## Deferred work and why

| Deferred | Depends on | Priority |
|---|---|---|
| Full lessons for remaining 134 concepts (currently outline pages with key ideas, misconceptions and sources) | The lesson engine (done); authoring time | All essential concepts across the curriculum now have full lessons; the remaining 134 concepts are supporting, advanced, optional or technology-specific. Expand them by learning-path value and prerequisite order. See [ROADMAP.md](ROADMAP.md). |
| In-browser execution of numpy/pandas lessons (verified) | Pyodide packages are fetched from a CDN, which breaks offline verification | Medium — teach with pure Python now; add optional package-backed lessons later with a local package mirror. |
| Graph database lessons with live Cypher | No embedded property-graph database runs in the browser today | Medium — model graphs in Python; Neo4j via Docker in a local project. |
| Optional local-AI assistance (explanations, rubric feedback) | Optional Ollama integration and consent UI | Low — core learning must never depend on it. |
| Spaced review for outline-only concepts | Assessment items for those concepts | Follows expansion of supporting and advanced lessons. |
| Multi-device sync | Would need a server or file-sync convention | Low — export/import covers it. |

## Graph change log and open suggestions

* 2026-10-22 — initial graph: 21 stages, 85 modules, 414 concepts; 10 goal-based paths generated from targets.
* Open suggestions from the stage enrichment review are listed below and applied once checked.

<!-- suggestions:start -->
**Applied after review (2026-10-22, second audit pass by domain reviewers):**

* New concepts (14): `cs.backtracking`, `cs.union-find` (optional), `cs.tries` (optional), `tooling.ci-basics`,
  `tooling.git-tags-releases` (optional), `networking.http-versions`, `networking.firewalls` (optional),
  `backend.streaming-responses`, `math.maximum-likelihood`, `de.change-data-capture`, `ml.time-series-forecasting`,
  `ml.anomaly-detection` (optional), `dl.distributed-training`, `genai.data-privacy`.
* New prerequisite edges: heaps and hashing → dynamic arrays; graphs → recursion; two-pointers → sorting; git undo →
  branching; shell scripting → permissions and processes; pull requests → merge conflicts; package managers →
  permissions; HTTP clients → HTTP semantics; network debugging → DNS and TLS; browsers → DNS; CORS → browsers;
  proxies → TLS; ORM → joins; EDA → visualisation; feature engineering → EDA; streaming systems → distributed-systems
  basics; SVM → overfitting; Kubernetes → load balancers; OWASP Top 10 → authorisation; LLM security → input handling;
  AI system design → LLM security; coding interviews → heaps and dynamic programming; GenAI interviews → LLMOps.
* Corrected edge: dimensionality reduction now requires learning types + eigen/SVD (not clustering).
* New relation: `dl.tokenization` extends `genai.tokens-context` (beginner vs in-depth treatment of one topic).

**Considered and not applied (with reasons):**

* *Moving cryptography basics and cloud fundamentals earlier.* Stages are groupings; order comes from the graph, so
  `networking.tls` already pulls `security.cryptography-basics` (and its prerequisites) forward in every path. The UI
  shows cross-stage prerequisites explicitly. Recorded as a known "stage order inversion".
* *`data.data-loading` → `databases.sql-basics`.* Loading CSV/JSON should not wait for SQL; `read_sql` is one optional
  part of the concept.
* *`security.secrets-handling` dropping cryptography basics.* Kept: rotation, vault encryption and why hashing is not
  a way to store API keys rely on it.
* *Level inversion* `mlops.cost-estimation` (intermediate) → `mlops.performance-scaling` (advanced): left for the next
  pass; the estimate itself is intermediate, scaling decisions are advanced.
* *Security logging and detection (OWASP A09)* and *`networking`/`cs` optional extras*: queued as future concepts.
<!-- suggestions:end -->
