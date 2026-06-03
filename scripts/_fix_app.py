"""One-shot script: remove duplicate old-code block from streamlit_app.py."""
path = "frontend/streamlit_app.py"
lines = open(path, encoding="utf-8").readlines()

# Find ALL occurrences of the entry-point guard
guard = 'if __name__ == "__main__":\n'
indices = [i for i, l in enumerate(lines) if l == guard]
print(f"Entry-point guards at lines: {[i+1 for i in indices]}")

if len(indices) >= 2:
    # Keep only up to (and including) the first guard + its body line
    keep_until = indices[0] + 2   # +2 = guard line + "    main()" line
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines[:keep_until])
    print(f"Truncated: kept {keep_until} lines, removed {len(lines) - keep_until} lines.")
else:
    print("Only one guard found — nothing to do.")
