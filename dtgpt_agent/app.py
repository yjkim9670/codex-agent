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
    "user": "User",
    "assistant": "Assistant",
    "system": "System",
    "error": "Error",
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

        self.root.title("DTGPT Agent")
        self.root.geometry("1200x760")
        self.root.minsize(920, 560)

        self._build_ui()
        self._load_initial_data()
        self._poll_worker_events()

    def _build_ui(self) -> None:
        self.root.rowconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)

        top_bar = ttk.Frame(self.root, padding=(10, 8))
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.columnconfigure(6, weight=1)

        ttk.Label(top_bar, text="Provider").grid(row=0, column=0, padx=(0, 8), sticky="w")
        self.provider_combo = ttk.Combobox(top_bar, textvariable=self.provider_var, state="readonly", width=18)
        self.provider_combo.grid(row=0, column=1, padx=(0, 14), sticky="w")
        self.provider_combo.bind("<<ComboboxSelected>>", self._on_provider_changed)

        ttk.Label(top_bar, text="Model").grid(row=0, column=2, padx=(0, 8), sticky="w")
        self.model_combo = ttk.Combobox(top_bar, textvariable=self.model_var, state="readonly", width=34)
        self.model_combo.grid(row=0, column=3, padx=(0, 12), sticky="w")

        self.apply_settings_button = ttk.Button(top_bar, text="Apply", command=self._apply_settings)
        self.apply_settings_button.grid(row=0, column=4, padx=(0, 14), sticky="w")

        self.status_label = ttk.Label(top_bar, textvariable=self.status_var, anchor="e")
        self.status_label.grid(row=0, column=6, sticky="ew")

        body = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        body.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        left_frame = ttk.Frame(body, padding=(8, 8))
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)
        body.add(left_frame, weight=1)

        ttk.Label(left_frame, text="Sessions").grid(row=0, column=0, sticky="w", pady=(0, 6))

        session_list_wrap = ttk.Frame(left_frame)
        session_list_wrap.grid(row=1, column=0, sticky="nsew")
        session_list_wrap.rowconfigure(0, weight=1)
        session_list_wrap.columnconfigure(0, weight=1)

        self.session_listbox = tk.Listbox(session_list_wrap, exportselection=False)
        self.session_listbox.grid(row=0, column=0, sticky="nsew")
        self.session_listbox.bind("<<ListboxSelect>>", self._on_session_selected)

        session_scroll = ttk.Scrollbar(session_list_wrap, orient="vertical", command=self.session_listbox.yview)
        session_scroll.grid(row=0, column=1, sticky="ns")
        self.session_listbox.configure(yscrollcommand=session_scroll.set)

        session_button_row = ttk.Frame(left_frame)
        session_button_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        session_button_row.columnconfigure((0, 1, 2), weight=1)

        self.new_session_button = ttk.Button(session_button_row, text="New", command=self._create_session)
        self.new_session_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.rename_session_button = ttk.Button(session_button_row, text="Rename", command=self._rename_session)
        self.rename_session_button.grid(row=0, column=1, sticky="ew", padx=(0, 6))

        self.delete_session_button = ttk.Button(session_button_row, text="Delete", command=self._delete_session)
        self.delete_session_button.grid(row=0, column=2, sticky="ew")

        right_frame = ttk.Frame(body, padding=(8, 8))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=0)
        body.add(right_frame, weight=3)

        self.chat_view = ScrolledText(
            right_frame,
            wrap=tk.WORD,
            height=30,
            state="disabled",
            font=("TkTextFont", 10),
        )
        self.chat_view.grid(row=0, column=0, sticky="nsew", pady=(0, 8))

        input_row = ttk.Frame(right_frame)
        input_row.grid(row=1, column=0, sticky="ew")
        input_row.columnconfigure(0, weight=1)

        self.input_text = tk.Text(input_row, height=5, wrap=tk.WORD, font=("TkTextFont", 10))
        self.input_text.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.input_text.bind("<Control-Return>", self._on_send_shortcut)

        self.send_button = ttk.Button(input_row, text="Send", command=self._send_message)
        self.send_button.grid(row=0, column=1, sticky="ns")

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
            role = str(message.get("role") or "assistant").lower()
            role_label = _ROLE_LABELS.get(role, role.capitalize() or "Assistant")
            created_at = _format_timestamp(message.get("created_at"))
            content = str(message.get("content") or "")

            header = f"[{created_at}] {role_label}\n"
            self.chat_view.insert(tk.END, header)
            self.chat_view.insert(tk.END, f"{content}\n\n")

        self.chat_view.configure(state="disabled")
        self.chat_view.see(tk.END)

        title = str(session.get("title") or "New session")
        self.status_var.set(f"Selected session: {title}")

    def _append_local_user_message(self, prompt: str) -> None:
        self.chat_view.configure(state="normal")
        self.chat_view.insert(tk.END, f"[{_format_timestamp(datetime.now().isoformat())}] User\n")
        self.chat_view.insert(tk.END, f"{prompt}\n\n")
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
            self._event_queue.put({
                "type": "send_success",
                "session_id": session_id,
                "payload": payload,
            })
        except Exception as exc:
            self._event_queue.put({
                "type": "send_error",
                "session_id": session_id,
                "error": str(exc),
            })

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
