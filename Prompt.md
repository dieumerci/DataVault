# AI Prompts Used During Development

The assignment encourages responsible use of AI tools. Below are the prompts I used at different stages of building this project, along with context on what I was thinking at each step.

---

## Prompt 1 — Initial Architecture & Scaffolding

**"Help me scaffold a Django project for a document intake system with PDF extraction and field corrections. I need Docker setup, a services layer pattern, and HTMX for the frontend. Guide me on structuring the models, writing regex parsers for financial fields, and implementing COALESCE-based search."**

### What I was thinking:

I already knew the tech stack I wanted before I opened the AI. I'd used Django and DRF before so I knew the basics, but I wanted to move fast on the boilerplate — Docker setup, project structure, the migration file. The interesting part to me was the COALESCE pattern for effective values, because that's what makes the correction workflow actually work. I needed search to reflect corrected data, not stale originals, and I wanted to think through whether to do that at the Python level, the ORM level, or raw SQL. I ended up doing all three, which I'm glad about because it shows I understand the trade-offs at each layer.

The services layer decision was mine — I've seen too many Django projects where views become 200-line monsters. Keeping business logic in plain Python functions means I can call the same `ingest_pdf()` from the API, the UI, or a future Celery task without duplicating anything.

---

## Prompt 2 — UI Polish & HTMX Patterns

**"I want to add inline field correction to my document detail page using HTMX. When the user types a corrected value and hits enter, the row should update without a full page reload. Show me the partial template pattern — how to use the same template fragment for both initial render and the HTMX swap response."**

### What I was thinking:

I'd used HTMX on a side project before, but I hadn't done the partial template pattern where the same `field_row.html` fragment serves double duty — Django includes it on page load, and the correction view returns it as the HTMX swap response. That felt cleaner than having two separate templates that could drift out of sync.

The AI helped me get the `hx-post`, `hx-target`, and `hx-swap="outerHTML"` wiring right on the first try. Without it I probably would've spent an hour debugging why the swap wasn't replacing the right element. The actual styling (Tailwind classes, confidence bars, the flash animation on save) was me — I wanted it to feel polished, not like a generic admin panel.

---

## Prompt 3 — Generating Sample PDFs for Testing

**"I need realistic sample PDF documents to test my extraction pipeline. Generate one for each form type my app supports: a W-9 tax form, an ACH Authorization form, and a Loan Application. Each one should have realistic-looking field labels and values — things like routing numbers, account numbers, dollar amounts, and customer names — laid out the way you'd actually see them on a real form. I need the parsers to be able to pick up the fields, so make sure the labels match patterns like 'Name:', 'Customer:', 'Amount: $X,XXX.XX', and include 9-digit routing numbers."**

### What I was thinking:

I had the extraction pipeline built — four regex parsers for routing numbers, account numbers, dollar amounts, and customer names — but I didn't have real documents to test them against. I couldn't just download actual W-9s or bank forms (privacy, legal issues), and blank government forms don't have the filled-in values my parsers need to find.

So I asked the AI to generate sample PDFs with realistic but fake data. The key was making sure the text matched what my regex patterns look for: a 9-digit number for the routing parser, a dollar amount with the `$` prefix for the amount parser, and labeled names like "Customer Name: Jane Smith" for the name parser. I basically used the AI to create test fixtures that exercise every branch of my extraction code.

This is something I'd do on any project — you need representative test data before you can trust your parsing logic. The alternative was manually creating PDFs in Word or Google Docs, which would've taken way longer and I'd probably miss edge cases.

---

## How I Used AI Overall

I used AI the way I'd use it on the job — as a thinking partner for architecture decisions and a speed boost on boilerplate. The things I relied on it for:

- **Scaffolding**: Docker setup, project structure, migration file
- **Pattern validation**: "Is subquery the right approach here, or should I use a JOIN?"
- **Debugging**: Getting psycopg working on Python 3.15 (no pre-built wheels, needed libpq)
- **Syntax**: HTMX attributes, Django ORM annotation syntax

The things that were my calls:

- **UUID primary keys** — sequential IDs leak information in financial systems
- **Three-app structure** (documents, api, ui) — separation of domain logic from HTTP
- **Services layer** — views stay under 20 lines, logic lives in testable functions
- **pypdf over Tesseract** — pure Python, no system deps, keeps Docker image small
- **Raw SQL for reporting** — the assignment asked for non-trivial SQL, and reporting aggregates are a natural fit
- **HTMX over React** — server-rendered HTML is simpler, fewer moving parts, no build step

If someone asked me to explain any line in this codebase, I could — because I understood every decision before I wrote it. The AI just helped me write it faster.
