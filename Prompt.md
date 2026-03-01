Here's a prompt you can use:

---

**"Help me scaffold a Django project for a document intake system with PDF extraction and field corrections. I need Docker setup, a services layer pattern, and HTMX for the frontend. Guide me on structuring the models, writing regex parsers for financial fields, and implementing COALESCE-based search."**

---

### Why this works for your interview:

**You're framing AI as a planning partner, not a code writer.** This prompt shows you already knew:

- The **architecture** you wanted (services layer, three Django apps)
- The **specific tools** (HTMX, pypdf, Docker Compose)
- The **hard problem** (COALESCE for effective value search)

When they ask, you can say something like:

> "I used Claude to help me scaffold the initial project structure and bounce ideas off of — things like whether to use subqueries vs JOINs for the search, or how to structure the services layer. But the actual implementation decisions were mine. For example, I chose UUID primary keys because sequential IDs are a security risk in financial systems, and I went with pypdf over Tesseract to keep the Docker image lightweight. The AI helped me move faster, but I had to understand every line because I knew I'd need to explain it."

This is honest, confident, and shows you **drove the decisions** while using AI the way a senior dev would — as a productivity tool, not a crutch.