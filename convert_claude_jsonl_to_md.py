import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

SRC = Path(sys.argv[1]).expanduser().resolve()
DST = Path(sys.argv[2]).expanduser().resolve()

# Home directory path to sanitize from output (replaces /Users/<username> with ~)
HOME_DIR = str(Path.home())

VOLATILE_KEYS = {
    "timestamp",
    "time",
    "updated_at",
    "created_at",
    "cwd",
    "transcript_path",
}

TIMESTAMP_KEYS = ("timestamp", "time", "created_at")

ID_KEYS = ("uuid", "id", "message_id", "request_id", "event_id")


def sanitize_home_paths(text: str) -> str:
    """Replace /Users/<username> or /home/<username> paths and dash-encoded
    equivalents with ~ to avoid exposing usernames in output."""
    # Replace runtime HOME path
    text = text.replace(HOME_DIR, "~")
    home_parts = HOME_DIR.strip("/").split("/")
    dash_form = "-" + "-".join(home_parts) + "-"
    text = text.replace(dash_form, "~")
    # Also catch common home path patterns that differ from runtime HOME
    # (e.g. when running inside Docker where HOME=/root but paths say /Users/...)
    text = re.sub(r"/(?:Users|home)/[a-zA-Z0-9._-]+", "~", text)
    text = re.sub(r"-(?:Users|home)-[a-zA-Z0-9._]+-", "~", text)
    return text


CLAUDE_INTERNAL_TAGS = [
    "system-reminder",
    "antml:thinking",
    "antml:function_calls",
    "antml:invoke",
    "antml:parameter",
    "antml:result",
    "user-prompt-submit-hook",
    "command-name",
    "functions",
    "function",
    "persisted-output",
]

# Build regex to strip all Claude internal XML tags and their content
_INTERNAL_TAG_PATTERN = re.compile(
    r"<(?:" + "|".join(re.escape(t) for t in CLAUDE_INTERNAL_TAGS) + r")(?:\s[^>]*)?>[\s\S]*?"
    r"</(?:" + "|".join(re.escape(t) for t in CLAUDE_INTERNAL_TAGS) + r")>",
)
# Also strip self-closing and orphan opening tags
_INTERNAL_TAG_OPEN = re.compile(
    r"<(?:" + "|".join(re.escape(t) for t in CLAUDE_INTERNAL_TAGS) + r")(?:\s[^>]*)?\s*/?>",
)


def neutralize_markers(text: str) -> str:
    """Neutralize structural markers embedded in body text (e.g. from tool results
    that displayed the markdown file itself) so they don't create false Cmd+F hits
    or pollute the ENTRY_KEY index."""
    # Neutralize the user-request search delimiter
    text = text.replace(">>>USER_REQUEST<<<", ">>>USER_REQUEST [quoted]<<<")
    # Neutralize ENTRY_KEY HTML comments so load_existing_keys ignores them
    text = re.sub(r"<!-- ENTRY_KEY:", "<!-- QUOTED_ENTRY_KEY:", text)
    # Strip Claude internal XML tags and their content
    text = _INTERNAL_TAG_PATTERN.sub("", text)
    text = _INTERNAL_TAG_OPEN.sub("", text)
    # Neutralize conversation headers so quoted file contents don't create false sections
    text = re.sub(r"^(## Conversation `)", r"## [Quoted] Conversation `", text, flags=re.MULTILINE)
    # Clean up excessive blank lines left by stripping
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text


def clean_project_name(name: str) -> str:
    """Convert path-based project names to readable form.
    e.g. '-Users-amrambouskila-IMPORTANT-Projects-oft' -> 'IMPORTANT-Projects-oft'

    Works both on the host and inside Docker by detecting the home prefix
    pattern from the name itself, not from the runtime HOME directory.
    """
    # Try runtime HOME first
    home_parts = HOME_DIR.strip("/").split("/")
    dash_prefix = "-" + "-".join(home_parts) + "-"
    if name.startswith(dash_prefix):
        return name[len(dash_prefix):]

    # Fallback: detect common patterns like -Users-<username>- or -home-<username>-
    # These are the standard home directory layouts on macOS and Linux
    m = re.match(r"^-(?:Users|home)-[^-]+-", name)
    if m:
        return name[m.end():]

    # Strip leading dash if that's all that's left
    if name.startswith("-"):
        return name.lstrip("-")

    return name


def extract_timestamp(rec):
    """Pull the best available timestamp from a record."""
    for key in TIMESTAMP_KEYS:
        val = rec.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    # Check nested message
    msg = rec.get("message")
    if isinstance(msg, dict):
        for key in TIMESTAMP_KEYS:
            val = msg.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def parse_timestamp(ts_str):
    """Parse a timestamp string into a datetime for sorting."""
    if not ts_str:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    return None


def render_tool_use(content_block):
    """Render a tool_use content block as a readable markdown section."""
    name = content_block.get("name", "unknown_tool")
    tool_input = content_block.get("input", {})
    parts = [f"**Tool Call: `{name}`**"]
    if tool_input:
        parts.append(f"```json\n{json.dumps(tool_input, ensure_ascii=False, indent=2)}\n```")
    return "\n".join(parts)


def render_tool_result(content_block):
    """Render a tool_result content block as a readable markdown section."""
    tool_use_id = content_block.get("tool_use_id", "")
    is_error = content_block.get("is_error", False)
    content = content_block.get("content", "")
    label = "Tool Error" if is_error else "Tool Result"
    parts = [f"**{label}** (id: `{tool_use_id}`)"]
    if isinstance(content, str) and content.strip():
        parts.append(f"```\n{content.strip()}\n```")
    elif isinstance(content, list):
        for item in content:
            t = textify(item).strip()
            if t:
                parts.append(t)
    return "\n".join(parts)


def textify(obj):
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, (int, float, bool)):
        return str(obj)

    if isinstance(obj, list):
        parts = []
        for x in obj:
            if isinstance(x, dict):
                block_type = x.get("type", "")
                if block_type == "tool_use":
                    parts.append(render_tool_use(x))
                    continue
                elif block_type == "tool_result":
                    parts.append(render_tool_result(x))
                    continue
                elif block_type == "thinking":
                    # Skip thinking blocks (signatures, internal reasoning)
                    continue
            parts.append(textify(x))
        return "\n\n".join(p for p in parts if p.strip())

    if isinstance(obj, dict):
        block_type = obj.get("type", "")
        if block_type == "tool_use":
            return render_tool_use(obj)
        if block_type == "tool_result":
            return render_tool_result(obj)

        preferred = [
            "text",
            "message",
            "content",
            "output_text",
            "input",
            "prompt",
            "assistant",
            "user",
            "result",
            "summary",
            "value",
        ]
        parts = []
        for k in preferred:
            if k in obj:
                t = textify(obj[k])
                if t.strip():
                    parts.append(t)

        if not parts:
            for k, v in obj.items():
                if k in VOLATILE_KEYS:
                    continue
                t = textify(v)
                if t.strip():
                    parts.append(t)

        seen = set()
        deduped = []
        for p in parts:
            if p not in seen:
                seen.add(p)
                deduped.append(p)
        return "\n".join(deduped).strip()

    return str(obj)


def guess_speaker(rec):
    for key in ("role", "speaker", "author"):
        val = rec.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().title()

    t = rec.get("type")
    if isinstance(t, str):
        tl = t.lower()
        if "user" in tl:
            return "User"
        if "assistant" in tl or "model" in tl:
            return "Assistant"
        if "tool" in tl:
            return "Tool"
        if "system" in tl:
            return "System"

    return "Entry"


def scrub_for_hash(obj):
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            if k in VOLATILE_KEYS:
                continue
            cleaned[k] = scrub_for_hash(v)
        return cleaned

    if isinstance(obj, list):
        return [scrub_for_hash(x) for x in obj]

    return obj


def stable_record_key(rec):
    for key in ID_KEYS:
        val = rec.get(key)
        if isinstance(val, str) and val.strip():
            return f"id:{key}:{val.strip()}"
        if isinstance(val, (int, float)):
            return f"id:{key}:{val}"

    canonical_obj = scrub_for_hash(rec)
    canonical_json = json.dumps(
        canonical_obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return f"hash:{digest}"


def raw_line_key(line):
    digest = hashlib.sha256(line.encode("utf-8")).hexdigest()
    return f"raw:{digest}"


def is_real_user_message(rec) -> bool:
    """Return True only for messages the user actually typed (not tool results)."""
    msg = rec.get("message", {})
    if not isinstance(msg, dict):
        return False
    if msg.get("role") != "user":
        return False
    content = msg.get("content", "")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return not any(
            isinstance(block, dict) and block.get("type") == "tool_result"
            for block in content
        )
    return False


def render_entry(entry_num: int, speaker: str, body: str, entry_key: str,
                 timestamp: str | None = None, real_user: bool = False,
                 conversation_id: str | None = None) -> str:
    ts_suffix = f" — {timestamp}" if timestamp else ""
    conv_suffix = f" — conv: `{conversation_id}`" if conversation_id else ""
    heading = "#" if real_user else "###"
    # Unique delimiter for real user messages — search for >>>USER_REQUEST<<< in Cmd+F
    user_delimiter = "\n>>>USER_REQUEST<<<\n" if real_user else ""
    return "\n".join(
        [
            "",
            f"<!-- ENTRY_KEY: {entry_key} -->",
            f"{user_delimiter}{heading} {speaker} #{entry_num}{ts_suffix}{conv_suffix}",
            "",
            body,
            "",
        ]
    )


def get_first_timestamp(jsonl_path: Path) -> datetime | None:
    """Get the earliest timestamp from a JSONL file for sorting conversations."""
    try:
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.rstrip("\n")
                if not raw.strip():
                    continue
                try:
                    rec = json.loads(raw)
                    ts = extract_timestamp(rec)
                    dt = parse_timestamp(ts)
                    if dt:
                        return dt
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return None


def parse_entries_from_file(path: Path, conversation_id: str) -> list[dict]:
    """Parse all entries from a single JSONL file, returning a list of entry dicts."""
    entries = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.rstrip("\n")
                if not raw.strip():
                    continue

                try:
                    rec = json.loads(raw)
                    entry_key = stable_record_key(rec)
                    speaker = guess_speaker(rec)
                    timestamp = extract_timestamp(rec)
                    real_user = is_real_user_message(rec)
                    if not real_user and speaker == "User":
                        speaker = "Tool Output"
                    body = neutralize_markers(sanitize_home_paths(textify(rec).strip()))
                    if not body:
                        body = neutralize_markers(sanitize_home_paths(json.dumps(rec, ensure_ascii=False, indent=2)))
                except json.JSONDecodeError:
                    entry_key = raw_line_key(raw)
                    speaker = "Entry"
                    timestamp = None
                    real_user = False
                    body = neutralize_markers(sanitize_home_paths(f"```text\n{raw}\n```"))

                entries.append({
                    "entry_key": entry_key,
                    "speaker": speaker,
                    "timestamp": timestamp,
                    "parsed_ts": parse_timestamp(timestamp),
                    "real_user": real_user,
                    "body": body,
                    "conversation_id": conversation_id,
                })

    except Exception as e:
        err = f"Conversion error: {e}"
        entry_key = f"error:{hashlib.sha256(err.encode('utf-8')).hexdigest()}"
        entries.append({
            "entry_key": entry_key,
            "speaker": "System",
            "timestamp": None,
            "parsed_ts": None,
            "real_user": False,
            "body": err,
            "conversation_id": conversation_id,
        })

    return entries


def load_existing_keys(out_path: Path) -> set[str]:
    """Load entry keys from the markdown file, skipping any that appear inside
    code blocks (which are quoted content, not real entries)."""
    keys = set()
    if not out_path.exists():
        return keys
    try:
        in_code_block = False
        for line in out_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue
            m = re.search(r"<!-- ENTRY_KEY: (.+?) -->", line)
            if m:
                keys.add(m.group(1))
    except Exception:
        pass
    return keys


def convert_project(project_dir: Path, project_name: str):
    """Convert all JSONL files in a project directory into a single markdown file,
    with conversations ordered chronologically."""
    jsonl_files = list(project_dir.glob("*.jsonl"))
    if not jsonl_files:
        return 0

    display_name = clean_project_name(project_name)
    out_path = DST / f"{display_name}.md"

    # Sort JSONL files by their first timestamp (chronological conversation order)
    file_timestamps = []
    for f in jsonl_files:
        first_ts = get_first_timestamp(f)
        file_timestamps.append((f, first_ts))
    file_timestamps.sort(key=lambda x: x[1] or datetime.min)

    # Load existing keys for incremental updates
    existing_keys = load_existing_keys(out_path)

    # Collect all entries, maintaining per-conversation order but sorting conversations by time
    all_entries = []
    for jsonl_file, _ in file_timestamps:
        conv_id = jsonl_file.stem
        entries = parse_entries_from_file(jsonl_file, conv_id)
        all_entries.extend(entries)

    # Filter out already-written entries
    new_entries = [e for e in all_entries if e["entry_key"] not in existing_keys]

    if not new_entries:
        return 0

    # Always do a full rewrite so that new entries (which may belong to
    # conversations that interleave chronologically with existing ones)
    # end up in the correct position.
    out_path.parent.mkdir(parents=True, exist_ok=True)

    header = [
        f"# {display_name}",
        "",
        f"All conversations from project `{display_name}`, ordered chronologically.",
        "",
        f"Total conversations: {len(jsonl_files)}",
        "",
        "---",
        "",
    ]

    blocks = []
    current_conv = None
    entry_counter = 0

    for entry in all_entries:
        # Add a conversation separator when switching to a new conversation
        if entry["conversation_id"] != current_conv:
            current_conv = entry["conversation_id"]
            first_ts = entry["timestamp"] or "unknown"
            blocks.append(f"\n---\n\n## Conversation `{current_conv}` (started {first_ts})\n")

        entry_counter += 1
        blocks.append(render_entry(
            entry_counter,
            entry["speaker"],
            entry["body"],
            entry["entry_key"],
            entry["timestamp"],
            real_user=entry["real_user"],
            conversation_id=entry["conversation_id"],
        ))

    content = "\n".join(header) + "\n".join(blocks)
    out_path.write_text(content, encoding="utf-8")

    return len(all_entries)


def main():
    if not SRC.exists():
        print(f"ERROR: Source directory not found: {SRC}", file=sys.stderr)
        sys.exit(1)

    # Discover projects: each subdirectory of SRC is a project
    project_dirs = sorted([d for d in SRC.iterdir() if d.is_dir()])
    if not project_dirs:
        print("ERROR: No project directories found.", file=sys.stderr)
        sys.exit(1)

    DST.mkdir(parents=True, exist_ok=True)

    total_entries = 0
    for i, project_dir in enumerate(project_dirs, 1):
        project_name = project_dir.name
        jsonl_count = len(list(project_dir.glob("*.jsonl")))
        count = convert_project(project_dir, project_name)
        total_entries += count
        status = f"{count} new entries" if count else "up to date"
        print(f"  [{i}/{len(project_dirs)}] {project_name} ({jsonl_count} conversations) — {status}")

    print(f"\nDone. Processed {len(project_dirs)} projects, wrote {total_entries} entries to {DST}")


if __name__ == "__main__":
    main()
