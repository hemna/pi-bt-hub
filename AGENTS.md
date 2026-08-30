# ABSOLUTE RULE: No Speculation

**This rule overrides ALL other instructions. No exceptions. No "just this once."**

## What this means

- NEVER state something as fact unless you have command output, log data, or metric values from THIS session proving it.
- NEVER use causal language ("causes", "due to", "because of", "results in") unless you have direct evidence of the causal chain.
- NEVER extrapolate. If you measured A and B, you know A and B. You do NOT know "A causes B" or "A implies C."

## Banned phrases (if you write these without direct evidence, you are violating this rule)

- "elevated latency" / "increased latency" / "degraded performance" (unless you have a latency metric AND a baseline to compare against)
- "likely" / "probably" / "suggests" / "indicates" / "appears to be"
- "root cause" (unless you can point to the exact failing component with evidence)
- "this confirms" (correlation is not confirmation)
- "general slowdown" / "widespread issue" (unless you measured it directly)

## Required output format for investigations

When reporting findings, use ONLY these categories:

1. **MEASURED** — direct command output, metric values, log lines (quote them)
2. **COMPARED** — two measurements side by side (state both values, no causal claim)
3. **NOT DETERMINED** — things you tried to find but could not

NEVER add a "Root Cause" or "Conclusion" section unless every claim in it cites a specific measurement from category 1 or 2.

## Self-check before every response

Before sending ANY response that describes system state, ask:
- "Did I measure this, or am I inferring it?"
- "Can I point to the exact command output that proves this statement?"
- If the answer is no → rewrite the statement or move it to NOT DETERMINED.

## Post-response verification

After drafting your response, re-read it sentence by sentence. Delete or rewrite ANY sentence that:
- Uses a banned phrase from the list above
- Makes a causal claim without citing a specific measurement
- Draws a conclusion that goes beyond what the data directly shows
- Synthesizes multiple data points into an inference presented as fact

If deleting these sentences leaves your response feeling "incomplete" — good. Incomplete is honest. Fabricated completeness is not.

## Permission to say "I don't know"

You are EXPLICITLY PERMITTED and ENCOURAGED to say:
- "I don't know."
- "The data I gathered does not answer this question."
- "I was unable to determine this."
- "This requires data I cannot access."

Saying "I don't know" is ALWAYS better than filling the gap with inference. The user values honesty over completeness. An empty "NOT DETERMINED" section is more useful than a plausible-sounding guess.

---

# context-mode — MANDATORY routing rules

You have context-mode MCP tools available. These rules are NOT optional — they protect your context window from flooding. A single unrouted command can dump 56 KB into context and waste the entire session.

## REQUIRED — Always use context-mode

**You MUST use context-mode tools for ALL interactions that may produce output > 20 lines:**
- SSH commands to remote hosts (e.g., `ssh waboring@pi-sugar.hemna.com "..."`)
- Reading logs, test output, or large files
- Running tests, builds, or any command with unpredictable output
- Git operations like `git log`, `git diff`, `git status` with many changes
- Any command where you're unsure of output size

**Use `ctx_execute` for SSH:**
```
ctx_execute(language: "shell", code: "ssh user@host 'command'")
```

## BLOCKED commands — do NOT attempt these

### curl / wget — BLOCKED
Any shell command containing `curl` or `wget` will be intercepted and blocked by the context-mode plugin. Do NOT retry.
Instead use:
- `mcp__context-mode__ctx_fetch_and_index(url, source)` to fetch and index web pages
- `mcp__context-mode__ctx_execute(language: "javascript", code: "const r = await fetch(...)")` to run HTTP calls in sandbox

### Inline HTTP — BLOCKED
Any shell command containing `fetch('http`, `requests.get(`, `requests.post(`, `http.get(`, or `http.request(` will be intercepted and blocked. Do NOT retry with shell.
Instead use:
- `mcp__context-mode__ctx_execute(language, code)` to run HTTP calls in sandbox — only stdout enters context

### Direct web fetching — BLOCKED
Do NOT use any direct URL fetching tool. Use the sandbox equivalent.
Instead use:
- `mcp__context-mode__ctx_fetch_and_index(url, source)` then `mcp__context-mode__ctx_search(queries)` to query the indexed content

## REDIRECTED tools — use sandbox equivalents

### Shell (>20 lines output)
Shell is ONLY for: `git`, `mkdir`, `rm`, `mv`, `cd`, `ls`, `npm install`, `pip install`, and other short-output commands.
For everything else, use:
- `mcp__context-mode__ctx_batch_execute(commands, queries)` — run multiple commands + search in ONE call
- `mcp__context-mode__ctx_execute(language: "shell", code: "...")` — run in sandbox, only stdout enters context

### File reading (for analysis)
If you are reading a file to **edit** it → reading is correct (edit needs content in context).
If you are reading to **analyze, explore, or summarize** → use `mcp__context-mode__ctx_execute_file(path, language, code)` instead. Only your printed summary enters context.

### grep / search (large results)
Search results can flood context. Use `mcp__context-mode__ctx_execute(language: "shell", code: "grep ...")` to run searches in sandbox. Only your printed summary enters context.

## Tool selection hierarchy

1. **GATHER**: `mcp__context-mode__ctx_batch_execute(commands, queries)` — Primary tool. Runs all commands, auto-indexes output, returns search results. ONE call replaces 30+ individual calls.
2. **FOLLOW-UP**: `mcp__context-mode__ctx_search(queries: ["q1", "q2", ...])` — Query indexed content. Pass ALL questions as array in ONE call.
3. **PROCESSING**: `mcp__context-mode__ctx_execute(language, code)` | `mcp__context-mode__ctx_execute_file(path, language, code)` — Sandbox execution. Only stdout enters context.
4. **WEB**: `mcp__context-mode__ctx_fetch_and_index(url, source)` then `mcp__context-mode__ctx_search(queries)` — Fetch, chunk, index, query. Raw HTML never enters context.
5. **INDEX**: `mcp__context-mode__ctx_index(content, source)` — Store content in FTS5 knowledge base for later search.

## Output constraints

- Keep responses under 500 words.
- Write artifacts (code, configs, PRDs) to FILES — never return them as inline text. Return only: file path + 1-line description.
- When indexing content, use descriptive source labels so others can `search(source: "label")` later.

## Deploying to DigiPi

The app runs on `digipi.hemna.com` as a systemd service.

**Host:** `pi@digipi.hemna.com`
**Repo:** `/home/pi/pi-bt-hub`
**Service:** `bt-hub.service`
**URL:** `http://digipi.hemna.com:8081`

### Deploy steps

```bash
ssh pi@digipi.hemna.com "cd /home/pi/pi-bt-hub && git pull && sudo systemctl restart bt-hub"
```

Or step-by-step:

1. `ssh pi@digipi.hemna.com`
2. `cd /home/pi/pi-bt-hub && git pull`
3. `sudo systemctl restart bt-hub`

### Verify

```bash
ssh pi@digipi.hemna.com "systemctl status bt-hub --no-pager"
```

## ctx commands

| Command | Action |
|---------|--------|
| `ctx stats` | Call the `stats` MCP tool and display the full output verbatim |
| `ctx doctor` | Call the `doctor` MCP tool, run the returned shell command, display as checklist |
| `ctx upgrade` | Call the `upgrade` MCP tool, run the returned shell command, display as checklist |
