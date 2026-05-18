---
name: web_research
description: "Fetch a web URL, extract readable content, and produce a structured summary. Trigger when the user provides a URL to summarize or asks what a page says. For single-page extraction only."
allowed-tools: Read
tags:
  - web
  - research
  - fetch
  - summary
version: 0.1
risk_level: network
---

# When to use

- Use when the user provides a URL and asks for its content to be summarized.
- Use when the user asks "what does this page say" or "提取这个网页的内容".
- Use for single-page content extraction.

# Do NOT use

- Do not use for multi-source research or comparison across multiple pages.
- Do not use for editing or modifying web content.
- Do not use for pages that require authentication.

# Inputs

- A URL (required)
- Optional: specific questions about the page content

# Workflow

1. **Validate**: Check the URL is well-formed and allowed by domain policy.
2. **Fetch**: Call `web.fetch(url="<url>")` to get the page as readable text.
3. **Fallback**: If web.fetch returns empty or blocked, try `web.browse(url="<url>")` for JavaScript-rendered pages.
4. **Extract**: Identify the main content — skip navigation, ads, and boilerplate.
5. **Structure**: Build a summary with: title, source URL, key points (3-5 bullets), and relevant excerpts.
6. **Present**: Output the structured summary to the user.

# Decision Rules

- If web.fetch returns ok=False with "blocked", explain the domain policy to the user and stop.
- If web.fetch returns empty text, try web.browse before giving up.
- If the content exceeds 12000 chars, summarize the most relevant sections first.
- Prefer the original source text over your own paraphrasing for key claims.

# Safety Rules

- Respect domain policies — if blocked, do not attempt to circumvent.
- Do not fetch localhost, 127.0.0.1, or internal IPs.
- Do not include credentials or API keys found in page content.
- Do not execute any JavaScript from the page.

# Output Format

```
**Source**: [title](url)

**Key Points**:
- Point 1
- Point 2
- Point 3

**Summary**: 1-2 paragraph overview of the main content.
```

# Failure Handling

- If the URL is invalid, ask the user for a corrected URL.
- If web.fetch times out, suggest the user verify the site is accessible.
- If the page requires JavaScript, use web.browse as fallback.
- If both fail, report the error and suggest alternative URLs.

# Examples

- Trigger: "Summarize https://example.com/article"
- Trigger: "https://www.36kr.com/p/123 这个网页说了什么"
- Trigger: "What does this page say? https://..."
- Non-trigger: "Search the web for recent AI news"
- Non-trigger: "Browse multiple product pages and compare prices"
