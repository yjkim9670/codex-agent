"""Tkinter desktop application for session-based Gemini/DTGPT chat."""

from __future__ import annotations

import queue
import re
import threading
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from tkinter import messagebox, simpledialog, ttk

from .chat_service import ChatService
from .config import MAX_PROMPT_CHARS, MAX_TITLE_CHARS

_ROLE_LABELS = {
    "user": "You",
    "assistant": "Assistant",
    "system": "System",
    "error": "Error",
}

_UI_COLORS = {
    "bg": "#edf1f7",
    "surface": "#ffffff",
    "surface_alt": "#f5f8fc",
    "surface_muted": "#e8eef7",
    "text": "#0f172a",
    "muted": "#5b6b83",
    "border": "#d4dde8",
    "primary": "#0f766e",
    "primary_hover": "#0d625c",
    "success": "#0f766e",
    "user_bubble": "#dbeafe",
    "assistant_bubble": "#ecfeff",
    "system_bubble": "#fff7ed",
    "error_bubble": "#fee2e2",
    "error_text": "#7f1d1d",
    "quote_bar": "#94a3b8",
    "code_bg": "#0b1220",
    "code_border": "#334155",
    "code_text": "#e2e8f0",
    "code_meta": "#93c5fd",
}

_FENCE_PATTERN = re.compile(r"^\s*```\s*([A-Za-z0-9_+\-\.#]*)\s*$")
_UNORDERED_LIST_PATTERN = re.compile(r"^\s*[-*+]\s+")
_ORDERED_LIST_PATTERN = re.compile(r"^\s*(\d+)\.\s+")


def _format_timestamp(value: str | None) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(str(value))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


def _normalize_text(value: str | None) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")


def _select_ui_font(root: tk.Misc) -> str:
    preferred = (
        "Malgun Gothic",
        "Apple SD Gothic Neo",
        "Noto Sans CJK KR",
        "Noto Sans KR",
        "NanumGothic",
        "Segoe UI",
        "Arial",
    )
    available = set(tkfont.families(root))
    for family in preferred:
        if family in available:
            return family
    return "TkDefaultFont"


def _select_mono_font(root: tk.Misc) -> str:
    preferred = (
        "Cascadia Code",
        "JetBrains Mono",
        "D2Coding",
        "Consolas",
        "Menlo",
        "Monaco",
        "Courier New",
        "Liberation Mono",
        "DejaVu Sans Mono",
    )
    available = set(tkfont.families(root))
    for family in preferred:
        if family in available:
            return family
    return "TkFixedFont"


def _split_markdown_sections(text: str) -> list[tuple[str, str, str]]:
    normalized = _normalize_text(text)
    lines = normalized.split("\n")

    sections: list[tuple[str, str, str]] = []
    markdown_lines: list[str] = []
    code_lines: list[str] = []
    code_lang = ""
    in_code = False

    for line in lines:
        match = _FENCE_PATTERN.match(line)
        if match:
            if in_code:
                sections.append(("code", code_lang, "\n".join(code_lines)))
                code_lines = []
                code_lang = ""
                in_code = False
            else:
                if markdown_lines:
                    sections.append(("markdown", "", "\n".join(markdown_lines)))
                    markdown_lines = []
                code_lang = str(match.group(1) or "").strip()
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
        else:
            markdown_lines.append(line)

    if in_code:
        sections.append(("code", code_lang, "\n".join(code_lines)))
    if markdown_lines:
        sections.append(("markdown", "", "\n".join(markdown_lines)))

    if not sections:
        sections.append(("markdown", "", ""))
    return sections


class DtgptAgentApp:
    """Main Tkinter UI controller."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.service = ChatService()

        self.sessions: list[dict] = []
        self._session_ids: list[str] = []
        self.current_session_id: str | None = None
        self._is_busy = False

        self._event_queue: queue.Queue = queue.Queue()
        self._chat_layout_after_id: str | None = None
        self._bubble_max_width_px = 760

        self.provider_var = tk.StringVar(value="")
        self.model_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Ready")
        self.session_title_var = tk.StringVar(value="No session selected")

        self.ui_font_family = _select_ui_font(root)
        self.mono_font_family = _select_mono_font(root)

        self.root.title("DTGPT Agent")
        self.root.geometry("1260x820")
        self.root.minsize(980, 620)
        self.root.configure(bg=_UI_COLORS["bg"])

        # Enable IME path where supported so Korean input works reliably.
        try:
            self.root.tk.call("tk", "useinputmethods", True)
        except tk.TclError:
            pass

        self._configure_styles()
        self._build_ui()
        self._load_initial_data()
        self._poll_worker_events()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.root.option_add("*Font", f"{{{self.ui_font_family}}} 10")

        style.configure("App.TFrame", background=_UI_COLORS["bg"])
        style.configure("Card.TFrame", background=_UI_COLORS["surface"], relief="flat", borderwidth=1)

        style.configure(
            "AppTitle.TLabel",
            background=_UI_COLORS["bg"],
            foreground=_UI_COLORS["text"],
            font=(self.ui_font_family, 20, "bold"),
        )
        style.configure(
            "AppSubtitle.TLabel",
            background=_UI_COLORS["bg"],
            foreground=_UI_COLORS["muted"],
            font=(self.ui_font_family, 10),
        )
        style.configure(
            "SectionTitle.TLabel",
            background=_UI_COLORS["surface"],
            foreground=_UI_COLORS["text"],
            font=(self.ui_font_family, 12, "bold"),
        )
        style.configure(
            "SectionMeta.TLabel",
            background=_UI_COLORS["surface"],
            foreground=_UI_COLORS["muted"],
            font=(self.ui_font_family, 9),
        )
        style.configure(
            "FieldLabel.TLabel",
            background=_UI_COLORS["surface"],
            foreground=_UI_COLORS["muted"],
            font=(self.ui_font_family, 9, "bold"),
        )
        style.configure(
            "Status.TLabel",
            background=_UI_COLORS["surface"],
            foreground=_UI_COLORS["success"],
            font=(self.ui_font_family, 9, "bold"),
        )
        style.configure(
            "ChatTitle.TLabel",
            background=_UI_COLORS["surface"],
            foreground=_UI_COLORS["text"],
            font=(self.ui_font_family, 12, "bold"),
        )

        style.configure(
            "Primary.TButton",
            background=_UI_COLORS["primary"],
            foreground="#ffffff",
            padding=(12, 8),
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "Primary.TButton",
            background=[("active", _UI_COLORS["primary_hover"]), ("disabled", "#93a4b6")],
            foreground=[("disabled", "#e2e8f0")],
        )

        style.configure(
            "Ghost.TButton",
            background=_UI_COLORS["surface_muted"],
            foreground=_UI_COLORS["text"],
            padding=(10, 7),
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "Ghost.TButton",
            background=[("active", "#d9e3f0"), ("disabled", "#eef2f7")],
            foreground=[("disabled", "#9aa8ba")],
        )

        style.configure(
            "Copy.TButton",
            padding=(10, 4),
            borderwidth=0,
            focusthickness=0,
            background=_UI_COLORS["surface_muted"],
            foreground=_UI_COLORS["text"],
            font=(self.ui_font_family, 10, "bold"),
        )
        style.map(
            "Copy.TButton",
            background=[("active", "#d9e3f0"), ("disabled", "#eef2f7")],
            foreground=[("disabled", "#9aa8ba")],
        )

        style.configure(
            "Modern.TCombobox",
            fieldbackground=_UI_COLORS["surface_alt"],
            background=_UI_COLORS["surface_alt"],
            foreground=_UI_COLORS["text"],
            bordercolor=_UI_COLORS["border"],
            lightcolor=_UI_COLORS["border"],
            darkcolor=_UI_COLORS["border"],
            arrowcolor=_UI_COLORS["text"],
            padding=5,
        )
        style.map(
            "Modern.TCombobox",
            fieldbackground=[("readonly", _UI_COLORS["surface_alt"]), ("disabled", "#eef2f7")],
            foreground=[("disabled", "#9aa8ba")],
        )

    def _build_ui(self) -> None:
        self.root.rowconfigure(2, weight=1)
        self.root.columnconfigure(0, weight=1)

        header = ttk.Frame(self.root, style="App.TFrame", padding=(18, 14, 18, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="DTGPT Workspace", style="AppTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Session chat with provider/model switching in a modern desktop shell",
            style="AppSubtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        control_card = ttk.Frame(self.root, style="Card.TFrame", padding=(16, 12))
        control_card.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))
        control_card.columnconfigure(5, weight=1)

        ttk.Label(control_card, text="Provider", style="FieldLabel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.provider_combo = ttk.Combobox(
            control_card,
            textvariable=self.provider_var,
            state="readonly",
            width=16,
            style="Modern.TCombobox",
        )
        self.provider_combo.grid(row=0, column=1, sticky="w", padx=(0, 14))
        self.provider_combo.bind("<<ComboboxSelected>>", self._on_provider_changed)

        ttk.Label(control_card, text="Model", style="FieldLabel.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.model_combo = ttk.Combobox(
            control_card,
            textvariable=self.model_var,
            state="readonly",
            width=34,
            style="Modern.TCombobox",
        )
        self.model_combo.grid(row=0, column=3, sticky="w", padx=(0, 12))

        self.apply_settings_button = ttk.Button(
            control_card,
            text="Apply",
            command=self._apply_settings,
            style="Primary.TButton",
        )
        self.apply_settings_button.grid(row=0, column=4, sticky="w")

        self.status_label = ttk.Label(control_card, textvariable=self.status_var, style="Status.TLabel", anchor="e")
        self.status_label.grid(row=0, column=5, sticky="ew")

        body = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        body.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))

        left_card = ttk.Frame(body, style="Card.TFrame", padding=(12, 12, 12, 12))
        left_card.columnconfigure(0, weight=1)
        left_card.rowconfigure(2, weight=1)
        body.add(left_card, weight=1)

        ttk.Label(left_card, text="Conversations", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            left_card,
            text="Create, rename, or remove sessions.",
            style="SectionMeta.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 8))

        session_list_wrap = ttk.Frame(left_card, style="Card.TFrame")
        session_list_wrap.grid(row=2, column=0, sticky="nsew")
        session_list_wrap.rowconfigure(0, weight=1)
        session_list_wrap.columnconfigure(0, weight=1)

        self.session_listbox = tk.Listbox(
            session_list_wrap,
            exportselection=False,
            activestyle="none",
            borderwidth=0,
            relief="flat",
            highlightthickness=1,
            highlightbackground=_UI_COLORS["border"],
            highlightcolor=_UI_COLORS["primary"],
            background=_UI_COLORS["surface_alt"],
            foreground=_UI_COLORS["text"],
            selectbackground=_UI_COLORS["primary"],
            selectforeground="#ffffff",
            font=(self.ui_font_family, 10),
        )
        self.session_listbox.grid(row=0, column=0, sticky="nsew")
        self.session_listbox.bind("<<ListboxSelect>>", self._on_session_selected)

        session_scroll = ttk.Scrollbar(session_list_wrap, orient="vertical", command=self.session_listbox.yview)
        session_scroll.grid(row=0, column=1, sticky="ns")
        self.session_listbox.configure(yscrollcommand=session_scroll.set)

        session_button_row = ttk.Frame(left_card, style="Card.TFrame")
        session_button_row.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        session_button_row.columnconfigure((0, 1, 2), weight=1)

        self.new_session_button = ttk.Button(session_button_row, text="New", command=self._create_session, style="Ghost.TButton")
        self.new_session_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.rename_session_button = ttk.Button(
            session_button_row,
            text="Rename",
            command=self._rename_session,
            style="Ghost.TButton",
        )
        self.rename_session_button.grid(row=0, column=1, sticky="ew", padx=(0, 6))

        self.delete_session_button = ttk.Button(
            session_button_row,
            text="Delete",
            command=self._delete_session,
            style="Ghost.TButton",
        )
        self.delete_session_button.grid(row=0, column=2, sticky="ew")

        right_card = ttk.Frame(body, style="Card.TFrame", padding=(12, 12, 12, 12))
        right_card.columnconfigure(0, weight=1)
        right_card.rowconfigure(1, weight=1)
        body.add(right_card, weight=3)

        chat_header = ttk.Frame(right_card, style="Card.TFrame")
        chat_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        chat_header.columnconfigure(0, weight=1)

        ttk.Label(chat_header, textvariable=self.session_title_var, style="ChatTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(chat_header, text="Ctrl+Enter to send", style="SectionMeta.TLabel", anchor="e").grid(row=0, column=1, sticky="e")

        chat_wrap = ttk.Frame(right_card, style="Card.TFrame")
        chat_wrap.grid(row=1, column=0, sticky="nsew")
        chat_wrap.rowconfigure(0, weight=1)
        chat_wrap.columnconfigure(0, weight=1)

        self.chat_canvas = tk.Canvas(
            chat_wrap,
            background=_UI_COLORS["surface_alt"],
            highlightthickness=1,
            highlightbackground=_UI_COLORS["border"],
            bd=0,
            relief="flat",
        )
        self.chat_canvas.grid(row=0, column=0, sticky="nsew")

        chat_scrollbar = ttk.Scrollbar(chat_wrap, orient="vertical", command=self.chat_canvas.yview)
        chat_scrollbar.grid(row=0, column=1, sticky="ns")
        self.chat_canvas.configure(yscrollcommand=chat_scrollbar.set)

        self.chat_inner = tk.Frame(self.chat_canvas, bg=_UI_COLORS["surface_alt"])
        self._chat_window_id = self.chat_canvas.create_window((0, 0), window=self.chat_inner, anchor="nw")

        self.chat_inner.bind("<Configure>", self._on_chat_inner_configure)
        self.chat_canvas.bind("<Configure>", self._on_chat_canvas_configure)
        self.chat_canvas.bind("<MouseWheel>", self._on_chat_mousewheel)
        self.chat_canvas.bind("<Button-4>", self._on_chat_mousewheel_linux_up)
        self.chat_canvas.bind("<Button-5>", self._on_chat_mousewheel_linux_down)

        input_wrap = ttk.Frame(right_card, style="Card.TFrame", padding=(0, 10, 0, 0))
        input_wrap.grid(row=2, column=0, sticky="ew")
        input_wrap.columnconfigure(0, weight=1)

        self.input_text = tk.Text(
            input_wrap,
            height=5,
            wrap=tk.WORD,
            font=(self.ui_font_family, 11),
            borderwidth=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=_UI_COLORS["border"],
            highlightcolor=_UI_COLORS["primary"],
            background="#f8fafc",
            foreground=_UI_COLORS["text"],
            insertbackground=_UI_COLORS["text"],
            padx=8,
            pady=6,
            undo=True,
        )
        self.input_text.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.input_text.bind("<Control-Return>", self._on_send_shortcut)
        self.input_text.bind("<Command-Return>", self._on_send_shortcut)
        self.input_text.bind("<Shift-space>", self._on_shift_space_for_ime)

        self.send_button = ttk.Button(input_wrap, text="Send", command=self._send_message, style="Primary.TButton")
        self.send_button.grid(row=0, column=1, sticky="ns")

    def _on_chat_inner_configure(self, _event=None) -> None:
        self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))

    def _on_chat_canvas_configure(self, event) -> None:
        self.chat_canvas.itemconfigure(self._chat_window_id, width=event.width)
        next_max_width = max(280, int(event.width * 0.8))
        if abs(next_max_width - self._bubble_max_width_px) >= 12:
            self._bubble_max_width_px = next_max_width
            self._schedule_chat_layout_refresh()

    def _schedule_chat_layout_refresh(self) -> None:
        if self._chat_layout_after_id:
            try:
                self.root.after_cancel(self._chat_layout_after_id)
            except Exception:
                pass
        self._chat_layout_after_id = self.root.after(90, self._rerender_current_session)

    def _rerender_current_session(self) -> None:
        self._chat_layout_after_id = None
        if not self.current_session_id:
            return
        session = self.service.get_session(self.current_session_id)
        if session:
            self._render_session(session)

    def _on_chat_mousewheel(self, event) -> str:
        if event.delta:
            self.chat_canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _on_chat_mousewheel_linux_up(self, _event) -> str:
        self.chat_canvas.yview_scroll(-1, "units")
        return "break"

    def _on_chat_mousewheel_linux_down(self, _event) -> str:
        self.chat_canvas.yview_scroll(1, "units")
        return "break"

    def _copy_to_clipboard(self, text: str, status_message: str) -> None:
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(text or ""))
            self.root.update_idletasks()
            self.status_var.set(status_message)
        except Exception as exc:
            messagebox.showerror("Copy failed", str(exc))

    def _clear_chat_items(self) -> None:
        for child in self.chat_inner.winfo_children():
            child.destroy()

    def _bubble_wrap_width(self) -> int:
        return max(220, self._bubble_max_width_px - 46)

    def _is_markdown_special_line(self, stripped: str) -> bool:
        if not stripped:
            return False
        if stripped.startswith("#"):
            return True
        if stripped.startswith(">"):
            return True
        if _UNORDERED_LIST_PATTERN.match(stripped):
            return True
        if _ORDERED_LIST_PATTERN.match(stripped):
            return True
        return False

    def _render_markdown_message(self, parent: tk.Widget, markdown_text: str, bubble_bg: str, text_color: str) -> None:
        normalized = _normalize_text(markdown_text)
        lines = normalized.split("\n")

        if not normalized.strip():
            self._render_markdown_line(parent, "(empty)", bubble_bg, text_color, "body")
            return

        idx = 0
        while idx < len(lines):
            raw_line = lines[idx]
            stripped = raw_line.strip()

            if not stripped:
                spacer = tk.Frame(parent, bg=bubble_bg, height=4)
                spacer.pack(fill="x")
                idx += 1
                continue

            if stripped.startswith("### "):
                self._render_markdown_line(parent, stripped[4:].strip(), bubble_bg, text_color, "h3")
                idx += 1
                continue

            if stripped.startswith("## "):
                self._render_markdown_line(parent, stripped[3:].strip(), bubble_bg, text_color, "h2")
                idx += 1
                continue

            if stripped.startswith("# "):
                self._render_markdown_line(parent, stripped[2:].strip(), bubble_bg, text_color, "h1")
                idx += 1
                continue

            if _UNORDERED_LIST_PATTERN.match(stripped):
                items: list[str] = []
                while idx < len(lines):
                    line = lines[idx].strip()
                    if not _UNORDERED_LIST_PATTERN.match(line):
                        break
                    items.append(_UNORDERED_LIST_PATTERN.sub("", line, count=1).strip())
                    idx += 1
                for item in items:
                    self._render_markdown_line(parent, f"• {item}", bubble_bg, text_color, "list")
                continue

            if _ORDERED_LIST_PATTERN.match(stripped):
                items: list[str] = []
                while idx < len(lines):
                    line = lines[idx].strip()
                    if not _ORDERED_LIST_PATTERN.match(line):
                        break
                    match = _ORDERED_LIST_PATTERN.match(line)
                    number = match.group(1) if match else "1"
                    body = _ORDERED_LIST_PATTERN.sub("", line, count=1).strip()
                    items.append(f"{number}. {body}")
                    idx += 1
                for item in items:
                    self._render_markdown_line(parent, item, bubble_bg, text_color, "list")
                continue

            if stripped.startswith(">"):
                quote_lines: list[str] = []
                while idx < len(lines):
                    line = lines[idx].strip()
                    if not line.startswith(">"):
                        break
                    quote_lines.append(line[1:].strip())
                    idx += 1
                self._render_quote_block(parent, "\n".join(quote_lines), bubble_bg, text_color)
                continue

            paragraph_lines = [raw_line.rstrip()]
            idx += 1
            while idx < len(lines):
                next_stripped = lines[idx].strip()
                if not next_stripped:
                    break
                if self._is_markdown_special_line(next_stripped):
                    break
                paragraph_lines.append(lines[idx].rstrip())
                idx += 1

            self._render_markdown_line(parent, "\n".join(paragraph_lines), bubble_bg, text_color, "body")

    def _render_markdown_line(self, parent: tk.Widget, text: str, bg: str, fg: str, kind: str) -> None:
        font_size = 10
        font_weight = "normal"

        if kind == "h1":
            font_size = 14
            font_weight = "bold"
        elif kind == "h2":
            font_size = 13
            font_weight = "bold"
        elif kind == "h3":
            font_size = 12
            font_weight = "bold"
        elif kind == "list":
            font_size = 10
            font_weight = "normal"

        line = tk.Message(
            parent,
            text=str(text or ""),
            bg=bg,
            fg=fg,
            anchor="w",
            justify="left",
            width=self._bubble_wrap_width(),
            font=(self.ui_font_family, font_size, font_weight),
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=0,
        )
        line.pack(anchor="w", fill="x", pady=(0, 2))

    def _render_quote_block(self, parent: tk.Widget, text: str, bg: str, fg: str) -> None:
        quote_wrap = tk.Frame(parent, bg=bg)
        quote_wrap.pack(fill="x", pady=(1, 3))

        bar = tk.Frame(quote_wrap, bg=_UI_COLORS["quote_bar"], width=3)
        bar.pack(side="left", fill="y", padx=(0, 8))

        line = tk.Message(
            quote_wrap,
            text=str(text or ""),
            bg=bg,
            fg=fg,
            anchor="w",
            justify="left",
            width=max(160, self._bubble_wrap_width() - 16),
            font=(self.ui_font_family, 10, "normal"),
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=0,
        )
        line.pack(side="left", fill="x", expand=True)

    def _render_code_block(self, parent: tk.Widget, code: str, language: str) -> None:
        code_text = str(code or "")
        code_wrap = tk.Frame(
            parent,
            bg=_UI_COLORS["code_bg"],
            highlightthickness=1,
            highlightbackground=_UI_COLORS["code_border"],
            bd=0,
        )
        code_wrap.pack(fill="x", pady=(2, 4))

        code_header = tk.Frame(code_wrap, bg=_UI_COLORS["code_bg"])
        code_header.pack(fill="x", padx=8, pady=(6, 2))

        lang_text = str(language or "code").strip() or "code"
        tk.Label(
            code_header,
            text=lang_text,
            bg=_UI_COLORS["code_bg"],
            fg=_UI_COLORS["code_meta"],
            font=(self.ui_font_family, 9, "bold"),
        ).pack(side="left")

        ttk.Button(
            code_header,
            text="Copy",
            style="Copy.TButton",
            command=lambda snippet=code_text: self._copy_to_clipboard(snippet, "코드블록을 복사했습니다."),
            width=5,
        ).pack(side="right")

        line_count = max(3, min(18, code_text.count("\n") + 1))
        char_width = max(28, min(120, int(self._bubble_wrap_width() / 8)))

        code_view = tk.Text(
            code_wrap,
            height=line_count,
            width=char_width,
            wrap=tk.WORD,
            bg=_UI_COLORS["code_bg"],
            fg=_UI_COLORS["code_text"],
            insertbackground=_UI_COLORS["code_text"],
            borderwidth=0,
            relief="flat",
            padx=8,
            pady=6,
            font=(self.mono_font_family, 10),
        )
        code_view.pack(fill="x", padx=6, pady=(0, 8))
        code_view.insert("1.0", code_text)
        code_view.configure(state="disabled")

    def _bubble_bg_for_role(self, role: str) -> str:
        normalized = str(role or "assistant").lower()
        if normalized == "user":
            return _UI_COLORS["user_bubble"]
        if normalized == "error":
            return _UI_COLORS["error_bubble"]
        if normalized == "system":
            return _UI_COLORS["system_bubble"]
        return _UI_COLORS["assistant_bubble"]

    def _render_message_bubble(self, role: str, content: str, created_at: str | None = None) -> None:
        normalized_role = str(role or "assistant").lower()
        role_label = _ROLE_LABELS.get(normalized_role, normalized_role.capitalize() or "Assistant")
        timestamp = _format_timestamp(created_at)
        align_right = normalized_role == "user"

        bubble_bg = self._bubble_bg_for_role(normalized_role)
        text_color = _UI_COLORS["error_text"] if normalized_role == "error" else _UI_COLORS["text"]

        row = tk.Frame(self.chat_inner, bg=_UI_COLORS["surface_alt"])
        row.pack(fill="x", padx=10, pady=4)

        bubble = tk.Frame(
            row,
            bg=bubble_bg,
            highlightthickness=1,
            highlightbackground=_UI_COLORS["border"],
            bd=0,
        )
        bubble.pack(side="right" if align_right else "left", anchor="e" if align_right else "w", padx=2)

        bubble_header = tk.Frame(bubble, bg=bubble_bg)
        bubble_header.pack(fill="x", padx=10, pady=(8, 3))

        tk.Label(
            bubble_header,
            text=f"{role_label} · {timestamp}",
            bg=bubble_bg,
            fg=_UI_COLORS["muted"],
            font=(self.ui_font_family, 9, "bold"),
            anchor="w",
        ).pack(side="left")

        raw_message = str(content or "")
        ttk.Button(
            bubble_header,
            text="Copy",
            style="Copy.TButton",
            command=lambda text_to_copy=raw_message: self._copy_to_clipboard(text_to_copy, "메시지를 복사했습니다."),
            width=5,
        ).pack(side="right")

        bubble_body = tk.Frame(bubble, bg=bubble_bg)
        bubble_body.pack(fill="x", padx=10, pady=(0, 9))

        sections = _split_markdown_sections(raw_message)
        for index, (kind, language, section_text) in enumerate(sections):
            if kind == "code":
                self._render_code_block(bubble_body, section_text, language)
            else:
                self._render_markdown_message(bubble_body, section_text, bubble_bg, text_color)
            if index + 1 < len(sections):
                tk.Frame(bubble_body, bg=bubble_bg, height=4).pack(fill="x")

    def _scroll_chat_to_bottom(self) -> None:
        self.chat_canvas.update_idletasks()
        self.chat_canvas.yview_moveto(1.0)

    def _load_initial_data(self) -> None:
        self._load_settings_controls()
        self._refresh_session_list()

    def _load_settings_controls(self) -> None:
        settings = self.service.get_settings()
        providers = self.service.get_provider_options()

        provider = settings.get("provider")
        if provider not in providers:
            provider = providers[0] if providers else "gemini"

        self.provider_combo["values"] = providers
        self.provider_var.set(provider)
        self._reload_model_options(provider, selected_model=settings.get("model"))

    def _reload_model_options(self, provider: str, selected_model: str | None = None) -> None:
        model_options = self.service.get_model_options(provider)
        normalized_model = str(selected_model or "").strip()

        if normalized_model and normalized_model not in model_options:
            model_options = [normalized_model] + [item for item in model_options if item != normalized_model]

        self.model_combo["values"] = model_options

        if normalized_model:
            self.model_var.set(normalized_model)
        elif model_options:
            self.model_var.set(model_options[0])
        else:
            self.model_var.set("")

    def _refresh_session_list(self, select_session_id: str | None = None) -> None:
        sessions = self.service.list_sessions()
        if not sessions:
            created = self.service.create_session()
            sessions = self.service.list_sessions()
            select_session_id = created.get("id")

        self.sessions = sessions
        self._session_ids = [str(item.get("id")) for item in sessions if item.get("id")]

        self.session_listbox.delete(0, tk.END)
        for session in sessions:
            title = str(session.get("title") or "New session")
            message_count = int(session.get("message_count") or 0)
            display = f"{title} ({message_count})"
            self.session_listbox.insert(tk.END, display)

        target_session_id = select_session_id or self.current_session_id
        selected_index = 0
        if target_session_id and target_session_id in self._session_ids:
            selected_index = self._session_ids.index(target_session_id)

        if self._session_ids:
            self.session_listbox.selection_clear(0, tk.END)
            self.session_listbox.selection_set(selected_index)
            self.session_listbox.activate(selected_index)
            self._open_session(self._session_ids[selected_index])

    def _open_session(self, session_id: str) -> None:
        session = self.service.get_session(session_id)
        if not session:
            self.session_title_var.set("No session selected")
            self.status_var.set("Session not found.")
            return

        self.current_session_id = session_id
        self._render_session(session)

    def _render_session(self, session: dict) -> None:
        messages = session.get("messages", []) if isinstance(session, dict) else []

        self._clear_chat_items()
        for message in messages:
            if not isinstance(message, dict):
                continue
            self._render_message_bubble(
                role=str(message.get("role") or "assistant"),
                content=str(message.get("content") or ""),
                created_at=message.get("created_at"),
            )

        title = str(session.get("title") or "New session")
        self.session_title_var.set(title)
        self.status_var.set(f"Selected session: {title}")
        self.root.after_idle(self._scroll_chat_to_bottom)

    def _append_local_user_message(self, prompt: str) -> None:
        self._render_message_bubble("user", prompt, datetime.now().astimezone().isoformat(timespec="seconds"))
        self.root.after_idle(self._scroll_chat_to_bottom)

    def _on_provider_changed(self, _event=None) -> None:
        provider = self.provider_var.get().strip()
        self._reload_model_options(provider)

    def _apply_settings(self) -> None:
        if self._is_busy:
            return

        provider = self.provider_var.get().strip()
        model = self.model_var.get().strip()

        updated = self.service.update_settings(provider=provider, model=model)
        updated_provider = updated.get("provider")
        updated_model = updated.get("model")

        self.provider_var.set(updated_provider)
        self._reload_model_options(updated_provider, selected_model=updated_model)
        self.status_var.set(f"Settings updated: {updated_provider} / {updated_model}")

    def _on_session_selected(self, _event=None) -> None:
        indices = self.session_listbox.curselection()
        if not indices:
            return
        index = int(indices[0])
        if index < 0 or index >= len(self._session_ids):
            return
        self._open_session(self._session_ids[index])

    def _create_session(self) -> None:
        if self._is_busy:
            return
        created = self.service.create_session()
        self._refresh_session_list(select_session_id=created.get("id"))
        self.status_var.set("New session created.")

    def _rename_session(self) -> None:
        if self._is_busy:
            return
        session_id = self.current_session_id
        if not session_id:
            return

        current = self.service.get_session(session_id)
        if not current:
            return

        initial_title = str(current.get("title") or "")
        new_title = simpledialog.askstring(
            "Rename Session",
            "New session title:",
            initialvalue=initial_title,
            parent=self.root,
        )
        if new_title is None:
            return

        normalized = str(new_title).strip()
        if not normalized:
            messagebox.showwarning("Invalid title", "Session title cannot be empty.")
            return
        if len(normalized) > int(MAX_TITLE_CHARS):
            messagebox.showwarning("Invalid title", f"Session title is too long. (max {MAX_TITLE_CHARS})")
            return

        updated = self.service.rename_session(session_id, normalized)
        if not updated:
            messagebox.showerror("Rename failed", "Session not found.")
            return

        self._refresh_session_list(select_session_id=session_id)
        self.status_var.set("Session renamed.")

    def _delete_session(self) -> None:
        if self._is_busy:
            return
        session_id = self.current_session_id
        if not session_id:
            return

        if not messagebox.askyesno("Delete Session", "Delete the selected session?"):
            return

        deleted = self.service.delete_session(session_id)
        if not deleted:
            messagebox.showerror("Delete failed", "Session not found.")
            return

        self.current_session_id = None
        self.session_title_var.set("No session selected")
        self._refresh_session_list()
        self.status_var.set("Session deleted.")

    def _on_send_shortcut(self, _event=None):
        self._send_message()
        return "break"

    def _on_shift_space_for_ime(self, _event=None):
        # Keep Shift+Space available for IME language toggle without inserting a space.
        return "break"

    def _set_busy(self, is_busy: bool, status: str | None = None) -> None:
        self._is_busy = is_busy

        send_state = tk.DISABLED if is_busy else tk.NORMAL
        self.send_button.configure(state=send_state)

        text_state = tk.DISABLED if is_busy else tk.NORMAL
        self.input_text.configure(state=text_state)

        session_button_state = tk.DISABLED if is_busy else tk.NORMAL
        self.new_session_button.configure(state=session_button_state)
        self.rename_session_button.configure(state=session_button_state)
        self.delete_session_button.configure(state=session_button_state)
        self.apply_settings_button.configure(state=session_button_state)

        self.provider_combo.configure(state="disabled" if is_busy else "readonly")
        self.model_combo.configure(state="disabled" if is_busy else "readonly")

        if status is not None:
            self.status_var.set(status)

    def _send_message(self) -> None:
        if self._is_busy:
            return

        if not self.current_session_id:
            created = self.service.create_session()
            self._refresh_session_list(select_session_id=created.get("id"))

        session_id = self.current_session_id
        if not session_id:
            return

        prompt = self.input_text.get("1.0", tk.END).strip()
        if not prompt:
            return
        if len(prompt) > int(MAX_PROMPT_CHARS):
            messagebox.showwarning("Prompt too long", f"Prompt is too long. (max {MAX_PROMPT_CHARS})")
            return

        self.input_text.delete("1.0", tk.END)
        self._append_local_user_message(prompt)

        self._set_busy(True, status="Sending message...")

        worker = threading.Thread(
            target=self._send_message_worker,
            args=(session_id, prompt),
            daemon=True,
        )
        worker.start()

    def _send_message_worker(self, session_id: str, prompt: str) -> None:
        try:
            payload = self.service.send_message(session_id=session_id, prompt=prompt)
            self._event_queue.put({"type": "send_success", "session_id": session_id, "payload": payload})
        except Exception as exc:
            self._event_queue.put({"type": "send_error", "session_id": session_id, "error": str(exc)})

    def _poll_worker_events(self) -> None:
        try:
            while True:
                event = self._event_queue.get_nowait()
                event_type = event.get("type")

                if event_type == "send_success":
                    session_id = event.get("session_id")
                    self._set_busy(False)
                    self._refresh_session_list(select_session_id=session_id)
                    self.status_var.set("Response received.")
                elif event_type == "send_error":
                    session_id = event.get("session_id")
                    error = str(event.get("error") or "Unknown error")
                    self._set_busy(False, status=f"Send failed: {error}")
                    self._refresh_session_list(select_session_id=session_id)
                    messagebox.showerror("Send failed", error)
        except queue.Empty:
            pass
        finally:
            self.root.after(120, self._poll_worker_events)


def run() -> None:
    root = tk.Tk()
    DtgptAgentApp(root)
    root.mainloop()


if __name__ == "__main__":
    run()
