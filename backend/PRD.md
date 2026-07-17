# Product Requirements Document: Java Codebase Agentic Analyzer

## 1. What is this?

This is a tool that reads through a Java codebase — potentially thousands of
files — and automatically produces three things a business or engineering
team actually wants, but rarely has time to write by hand:

1. **A plain list of the business rules hidden inside the code**
   (e.g. *"If the order quantity is zero or less, reject it"*).
2. **A map of how the different parts of the system depend on and call
   each other** (which service talks to which, who calls whom).
3. **Human-readable documentation** describing what each class and method
   does, including diagrams of the decision logic.

You give it a codebase (a ZIP file or a link to a Git repository). A few
seconds to a few minutes later — depending on size — you get back a
structured, browsable answer instead of having to read the source code
yourself.

## 2. The problem it solves

Large, older Java systems ("legacy code") accumulate business logic that
lives only inside `if` statements and `switch` blocks written years ago by
people who may no longer be at the company. When the business needs to
answer "what exactly happens when a customer cancels an order after
payment?", the honest answer today is: *someone has to go read the code*.

This tool automates that reading. It doesn't replace an engineer's
judgment, but it turns a multi-day "go dig through the codebase" exercise
into a report that can be generated on demand and kept up to date.

## 3. Who uses it

- **Business analysts / product managers** who need to understand what a
  legacy system actually does before requesting a change.
- **Engineers new to a codebase** who want a fast orientation instead of
  reading thousands of files line by line.
- **Architects** planning a migration or a rewrite, who need to know which
  services depend on which before they touch anything.
- **Compliance/audit teams** who need a record of validation rules
  (e.g. "what stops a negative order quantity from being processed?").

## 4. How it works, in plain English

Think of the system as **a small team of specialists** working together,
managed by a project lead. This mirrors how a human team would actually
tackle "go read this huge codebase and summarize it":

| Role | What they do |
|---|---|
| **The Project Lead** (Supervisor) | Receives the codebase, splits it into manageable batches of files, hands batches out to readers, and reviews the combined result at the end. |
| **The Readers** (Parsing specialists) | Each one skims a batch of files at the same time as the others (working in parallel, not one-by-one), turning raw code into a structured outline of classes, methods, conditions, and calls. |
| **The Rule Spotter** (Logic extraction) | Goes through that outline looking for decision points — `if`, `switch` — and figures out which ones look like validation checks, which look like business decisions, and which are just routing logic. |
| **The Rule Writer** (Rule mining) | Turns each decision point into a plain sentence: *"IF &lt;condition&gt; THEN &lt;action&gt;"* — the same format a business analyst would write in a requirements document. |
| **The Cartographer** (Dependency mapping) | Draws the "org chart" of the code: which class calls which other class, which services depend on which other services. |
| **The Technical Writer** (Documentation) | Writes up a readable summary per class/method, plus flowcharts of the decision logic. |
| **The Reviewer** (Critic) | Checks everyone's work. Did some files fail to read cleanly? Did we find suspiciously few rules for the amount of code? Is the dependency map full of question marks? It scores the overall confidence in the result, and if that score is too low, it sends the weak parts back to be redone — up to a few times — rather than accepting a shoddy first draft. |

This "redo the weak parts, not everything" behavior is the key quality
control in the system: instead of blindly re-running the whole analysis
when something looks off, it only sends back the specific step that's
weak (e.g. just the dependency mapping, or just the rule writing),
which is both faster and cheaper.

## 5. A real example (from this project's own test data)

The system was run against three small sample Java files (an order
service, an inventory service, and a REST controller — a typical
"place an order" flow). Here is exactly what it produced, unedited:

**Summary:** 3 files → 3 classes → 8 methods → **8 business rules found**,
overall confidence **77%**.

**Three of the rules it wrote, in its own words:**

- *IF order == null THEN throw "Order must not be null"*
- *IF order.getQuantity() <= 0 THEN throw "Quantity must be greater than zero"*
- *IF the requested stock is not available THEN mark the order as REJECTED*

**Part of the dependency map it built:** `OrderController` calls
`OrderService.placeOrder()`, which in turn calls `InventoryService` to
check stock and `PaymentService` to charge the customer — exactly the
real call chain in the code, discovered automatically rather than
documented by hand.

**One honest gap it flagged itself:** of the calls it found, 16 could not
be confidently matched to a known method (e.g. calls like
`order.getSku()` where "order" is just a piece of data being passed
around, not a service). The system reports this rather than guessing
silently — see "What this tool is not," below.

## 6. What you get back

You interact with the system through four simple requests:

1. **"Analyze this codebase"** — upload a ZIP or point it at a Git repo.
   You get back a tracking ID immediately; the analysis runs in the
   background so you're not stuck waiting on a slow request.
2. **"What's the status?"** — check whether the analysis is still running,
   finished, or failed, plus the headline numbers (files/classes/methods/
   rules found, confidence score).
3. **"Show me the rules"** — the full list of IF/THEN business rules.
4. **"Show me the dependencies"** — the call/service map.
5. **"Show me the documentation"** — the readable write-up and decision
   diagrams.

Everything is saved (in a simple database) so you can come back later and
re-fetch results without re-running the analysis.

## 7. Quality and trust

Every result comes with a **confidence score from 0 to 100%**, built from
four honest questions the system asks itself:
how much of the code parsed without errors, how much of it yielded
extractable logic, how many rules it found relative to the amount of code,
and how much of the dependency map it could actually resolve with
certainty. If confidence is too low, it automatically retries the weak
parts (up to 3 times) before handing back a final answer — and if it's
still not confident after that, it tells you exactly which part is weak
(e.g. "16 calls could not be resolved") instead of hiding the gap.

## 8. What this tool is not

- **It is not a compiler.** It doesn't fully understand Java's type system,
  so some method calls (especially through method parameters rather than
  through the service's own fields) may be reported as "unresolved" rather
  than confidently linked. This is intentional — the tool would rather
  admit uncertainty than silently guess wrong.
- **It does not use AI/LLM text generation by default.** Out of the box,
  every rule and description comes from directly reading the code
  structure, not from an AI's interpretation — so results are
  deterministic and reproducible. An optional AI-enhancement mode can be
  turned on later to make rule wording read more naturally, but it is
  off unless a team deliberately enables it.
- **It does not modify your code.** It only reads it.

## 9. Under the hood, briefly (for technical stakeholders)

- Built as a Python web service (FastAPI) that exposes the four requests
  above.
- Reads Java source using an industry-standard code-parsing library
  (Tree-sitter) — the same category of technology that powers syntax
  highlighting in modern code editors — rather than pattern-matching text
  with regular expressions.
- Processes many files at once using parallel workers, so a large codebase
  doesn't take proportionally longer per file.
- Results are stored in a lightweight database (SQLite) with a clear
  upgrade path to a larger database if usage grows.
- Every step's timing and success/failure is logged, so if something
  underperforms it's traceable to a specific stage rather than a black box.
- Two optional, off-by-default upgrades exist for teams that want them:
  an alternative "workflow visualization" style of running the same
  pipeline (LangGraph), and exporting the dependency map into a graph
  database (Neo4j) for more advanced querying.

## 10. Glossary

- **Codebase**: the full collection of source code files for an
  application.
- **Business rule**: a condition-and-action pair that reflects a real
  business decision (e.g. "reject orders with zero quantity").
- **Dependency graph**: a map of which piece of code relies on or calls
  which other piece.
- **Confidence score**: the system's own self-assessment of how complete
  and trustworthy a given analysis result is.
- **Agent**: a specialized worker (in this case, a piece of software, not
  a person) responsible for one step of the analysis, analogous to a
  team member with one job.
