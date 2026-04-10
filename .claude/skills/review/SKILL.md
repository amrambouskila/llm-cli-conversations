---
name: review
description: Review recent changes against DESIGN.md and CLAUDE.md for alignment
---

Review the current uncommitted or recently committed changes for quality and alignment with the project direction.

1. Read DESIGN.md and CLAUDE.md to understand the project constraints and anti-patterns.
2. Look at the current diff (staged + unstaged changes).
3. Check each change against:
   - Does it match the product thesis (search engine + dashboard, not conversation museum)?
   - Does it violate any anti-patterns listed in CLAUDE.md?
   - Does it introduce unnecessary complexity or feature bloat per DESIGN.md §7?
   - Is the code consistent with the conventions in CLAUDE.md?
4. Report findings concisely: what looks good, what needs attention, what should be reconsidered.