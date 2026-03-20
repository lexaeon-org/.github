#!/usr/bin/env python3
import anthropic
import os
import sys

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
PR_TITLE = os.environ.get("PR_TITLE", "")
PR_AUTHOR = os.environ.get("PR_AUTHOR", "")
REPO_NAME = os.environ.get("REPO_NAME", "")

with open("pr_diff.txt", "r") as f:
    diff = f.read()

# Truncate very large diffs to avoid token limits
MAX_DIFF_CHARS = 80_000
if len(diff) > MAX_DIFF_CHARS:
    diff = diff[:MAX_DIFF_CHARS] + "\n\n[diff truncated — review remaining changes manually]"

REVIEW_PROMPT = f"""You are a senior engineer reviewing a pull request for security, performance, and code quality issues.

Repository: {REPO_NAME}
PR Title: {PR_TITLE}
Author: {PR_AUTHOR}

## What to look for

### Security (highest priority)
- New API routes or endpoints missing authentication checks (getUser, requireOrgRole, requireAdmin)
- Database queries missing organization_id filter — any query that could return data across org boundaries
- RLS bypassed via service role client without manual org filter applied in application code
- Caller-supplied org_id used directly without server-side verification from the session
- New tables or columns missing RLS policies
- Raw SQL with string interpolation (SQL injection risk)
- Secrets, API keys, or credentials hardcoded in code
- Edge functions or cron jobs with no or weak auth

### Performance
- Sequential awaits that could be parallelized with Promise.all() or asyncio.gather()
- N+1 query patterns — queries inside loops
- External API calls (Anthropic, Stripe, Apollo, etc.) missing AbortSignal.timeout() or equivalent
- select('*') on large tables where only a few columns are needed
- Missing database indexes on frequently filtered columns

### Code quality
- TypeScript `any` types that bypass type safety
- Disabled eslint or typescript rules (// @ts-ignore, // eslint-disable)
- New Alembic migrations that use raw SQL instead of ORM operations
- Direct SQL run against Supabase outside of Alembic migrations
- Error handlers that expose stack traces or internal error messages to clients

## Output format

Respond in this exact markdown format:

---
## Claude PR Review

**Repository:** {REPO_NAME}
**PR:** {PR_TITLE}

### 🔴 Critical
<!-- List critical security or data integrity issues. If none, write: _None found_ -->

### 🟠 High
<!-- List high severity performance or security issues. If none, write: _None found_ -->

### 🟡 Medium
<!-- List medium severity issues. If none, write: _None found_ -->

### ✅ Looks good
<!-- List areas you checked that look clean -->

---
**Tip:** Critical and High issues should be resolved before merging.
---

For each finding use this format:
- `path/to/file.ts:LINE` — Brief description of the issue and why it matters

If the diff is empty or only contains documentation/config changes with no security or performance implications, say so clearly and mark everything as clean.
"""

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

message = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=2000,
    messages=[
        {
            "role": "user",
            "content": f"{REVIEW_PROMPT}\n\n## PR Diff\n\n```diff\n{diff}\n```"
        }
    ]
)

review = message.content[0].text

# Write the review comment
with open("review_comment.md", "w") as f:
    f.write(review)

# Check if criticals were found
has_criticals = "🔴 Critical" in review and "_None found_" not in review.split("🔴 Critical")[1].split("###")[0]

# Export for the workflow
with open(os.environ["GITHUB_ENV"], "a") as f:
    f.write(f"HAS_CRITICALS={'true' if has_criticals else 'false'}\n")

print(f"Review complete. Criticals found: {has_criticals}")
print(review)