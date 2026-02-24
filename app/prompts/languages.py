"""Language-specific review hints appended to the system prompt.

Each entry maps a file extension (or set of extensions) to extra review
guidance that steers the AI toward language-idiomatic issues.
"""

from __future__ import annotations

# Extension → (language label, extra review instructions)
LANGUAGE_HINTS: dict[str, tuple[str, str]] = {
    # Python
    ".py": ("Python", """
## Python-Specific Review Focus
- Check for **type hint** correctness (missing annotations on public APIs, `Optional` vs `X | None`).
- Flag mutable default arguments (`def f(items=[])`).
- Look for bare `except:` or overly broad `except Exception`.
- Verify `async`/`await` consistency — blocking calls inside async functions.
- Check for f-string vs `.format()` inconsistencies, unreachable code after `return`/`raise`.
- Watch for missing `__init__.py`, circular imports, and incorrect relative imports.
- Flag deprecated stdlib usage (e.g., `datetime.utcnow()`).
"""),

    # JavaScript
    ".js": ("JavaScript", """
## JavaScript-Specific Review Focus
- Flag `var` usage — prefer `const`/`let`.
- Check for `==` vs `===` (loose equality bugs).
- Look for missing `await` on async calls and unhandled Promise rejections.
- Watch for prototype pollution, `eval()`, and `innerHTML` (XSS vectors).
- Check error handling in `.catch()` chains and `try/catch` blocks.
- Flag unused variables and imports.
"""),

    # TypeScript
    ".ts": ("TypeScript", """
## TypeScript-Specific Review Focus
- Flag `any` type usage — suggest specific types or generics.
- Check for `as` type assertions that bypass type safety.
- Look for missing `await` on async calls and unhandled Promise rejections.
- Verify interface/type definitions match actual usage.
- Watch for `!` non-null assertions hiding real null checks.
- Check enum usage and recommend `as const` objects where appropriate.
"""),

    ".tsx": ("TypeScript/React", """
## TypeScript + React-Specific Review Focus
- Flag `any` type usage in props and state.
- Check `useEffect` dependency arrays for missing or extra dependencies.
- Look for inline function/object creation in JSX causing unnecessary re-renders.
- Verify `key` prop usage in lists (no index-as-key for dynamic lists).
- Watch for direct DOM manipulation instead of React state updates.
- Check for missing error boundaries around async operations.
"""),

    ".jsx": ("JavaScript/React", """
## React-Specific Review Focus
- Check `useEffect` dependency arrays for missing or extra dependencies.
- Look for inline function/object creation in JSX causing unnecessary re-renders.
- Verify `key` prop usage in lists (no index-as-key for dynamic lists).
- Watch for direct DOM manipulation instead of React state updates.
- Flag prop drilling — suggest Context or composition patterns.
"""),

    # Go
    ".go": ("Go", """
## Go-Specific Review Focus
- Check that **every error is handled** — no ignored `err` returns.
- Look for goroutine leaks (goroutines without cancellation or timeout).
- Verify proper `defer` usage for resource cleanup (files, mutexes, connections).
- Watch for data races — shared state without mutex or channel synchronization.
- Check for unnecessary pointer usage and excessive heap allocations.
- Flag missing context propagation (`context.Context` should flow through call chains).
"""),

    # Rust
    ".rs": ("Rust", """
## Rust-Specific Review Focus
- Check for unnecessary `.unwrap()` / `.expect()` — suggest `?` operator or proper error handling.
- Look for unnecessary `.clone()` calls that hurt performance.
- Verify lifetime annotations are correct and minimal.
- Watch for potential deadlocks with `Mutex`/`RwLock`.
- Check `unsafe` blocks — ensure they are justified and sound.
- Flag missing `#[derive]` traits where useful (Debug, Clone, PartialEq).
"""),

    # Java
    ".java": ("Java", """
## Java-Specific Review Focus
- Check for null pointer risks — suggest `Optional<T>` or `@Nullable`/`@NonNull`.
- Look for resource leaks — verify try-with-resources for I/O and connections.
- Watch for mutable state in shared objects without synchronization.
- Flag raw types (e.g., `List` instead of `List<String>`).
- Check exception handling — avoid catching `Exception` or `Throwable` generically.
- Look for missing `@Override` annotations and incorrect `equals`/`hashCode`.
"""),

    # C / C++
    ".c": ("C", """
## C-Specific Review Focus
- Check for buffer overflows, out-of-bounds access, and off-by-one errors.
- Look for memory leaks — every `malloc`/`calloc` should have a matching `free`.
- Verify null pointer checks before dereference.
- Watch for undefined behavior (signed overflow, use-after-free, dangling pointers).
- Flag usage of unsafe functions (`gets`, `strcpy`, `sprintf`) — suggest safe alternatives.
"""),

    ".cpp": ("C++", """
## C++-Specific Review Focus
- Check for memory management issues — prefer smart pointers over raw `new`/`delete`.
- Look for missing virtual destructors in polymorphic base classes.
- Watch for dangling references and use-after-move.
- Verify RAII patterns for resource management.
- Flag C-style casts — prefer `static_cast`, `dynamic_cast`, etc.
- Check for exception safety (strong/basic guarantees).
"""),

    # Ruby
    ".rb": ("Ruby", """
## Ruby-Specific Review Focus
- Check for N+1 query patterns in ActiveRecord (missing `includes`/`preload`).
- Look for SQL injection via string interpolation in queries.
- Watch for thread-safety issues with mutable class variables.
- Flag `eval` and `send` with user-controlled input.
- Check for proper exception handling (rescue specific errors, not `StandardError`).
"""),

    # PHP
    ".php": ("PHP", """
## PHP-Specific Review Focus
- Check for SQL injection — verify parameterized queries / prepared statements.
- Look for XSS via unescaped output — use `htmlspecialchars()` or template escaping.
- Watch for type juggling bugs (loose comparisons with `==`).
- Flag deprecated functions and PHP version compatibility issues.
- Check for proper input validation and sanitization.
"""),

    # Shell
    ".sh": ("Shell/Bash", """
## Shell Script Review Focus
- Check for **unquoted variables** (`$var` vs `"$var"`) — word splitting bugs.
- Look for command injection via unsanitized input in commands.
- Verify `set -euo pipefail` or equivalent error handling at the top.
- Watch for POSIX compatibility issues if the script should be portable.
- Flag `eval` usage and backtick command substitution (prefer `$()`).
"""),

    ".bash": ("Bash", """
## Shell Script Review Focus
- Check for unquoted variables and word splitting bugs.
- Look for command injection via unsanitized input.
- Verify error handling with `set -euo pipefail`.
- Flag `eval` usage and backtick command substitution.
"""),

    # Kotlin
    ".kt": ("Kotlin", """
## Kotlin-Specific Review Focus
- Check for nullable type handling — verify safe calls (`?.`) and avoid `!!`.
- Look for coroutine scope leaks and missing cancellation handling.
- Watch for Java interop issues (platform types, nullable annotations).
- Verify `data class` usage where appropriate (equals/hashCode/copy).
- Flag blocking calls inside coroutine scope.
"""),

    # Swift
    ".swift": ("Swift", """
## Swift-Specific Review Focus
- Check for force unwrapping (`!`) — suggest `if let`/`guard let` instead.
- Look for retain cycles in closures — verify `[weak self]` usage.
- Watch for thread safety with shared mutable state.
- Verify proper error handling with `do`/`try`/`catch`.
- Flag `Any` type usage — suggest specific protocols or generics.
"""),

    # SQL
    ".sql": ("SQL", """
## SQL-Specific Review Focus
- Check for SQL injection risks in dynamic queries.
- Look for missing indexes on columns used in WHERE/JOIN clauses.
- Watch for N+1 query patterns and suggest batch operations.
- Verify transactions wrap related operations correctly.
- Flag SELECT * usage — suggest explicit column lists.
"""),

    # YAML / Config
    ".yaml": ("YAML", """
## YAML/Config Review Focus
- Check for hardcoded secrets or credentials.
- Verify correct indentation (YAML is indentation-sensitive).
- Look for insecure defaults (debug mode enabled, permissive CORS, etc.).
"""),

    ".yml": ("YAML", """
## YAML/Config Review Focus
- Check for hardcoded secrets or credentials.
- Verify correct indentation.
- Look for insecure defaults.
"""),
}

# Map additional extensions to the same hints
_ALIASES = {
    ".mjs": ".js",
    ".cjs": ".js",
    ".mts": ".ts",
    ".cts": ".ts",
    ".h": ".c",
    ".hpp": ".cpp",
    ".cc": ".cpp",
    ".cxx": ".cpp",
    ".kts": ".kt",
    ".pyw": ".py",
}

for _alias, _target in _ALIASES.items():
    if _target in LANGUAGE_HINTS:
        LANGUAGE_HINTS[_alias] = LANGUAGE_HINTS[_target]


def get_language_hints(file_extensions: set[str]) -> str:
    """Build a combined language-hint block for a set of file extensions.

    Args:
        file_extensions: Set of file extensions (e.g., {".py", ".ts"}).

    Returns:
        Concatenated hint string to append to the system prompt,
        or empty string if no hints apply.
    """
    seen_labels: set[str] = set()
    parts: list[str] = []

    for ext in sorted(file_extensions):
        entry = LANGUAGE_HINTS.get(ext)
        if entry and entry[0] not in seen_labels:
            seen_labels.add(entry[0])
            parts.append(entry[1].strip())

    return "\n\n".join(parts)
