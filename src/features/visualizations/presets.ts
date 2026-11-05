// Curated visualizations for the Visual explorer. Lessons can embed the same
// components with their own props; these presets are reviewed reference diagrams.
import type { VisualizationId } from "../../content/visualizationSchemas";

export interface Preset {
  id: string;
  component: VisualizationId;
  title: string;
  summary: string;
  concepts: string[];
  props: Record<string, unknown>;
}

export const presets: Preset[] = [
  {
    id: "tracer-aliasing",
    component: "python-tracer",
    title: "Names, objects and aliasing",
    summary: "Step through Python and watch names attach to objects. Edit the code to explore your own programs.",
    concepts: ["python.variables", "python.mutability"],
    props: { code: "a = [1, 2]\nb = a\nb.append(3)\nc = [1, 2, 3]\nprint(a == c, a is c)\n" },
  },
  {
    id: "http-lifecycle",
    component: "step-diagram",
    title: "The life of an HTTP request",
    summary: "From typing a URL to rendering JSON: DNS, TCP, TLS, the request, routing, the database and the response.",
    concepts: ["networking.http-basics", "networking.dns", "networking.tls", "backend.web-frameworks"],
    props: {
      width: 760,
      height: 300,
      nodes: [
        { id: "client", label: "Browser / client", x: 90, y: 150, shape: "actor" },
        { id: "dns", label: "DNS resolver", x: 300, y: 50 },
        { id: "proxy", label: "Reverse proxy", x: 330, y: 220 },
        { id: "app", label: "API app", x: 520, y: 220 },
        { id: "db", label: "Database", x: 690, y: 220, shape: "store" },
      ],
      edges: [
        { id: "c-dns", from: "client", to: "dns", label: "1. name → IP" },
        { id: "c-proxy", from: "client", to: "proxy", label: "TCP + TLS + HTTP" },
        { id: "proxy-app", from: "proxy", to: "app", label: "forward" },
        { id: "app-db", from: "app", to: "db", label: "SQL" },
      ],
      steps: [
        { title: "Parse the URL", body: "The client splits `https://api.example.com/notes?limit=2` into scheme (`https`), host, default port 443, path `/notes` and query `limit=2`.", active: ["client"] },
        { title: "Resolve the name with DNS", body: "The host name must become an IP address. The resolver answers from cache or asks the DNS hierarchy; the answer is cached for its TTL.", active: ["client", "dns", "c-dns"], payload: "api.example.com.  300  IN  A  203.0.113.10" },
        { title: "Open a TCP connection", body: "A three-way handshake (SYN, SYN-ACK, ACK) to port 443 creates a reliable, ordered byte stream.", active: ["client", "proxy", "c-proxy"] },
        { title: "Secure it with TLS", body: "The server presents a certificate for `api.example.com`; the client checks it chains to a trusted authority, then both sides derive encryption keys. Everything after this is encrypted.", active: ["client", "proxy", "c-proxy"] },
        { title: "Send the HTTP request", body: "A request is plain text inside the encrypted stream: a method, a target, headers and (for POST/PUT) a body.", active: ["client", "proxy", "c-proxy"], payload: "GET /notes?limit=2 HTTP/1.1\nHost: api.example.com\nAccept: application/json\nAuthorization: Bearer <token>" },
        { title: "Route to the application", body: "A reverse proxy terminates TLS and forwards to an app server. The framework runs middleware (logging, auth), matches the route and validates parameters.", active: ["proxy", "app", "proxy-app"] },
        { title: "Query the database", body: "The handler fetches data with a parameterised query — never by pasting user input into SQL.", active: ["app", "db", "app-db"], payload: "SELECT id, title FROM notes ORDER BY id LIMIT ?;   -- params: (2,)" },
        { title: "Send the response", body: "Status line, headers, then the body. `200 OK` means success; the `Content-Type` tells the client how to parse the body.", active: ["client", "proxy", "app", "c-proxy", "proxy-app"], payload: 'HTTP/1.1 200 OK\nContent-Type: application/json\nCache-Control: no-store\n\n[{"id": 1, "title": "Buy milk"}, {"id": 2, "title": "Call Ada"}]' },
        { title: "Use the result", body: "The client parses the JSON. The connection is usually kept alive and reused for the next request, skipping DNS, TCP and TLS setup.", active: ["client"] },
      ],
    },
  },
  {
    id: "rag-pipeline",
    component: "step-diagram",
    title: "A retrieval-augmented generation pipeline",
    summary: "Offline indexing, then per-question retrieval, context assembly and grounded generation with citations.",
    concepts: ["rag.why-rag", "rag.chunking", "rag.vector-similarity", "rag.context-assembly", "rag.grounding-citations"],
    props: {
      width: 780,
      height: 320,
      nodes: [
        { id: "docs", label: "Documents", x: 80, y: 70, shape: "store" },
        { id: "chunk", label: "Parse + chunk", x: 250, y: 70 },
        { id: "embed", label: "Embed chunks", x: 420, y: 70 },
        { id: "index", label: "Index (vector + BM25)", x: 620, y: 70, shape: "store" },
        { id: "user", label: "User question", x: 80, y: 240, shape: "actor" },
        { id: "retrieve", label: "Retrieve top-k", x: 300, y: 240 },
        { id: "prompt", label: "Assemble prompt", x: 480, y: 240 },
        { id: "llm", label: "LLM", x: 660, y: 240, shape: "pill" },
      ],
      edges: [
        { id: "e1", from: "docs", to: "chunk" },
        { id: "e2", from: "chunk", to: "embed" },
        { id: "e3", from: "embed", to: "index" },
        { id: "e4", from: "user", to: "retrieve", label: "query" },
        { id: "e5", from: "index", to: "retrieve", label: "search" },
        { id: "e6", from: "retrieve", to: "prompt", label: "chunks" },
        { id: "e7", from: "prompt", to: "llm" },
      ],
      steps: [
        { title: "Ingest documents", body: "Extract clean text and metadata (title, source, date, permissions) from each file. Parsing errors here silently cap quality later.", active: ["docs", "e1", "chunk"] },
        { title: "Chunk", body: "Split text into overlapping, retrievable pieces sized for the embedding model and the prompt budget. Keep the source and position with every chunk.", active: ["chunk"], payload: "chunk_id: handbook.md#12\ntext: 'Refunds are issued within 14 days…'\nmetadata: {source: handbook.md, section: Refunds}" },
        { title: "Embed and index (offline)", body: "Each chunk becomes a vector; vectors go into a nearest-neighbour index, and text into a keyword index. This happens once per document version, not per question.", active: ["embed", "e2", "e3", "index"] },
        { title: "A question arrives", body: "The question is embedded with the **same** model used for the chunks, and tokenised for keyword search.", active: ["user", "e4", "retrieve"], payload: "How long do refunds take?" },
        { title: "Retrieve", body: "Find the most similar chunks (cosine similarity) and the best keyword matches, fuse the rankings, and apply metadata filters such as the user's permissions.", active: ["retrieve", "e5", "index"] },
        { title: "Assemble the context", body: "Order and deduplicate the top chunks, fit them in the token budget, label each with its source, and instruct the model to answer only from them.", active: ["prompt", "e6"], payload: "Answer using ONLY the sources below. Cite them like [1].\nIf the answer is not in the sources, say you don't know.\n\n[1] handbook.md#12: Refunds are issued within 14 days…\n\nQuestion: How long do refunds take?" },
        { title: "Generate a grounded answer", body: "The model answers with citations. Evaluate retrieval and generation separately: a wrong answer is usually a retrieval failure.", active: ["llm", "e7"], payload: "Refunds are issued within 14 days of approval [1]." },
      ],
    },
  },
  {
    id: "agent-loop",
    component: "step-diagram",
    title: "The agent tool-call loop",
    summary: "An LLM decides which tool to call, your code validates and runs it, and the result goes back — until a stop condition.",
    concepts: ["agents.agent-loop", "genai.tool-calling", "agents.human-in-the-loop", "agents.failure-recovery"],
    props: {
      width: 760,
      height: 320,
      nodes: [
        { id: "user", label: "User goal", x: 90, y: 60, shape: "actor" },
        { id: "llm", label: "LLM (decides)", x: 330, y: 60, shape: "pill" },
        { id: "runtime", label: "Your agent code", x: 330, y: 200 },
        { id: "approve", label: "Human approval", x: 600, y: 60, shape: "actor" },
        { id: "tools", label: "Tools", x: 600, y: 200 },
        { id: "state", label: "State / memory", x: 90, y: 230, shape: "store" },
      ],
      edges: [
        { id: "u-l", from: "user", to: "llm", label: "goal" },
        { id: "l-r", from: "llm", to: "runtime", label: "tool call" },
        { id: "r-a", from: "runtime", to: "approve", label: "risky?" },
        { id: "r-t", from: "runtime", to: "tools", label: "execute" },
        { id: "r-s", from: "runtime", to: "state", label: "record" },
      ],
      steps: [
        { title: "Give the model a goal and tools", body: "The prompt contains the goal, the conversation so far and a description (name, purpose, JSON schema) of each tool.", active: ["user", "llm", "u-l"] },
        { title: "The model proposes an action", body: "The model does not run anything itself. It returns a structured request to call a tool — or a final answer.", active: ["llm", "l-r", "runtime"], payload: '{"tool": "get_order", "arguments": {"order_id": "A-1042"}}' },
        { title: "Validate the call", body: "Your code checks the tool exists, validates arguments against the schema and enforces permissions. Invalid calls become error messages sent back to the model.", active: ["runtime"] },
        { title: "Ask a human for risky actions", body: "Irreversible or costly actions (refunds, emails, deletions) wait for approval; the person can approve, edit or reject.", active: ["runtime", "r-a", "approve"] },
        { title: "Execute the tool", body: "Run it with timeouts and retries for transient failures. Treat the result as untrusted data — it may contain injected instructions.", active: ["runtime", "r-t", "tools"], payload: '{"order_id": "A-1042", "status": "delivered", "total": 1299}' },
        { title: "Record the observation", body: "Append the call and its result to the state the model sees next, and to logs for tracing and evaluation.", active: ["runtime", "r-s", "state"] },
        { title: "Loop or stop", body: "The model sees the observation and decides again. Stop when it gives a final answer, when the step or cost budget runs out, or when a loop is detected.", active: ["llm", "runtime", "l-r"] },
      ],
    },
  },
  {
    id: "mcp-session",
    component: "step-diagram",
    title: "MCP requests (revision 2026-07-28)",
    summary:
      "How a host application discovers and calls tools on a Model Context Protocol server. Messages follow the 2026-07-28 specification, where every request is self-contained (no initialize handshake).",
    concepts: ["agents.mcp", "agents.mcp-servers"],
    props: {
      width: 760,
      height: 260,
      nodes: [
        { id: "host", label: "Host app (chat / IDE)", x: 110, y: 130, shape: "actor" },
        { id: "client", label: "MCP client", x: 360, y: 130 },
        { id: "server", label: "MCP server", x: 620, y: 130 },
      ],
      edges: [
        { id: "h-c", from: "host", to: "client" },
        { id: "c-s", from: "client", to: "server", label: "JSON-RPC (stdio or HTTP)" },
      ],
      steps: [
        {
          title: "Connect",
          body: "The host launches a local server as a subprocess (stdio transport) or connects to a remote one over Streamable HTTP. Each client talks to one server. In this revision an open connection is **not** a session: every request stands alone.",
          active: ["host", "client", "server", "h-c"],
        },
        {
          title: "Discover (optional)",
          body: "`server/discover` returns the protocol versions, capabilities and identity of the server in one call. Every request — this one included — carries the protocol version and client capabilities in `params._meta`.",
          active: ["client", "server", "c-s"],
          payload:
            '→ {"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{\n     "io.modelcontextprotocol/protocolVersion":"2026-07-28",\n     "io.modelcontextprotocol/clientCapabilities":{}}}}\n← {"jsonrpc":"2.0","id":1,"result":{"resultType":"complete",\n     "supportedVersions":["2026-07-28"],"capabilities":{"tools":{}},\n     "_meta":{"io.modelcontextprotocol/serverInfo":{"name":"notes","version":"0.1"}}}}',
        },
        {
          title: "List tools",
          body: "Each tool has a name, a description and a JSON Schema for its input. The host shows them to the model. Treat descriptions from untrusted servers as untrusted text.",
          active: ["client", "server", "c-s"],
          payload:
            '→ {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{"_meta":{…same per-request fields…}}}\n← {"jsonrpc":"2.0","id":2,"result":{"resultType":"complete","tools":[{"name":"search_notes",\n     "description":"Full-text search over notes",\n     "inputSchema":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}]}}',
        },
        {
          title: "Call a tool",
          body: "When the model wants a tool, the host — after the user consents — asks the client to call it. Results come back as content blocks; a tool failure sets `isError` rather than raising a protocol error.",
          active: ["host", "client", "server", "h-c", "c-s"],
          payload:
            '→ {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search_notes",\n     "arguments":{"query":"refund"},"_meta":{…same per-request fields…}}}\n← {"jsonrpc":"2.0","id":3,"result":{"resultType":"complete",\n     "content":[{"type":"text","text":"2 notes found…"}],"isError":false}}',
        },
        {
          title: "Version mismatch",
          body: "If the server does not speak the requested version it answers with error −32022 and lists the versions it supports; the client retries with one of them. Servers from revision 2025-11-25 and earlier instead expect an `initialize` handshake — dual-era clients detect and fall back.",
          active: ["client", "server", "c-s"],
          payload: '← {"jsonrpc":"2.0","id":4,"error":{"code":-32022,"message":"Unsupported protocol version",\n     "data":{"supported":["2026-07-28","2025-11-25"],"requested":"1900-01-01"}}}',
        },
        { title: "Use the result", body: "The host gives the tool result to the model as an observation. Servers can also offer resources (data to read) and prompts (templates).", active: ["host", "h-c"] },
      ],
    },
  },
  {
    id: "ci-cd",
    component: "step-diagram",
    title: "A CI/CD pipeline",
    summary: "Every push is linted, tested and built automatically; verified artefacts are promoted through environments.",
    concepts: ["mlops.ci-cd", "mlops.release-strategies"],
    props: {
      width: 780,
      height: 230,
      nodes: [
        { id: "dev", label: "Push / PR", x: 70, y: 110, shape: "actor" },
        { id: "lint", label: "Lint + types", x: 210, y: 110 },
        { id: "test", label: "Tests", x: 340, y: 110 },
        { id: "build", label: "Build image", x: 470, y: 110 },
        { id: "staging", label: "Staging", x: 600, y: 50 },
        { id: "prod", label: "Production", x: 720, y: 170 },
      ],
      edges: [
        { id: "a", from: "dev", to: "lint" },
        { id: "b", from: "lint", to: "test" },
        { id: "c", from: "test", to: "build" },
        { id: "d", from: "build", to: "staging", label: "deploy" },
        { id: "e", from: "staging", to: "prod", label: "promote" },
      ],
      steps: [
        { title: "Trigger", body: "A push or pull request starts a pipeline on a clean machine, so results do not depend on anyone's laptop.", active: ["dev"] },
        { title: "Fast checks first", body: "Linters, formatters and type checkers fail in seconds, giving quick feedback.", active: ["dev", "a", "lint"] },
        { title: "Tests", body: "Unit and integration tests run, often across a matrix of versions. A failing test blocks the merge.", active: ["lint", "b", "test"] },
        { title: "Build one artefact", body: "Build a versioned artefact (for example a container image tagged with the commit). The same artefact moves through every environment.", active: ["test", "c", "build"] },
        { title: "Deploy to staging", body: "Deploy automatically to a production-like environment and run smoke tests against it.", active: ["build", "d", "staging"] },
        { title: "Promote safely", body: "Release to production gradually (canary or blue–green), watch error rates and latency, and roll back automatically if they degrade.", active: ["staging", "e", "prod"] },
      ],
    },
  },
  {
    id: "vectors",
    component: "vector-similarity",
    title: "Vector similarity",
    summary: "Dot product, cosine similarity and Euclidean distance — the maths behind embedding search.",
    concepts: ["math.vectors", "rag.vector-similarity"],
    props: { a: [3, 1], b: [1, 2] },
  },
  {
    id: "big-o",
    component: "complexity-growth",
    title: "How algorithms scale",
    summary: "Operation counts for O(1) to O(2ⁿ) as the input grows.",
    concepts: ["cs.complexity"],
    props: { maxN: 32 },
  },
  {
    id: "bfs-dfs",
    component: "graph-traversal",
    title: "Breadth-first vs depth-first search",
    summary: "Watch the queue or stack drive the order in which a graph is explored.",
    concepts: ["cs.graphs"],
    props: {
      nodes: [
        { id: "A", x: 40, y: 120 },
        { id: "B", x: 150, y: 40 },
        { id: "C", x: 150, y: 200 },
        { id: "D", x: 270, y: 40 },
        { id: "E", x: 270, y: 200 },
        { id: "F", x: 380, y: 120 },
      ],
      edges: [
        ["A", "B"],
        ["A", "C"],
        ["B", "D"],
        ["C", "E"],
        ["D", "F"],
        ["E", "F"],
        ["B", "C"],
      ],
      start: "A",
      directed: false,
    },
  },
  {
    id: "gradient",
    component: "gradient-descent",
    title: "Gradient descent",
    summary: "Minimise a loss by stepping against the gradient; see how the learning rate changes everything.",
    concepts: ["math.optimization", "ml.linear-regression"],
    props: { target: 3, start: -4, learningRate: 0.1 },
  },
  {
    id: "joins",
    component: "sql-join",
    title: "SQL joins",
    summary: "INNER, LEFT, RIGHT and FULL OUTER joins on the same two tables (verified against SQLite in the tests).",
    concepts: ["databases.sql-joins"],
    props: {
      left: { name: "users", key: "id", columns: ["id", "name"], rows: [[1, "Ada"], [2, "Linus"], [3, "Grace"]] },
      right: { name: "orders", key: "user_id", columns: ["order_id", "user_id", "total"], rows: [[10, 1, 250], [11, 1, 120], [12, 3, 990], [13, 7, 45]] },
    },
  },
  {
    id: "neural",
    component: "neural-forward",
    title: "A neural network forward pass",
    summary: "Weighted sums and activations flowing through a tiny network.",
    concepts: ["dl.neurons-layers", "dl.forward-propagation", "dl.activation-functions"],
    props: { inputs: [1, 0.5] },
  },
  {
    id: "attention",
    component: "attention",
    title: "Scaled dot-product attention",
    summary: "How each token mixes information from the others — with and without a causal mask.",
    concepts: ["dl.attention", "dl.transformer-architecture"],
    props: { tokens: ["the", "cat", "sat", "on", "mats"] },
  },
];
