# Curriculum

The curriculum is one **knowledge graph** of concepts connected by prerequisite edges, organised into 21 stages
and their modules. Lessons, assessments, projects, interview questions, glossary terms and learning paths all hang
off that graph, so nothing is duplicated and every recommendation can explain itself.

See [CURRICULUM_AUDIT.md](CURRICULUM_AUDIT.md) for how the graph was derived, the coverage matrix and what is still
missing, and [ROADMAP.md](ROADMAP.md) for which concepts have full lessons today.

## Stages

| # | Stage | What it covers |
|---|---|---|
| 1 | Computer and Development Foundations | Hardware, data representation, OS and processes, files and paths, terminal, environment variables, installing tools, editors, how programs run, algorithmic thinking, internet basics, troubleshooting, reading docs, how to learn. |
| 2 | Python | First program → variables, numbers, strings, I/O, control flow, collections and references, functions and scope, errors and debugging, files and modules, idioms (comprehensions, iterators, generators, closures, decorators, context managers), OOP, typing, testing, logging, environments and packaging, CLI, configuration, performance, concurrency, asyncio, internals, secure coding. |
| 3 | CS and Software Engineering | Decomposition, Big-O, recursion, searching, sorting, algorithm design, arrays, hashing, stacks/queues, linked lists, trees, heaps, graphs, shortest paths; abstraction, OOP and functional principles, SOLID, patterns, clean code, refactoring; testing strategy, code review, SDLC, requirements and docs, dependency management, concurrency, architectural trade-offs. |
| 4 | Git, GitHub, Linux and the Shell | Version control, commits, undo, branches, conflicts, rebase, internals, remotes, collaboration, pull requests, branching strategies; Linux file system, permissions, processes, pipes, scripting, SSH, package managers. |
| 5 | Networking, HTTP and the Web | Layers, IP and ports, DNS, TCP/UDP, sockets, HTTP requests and semantics, URLs, cookies, TLS, CORS, browsers, JSON APIs, HTTP clients, REST, other API styles, proxies and load balancers, network debugging. |
| 6 | Backend Development | Frameworks, API design, error handling, FastAPI, Pydantic, middleware, dependency injection, async endpoints, authentication, authorisation, secrets, configuration, background jobs, events, caching, rate limiting, API testing. |
| 7 | Databases | Relational model, SQL (queries, modification, aggregation, joins, CTEs, window functions), schema design, indexes, query plans, transactions, sqlite3, PostgreSQL, migrations, ORMs, pooling, backups, Redis, NoSQL models. |
| 8 | Maths and Statistics for ML | Functions and logs, summation, vectors, matrices, transformations, eigen/SVD, derivatives, gradients, optimisation, probability, Bayes, random variables, distributions, descriptive statistics, inference, hypothesis testing, information theory, numerical computing. |
| 9 | Data Analysis | Notebooks, NumPy, pandas, loading data, transforms, cleaning, data quality, EDA, visualisation, feature engineering, time series. |
| 10 | Data Engineering | Formats, ETL/ELT, batch vs streaming, idempotency, orchestration, dbt, dimensional modelling, warehouses/lakes/lakehouses, schema evolution, distributed systems, Spark, Kafka, pipeline quality, lineage and governance, cloud platforms, Databricks. |
| 11 | Machine Learning | What ML is, learning types, splits, linear/logistic regression, kNN, trees, ensembles, SVM, clustering, dimensionality reduction, metrics, overfitting, cross-validation, leakage, scikit-learn, tuning, imbalance, pipelines, reproducibility, interpretability, fairness, RL basics. |
| 12 | Deep Learning and Transformers | Neurons, activations, forward pass, losses, backpropagation, optimisers, training loops, regularisation, PyTorch, embeddings, CNNs, RNNs, tokenisation, attention, Transformers, positional information, pretraining and fine-tuning, GPUs, inference performance. |
| 13 | Generative AI and LLM Engineering | What LLMs are, tokens and context, sampling, architecture, hallucinations, prompting, APIs, structured outputs, tool calling, local inference, licensing, model selection, fine-tuning, multimodal, evaluation, prompt injection, guardrails, cost and latency. |
| 14 | RAG | Why RAG, ingestion, chunking, keyword search (BM25), embeddings, vector similarity, vector databases, hybrid search, metadata filters, reranking, context assembly, grounding and citations, advanced patterns, evaluation, failure analysis, access control, performance, observability. |
| 15 | LLM Frameworks | Why frameworks, LangChain core/tools/retrievers, LangGraph state graphs, persistence, human-in-the-loop, LangSmith, Langfuse, LlamaIndex, other SDKs, trade-offs. |
| 16 | Agentic AI | Agents vs workflows, the agent loop, planning, tool design, state and memory, human approval, permissions and sandboxing, recovery, multi-agent systems, MCP, building MCP servers, A2A, LangGraph agents, CrewAI, AutoGen, other frameworks, evaluation, security, observability. |
| 17 | Graphs and Knowledge Systems | Property graphs, relational vs graph, Cypher, traversals, modelling, Neo4j and local options, knowledge graphs, KG construction, graph algorithms, GraphRAG. |
| 18 | MLOps, LLMOps and Production | Containers, Docker, CI/CD, environments, releases, experiment tracking, MLflow, versioning, serving, training pipelines, logging and tracing, observability, model monitoring, incidents, SRE, scaling, caching/queues, fault tolerance, Kubernetes, IaC, cost, LLMOps, production evaluation. |
| 19 | Security, Privacy and Responsible AI | Security mindset, cryptography basics, threat modelling, OWASP Top 10, input handling, secrets, supply chain, privacy engineering, LLM security, responsible AI, governance. |
| 20 | System Design and Cloud | System design, estimation, scalability, monoliths vs microservices, consistency and consensus, distributed patterns, cloud fundamentals, serverless, AI system design. |
| 21 | Interviews and Mastery | Problem-solving process, coding, system design, ML and GenAI interviews, debugging interviews, technical communication, project walkthroughs. |

## Prerequisite philosophy

* **Direct prerequisites only.** A concept lists what you must already understand to follow it; transitive
  prerequisites are inferred. The graph is validated to be acyclic.
* **Stages are groupings, not gates.** Order comes from the graph. Advanced Python topics may depend on CS concepts
  (`python.profiling` needs `cs.complexity`), and TLS depends on cryptography basics in the security stage.
* **Maths when it becomes useful.** GenAI application concepts (`genai.what-are-llms`, prompting, tool calling) do not
  require backpropagation; the deeper `genai.llm-architecture` does. Embeddings need vectors, not calculus.
* **Concepts before frameworks.** Every framework concept (LangChain, LangGraph, CrewAI, MLflow, Spark…) requires the
  framework-independent concept it implements, and protocols (MCP, A2A) are taught separately from frameworks.
* **Priorities:** *essential* foundation · *supporting* knowledge · *advanced* specialisation · *optional* enrichment ·
  *technology-specific* implementation. Essential concepts come first in recommendations; the whole roadmap is
  visible from day one.

## Learning paths

Paths are defined only by their **targets** (`content/paths.yaml`); each path is the prerequisite closure of its
targets, ordered so every concept comes after everything it needs. Current paths: Python Developer, Backend Developer,
Data Scientist, Data Engineer, ML Engineer, GenAI Engineer, RAG Application Developer, Agentic AI Engineer, Production
AI Engineer, and Technical Interview Preparation. Experienced learners can **skip what they know** with a diagnostic
(two mastery-check questions per lesson, one of them always code) or mark outline-only concepts as known
(self-reported, labelled as such).

## Lesson design

Each lesson adapts this structure: objectives and prerequisites → why it exists → plain definition → mental model →
visual explanation (step-through tracer or diagram) → how it works inside (optional deep dive) → step-by-step
walkthrough → annotated, executed examples → common mistakes with real error messages → debugging → practice across
skills → interview angle → summary and cheat sheet → related concepts → mastery check.
"Show deep dives" toggles between the beginner view and full technical detail.

## How mastery is measured

Assessment items are tagged with a **skill**: recognition, explanation, prediction, implementation, debugging,
transfer or design. Rules (implemented in `src/engine/mastery.ts`, unit-tested):

| Status | Rule |
|---|---|
| Not started | No lesson visit and no attempts. |
| Learning | Any activity, not yet proficient. |
| Proficient | ≥ 3 distinct items attempted, ≥ 70 % correct on each item's **latest** attempt, and correct answers covering ≥ 2 skills. |
| Mastered | Passed the lesson's mastery check: new items, one attempt each, no hints, score ≥ the pass mark (usually 80 %) **and** at least one coding/debugging task solved independently. Also reached via a diagnostic (both items correct) or, for outline-only concepts, self-reported (always labelled). |
| Weak (flag) | ≥ 3 recent attempts and < 60 % of the last 5 correct. |
| Review due (flag) | The spaced-review date has arrived. |

**Spaced review** uses Leitner boxes with intervals of 1, 3, 7, 16, 35 and 90 days. A review asks three questions
chosen from items you have not seen recently, mixing skills and including a coding task once the concept has been
reviewed before; passing (≥ 2/3) moves the concept up a box, failing makes it due again immediately.

**Explanations** are self-assessed against a visible rubric (≥ 75 % of points) and labelled as such; they never count
toward reviews. Optional local AI may assist in future, but core assessment never depends on it.

**Recommendations** (`src/engine/recommend.ts`) follow a fixed priority — due reviews, weak concepts, unfinished
lessons (or their mastery check), then the next concept in your active path (or its earliest unmet prerequisite) —
and always display the reason.
