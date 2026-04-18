def get_inline_text(value):
    if isinstance(value, str):
        return value
    return render_inline(value or [])


def render_inline(inlines):

    if not inlines:
        return ""

    parts = []

    for inline in inlines:

        t = inline.type

        # ------------------------
        # TEXT
        # ------------------------
        if t == "text":
            parts.append(inline.text)

        # ------------------------
        # CODE
        # ------------------------
        elif t == "code":
            inner = render_inline(inline.children or [])
            parts.append(f"`{inner}`")

        # ------------------------
        # LINK
        # ------------------------
        elif t == "link":
            label = render_inline(inline.children or [])
            parts.append(f"{label} ({inline.href})")

        # ------------------------
        # CMD
        # ------------------------
        elif t == "cmd":
            label = render_inline(inline.children or [])
            parts.append(f"{label}")

        # ------------------------
        # STRONG
        # ------------------------
        elif t == "strong":
            inner = render_inline(inline.children or [])
            parts.append(f"*{inner}*")

        # ------------------------
        # EM
        # ------------------------
        elif t == "em":
            inner = render_inline(inline.children or [])
            parts.append(f"_{inner}_")

        # ------------------------
        # UNDERLINE
        # ------------------------
        elif t == "underline":
            inner = render_inline(inline.children or [])
            parts.append(inner)  # Terminal kann kein echtes underline

        # ------------------------
        # MARK
        # ------------------------
        elif t == "mark":
            inner = render_inline(inline.children or [])
            variant = inline.variant or ""

            if variant == "important":
                parts.append(f"[!] {inner}")
            elif variant == "error":
                parts.append(f"[ERROR] {inner}")
            elif variant == "success":
                parts.append(f"[OK] {inner}")
            else:
                parts.append(inner)

        # ------------------------
        # SELECT
        # ------------------------
        elif t == "select":
            inner = render_inline(inline.children or [])
            parts.append(inner)

        # ------------------------
        # BREAK
        # ------------------------
        elif t == "break":
            parts.append("\n")

        # ------------------------
        # FALLBACK
        # ------------------------
        else:
            parts.append(f"[{t}]")

    return "".join(parts)
