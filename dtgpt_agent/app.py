"""Tkinter desktop application for session-based Gemini/DTGPT chat."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

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
    "primary_soft": "#d7f3ef",
    "success": "#0f766e",
    "user_bubble": "#dbeafe",
    "assistant_bubble": "#ecfeff",
    "system_bubble": "#fff7ed",
    "error_bubble": "#fee2e2",
    "error_text": "#7f1d1d",
}


def _format_timestamp(value: str | None) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(str(value))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


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

        self.provider_var = tk.StringVar(value="")
        self.model_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Ready")
        self.session_title_var = tk.StringVar(value="No session selected")

        self.root.title("DTGPT Agent")
        self.root.geometry("1260x820")
        self.root.minsize(980, 620)
        self.root.configure(bg=_UI_COLORS["bg"])

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

        self.root.option_add("*Font", "{Segoe UI} 10")

        style.configure("App.TFrame", background=_UI_COLORS["bg"])
        style.configure(
            "Card.TFrame",
            background=_UI_COLORS["surface"],
            relief="flat",
            borderwidth=1,
        )

        style.configure(
            "AppTitle.TLabel",
            background=_UI_COLORS["bg"],
            foreground=_UI_COLORS["text"],
            font=("Segoe UI Semibold", 20),
        )
        style.configure(
            "AppSubtitle.TLabel",
            background=_UI_COLORS["bg"],
            foreground=_UI_COLORS["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "SectionTitle.TLabel",
            background=_UI_COLORS["surface"],
            foreground=_UI_COLORS["text"],
            font=("Segoe UI Semibold", 12),
        )
        style.configure(
            "SectionMeta.TLabel",
            background=_UI_COLORS["surface"],
            foreground=_UI_COLORS["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "FieldLabel.TLabel",
            background=_UI_COLORS["surface"],
            foreground=_UI_COLORS["muted"],
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "Status.TLabel",
            background=_UI_COLORS["surface"],
            foreground=_UI_COLORS["success"],
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "ChatTitle.TLabel",
            background=_UI_COLORS["surface"],
            foreground=_UI_COLORS["text"],
            font=("Segoe UI Semibold", 12),
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
            font=("Segoe UI", 10),
        )
        self.session_listbox.grid(row=0, column=0, sticky="nsew")
        self.session_listbox.bind("<<ListboxSelect>>", self._on_session_selected)

        session_scroll = ttk.Scrollbar(session_list_wrap, orient="vertical", command=self.session_listbox.yview)
        session_scroll.grid(row=0, column=1, sticky="ns")
        self.session_listbox.configure(yscrollcommand=session_scroll.set)

        session_button_row = ttk.Frame(left_card, style="Card.TFrame")
        session_button_row.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        session_button_row.columnconfigure((0, 1, 2), weight=1)

        self.new_session_button = ttk.Button(
            session_button_row,
            text="New",
            command=self._create_session,
            style="Ghost.TButton",
        )
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

        ttk.Label(chat_header, textvariable=self.session_title_var, style="ChatTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            chat_header,
            text="Ctrl+Enter to send",
            style="SectionMeta.TLabel",
            anchor="e",
        ).grid(row=0, column=1, sticky="e")

        self.chat_view = ScrolledText(
            right_card,
            wrap=tk.WORD,
            state="disabled",
            height=30,
            font=("Segoe UI", 10),
            borderwidth=0,
            relief="flat",
            padx=6,
            pady=8,
            background=_UI_COLORS["surface_alt"],
            foreground=_UI_COLORS["text"],
            insertbackground=_UI_COLORS["text"],
            selectbackground="#bfdbfe",
        )
        self.chat_view.grid(row=1, column=0, sticky="nsew")
        self._configure_chat_tags()

        input_wrap = ttk.Frame(right_card, style="Card.TFrame", padding=(0, 10, 0, 0))
        input_wrap.grid(row=2, column=0, sticky="ew")
        input_wrap.columnconfigure(0, weight=1)

        self.input_text = tk.Text(
            input_wrap,
            height=5,
            wrap=tk.WORD,
            font=("Segoe UI", 10),
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
        )
        self.input_text.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.input_text.bind("<Control-Return>", self._on_send_shortcut)

        self.send_button = ttk.Button(input_wrap, text="Send", command=self._send_message, style="Primary.TButton")
        self.send_button.grid(row=0, column=1, sticky="ns")

    def _configure_chat_tags(self) -> None:
        self.chat_view.tag_configure(
            "header_user",
            foreground="#1d4ed8",
            font=("Segoe UI Semibold", 9),
            spacing1=2,
            spacing3=2,
            lmargin1=140,
            lmargin2=140,
            rmargin=18,
        )
        self.chat_view.tag_configure(
            "header_assistant",
            foreground="#0f766e",
            font=("Segoe UI Semibold", 9),
            spacing1=2,
            spacing3=2,
            lmargin1=18,
            lmargin2=18,
            rmargin=140,
        )
        self.chat_view.tag_configure(
            "header_system",
            foreground="#9a3412",
            font=("Segoe UI Semibold", 9),
            spacing1=2,
            spacing3=2,
            lmargin1=18,
            lmargin2=18,
            rmargin=140,
        )
        self.chat_view.tag_configure(
            "header_error",
            foreground=_UI_COLORS["error_text"],
            font=("Segoe UI Semibold", 9),
            spacing1=2,
            spacing3=2,
            lmargin1=18,
            lmargin2=18,
            rmargin=140,
        )

        self.chat_view.tag_configure(
            "body_user",
            background=_UI_COLORS["user_bubble"],
            foreground=_UI_COLORS["text"],
            lmargin1=140,
            lmargin2=140,
            rmargin=18,
            spacing1=2,
            spacing3=4,
            font=("Segoe UI", 10),
        )
        self.chat_view.tag_configure(
            "body_assistant",
            background=_UI_COLORS["assistant_bubble"],
            foreground=_UI_COLORS["text"],
            lmargin1=18,
            lmargin2=18,
            rmargin=140,
            spacing1=2,
            spacing3=4,
            font=("Segoe UI", 10),
        )
        self.chat_view.tag_configure(
            "body_system",
            background=_UI_COLORS["system_bubble"],
            foreground="#7c2d12",
            lmargin1=18,
            lmargin2=18,
            rmargin=140,
            spacing1=2,
            spacing3=4,
            font=("Segoe UI", 10),
        )
        self.chat_view.tag_configure(
            "body_error",
            background=_UI_COLORS["error_bubble"],
            foreground=_UI_COLORS["error_text"],
            lmargin1=18,
            lmargin2=18,
            rmargin=140,
            spacing1=2,
            spacing3=4,
            font=("Segoe UI", 10),
        )
        self.chat_view.tag_configure("message_gap", spacing1=2, spacing3=8)

    def _chat_tags_for_role(self, role: str) -> tuple[str, str]:
        normalized = str(role or "assistant").lower()
        if normalized == "user":
            return "header_user", "body_user"
        if normalized == "error":
            return "header_error", "body_error"
        if normalized == "system":
            return "header_system", "body_system"
        return "header_assistant", "body_assistant"

    def _insert_message_block(self, role: str, content: str, created_at: str | None = None) -> None:
        normalized_role = str(role or "assistant").lower()
        role_label = _ROLE_LABELS.get(normalized_role, normalized_role.capitalize() or "Assistant")
        timestamp = _format_timestamp(created_at)
        header_tag, body_tag = self._chat_tags_for_role(normalized_role)

        text = str(content or "")
        if not text.strip():
            text = "(empty)"
        if not text.endswith("\n"):
            text += "\n"

        self.chat_view.insert(tk.END, f"{role_label}  {timestamp}\n", header_tag)
        self.chat_view.insert(tk.END, text, body_tag)
        self.chat_view.insert(tk.END, "\n", "message_gap")

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

        self.chat_view.configure(state="normal")
        self.chat_view.delete("1.0", tk.END)

        for message in messages:
            if not isinstance(message, dict):
                continue
            self._insert_message_block(
                role=str(message.get("role") or "assistant"),
                content=str(message.get("content") or ""),
                created_at=message.get("created_at"),
            )

        self.chat_view.configure(state="disabled")
        self.chat_view.see(tk.END)

        title = str(session.get("title") or "New session")
        self.session_title_var.set(title)
        self.status_var.set(f"Selected session: {title}")

    def _append_local_user_message(self, prompt: str) -> None:
        self.chat_view.configure(state="normal")
        self._insert_message_block("user", prompt, datetime.now().astimezone().isoformat(timespec="seconds"))
        self.chat_view.configure(state="disabled")
        self.chat_view.see(tk.END)

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
            self._event_queue.put(
                {
                    "type": "send_success",
                    "session_id": session_id,
                    "payload": payload,
                }
            )
        except Exception as exc:
            self._event_queue.put(
                {
                    "type": "send_error",
                    "session_id": session_id,
                    "error": str(exc),
                }
            )

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
