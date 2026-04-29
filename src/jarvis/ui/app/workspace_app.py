"""Jarvis Codex-style App UI workspace skeleton (Tkinter)."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk
from typing import Dict, List

from src.jarvis.ui.app.mock_adapter import AppDataAdapter

TOKENS = {
    "bg": "#0f1117",
    "panel": "#151923",
    "panel2": "#1b2130",
    "border": "#2a3142",
    "text": "#e6e8ee",
    "muted": "#8b93a7",
    "accent": "#7aa2f7",
    "success": "#86d993",
    "warn": "#f0c674",
    "danger": "#ff6b6b",
    "codebg": "#0b0e14",
}


class WorkspaceApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Jarvis Workspace")
        self.root.geometry("1380x860")
        self.root.minsize(1100, 680)
        self.root.configure(bg=TOKENS["bg"])

        self.adapter = AppDataAdapter()
        self.current_task_id = "task_mock_001"
        self._seen_events = set()

        self.mode_var = tk.StringVar(value="Safe")
        self.project_var = tk.StringVar(value=os.path.basename(os.getcwd()))
        self.branch_var = tk.StringVar(value=os.getenv("JARVIS_BRANCH", "local"))
        self.provider_var = tk.StringVar(value="mock")
        self.model_var = tk.StringVar(value="default")
        self.gate_var = tk.StringVar(value="UNKNOWN")
        self.run_var = tk.StringVar(value="idle")

        self.task_input_var = tk.StringVar()

        self._build_layout()
        self.refresh_all_panels()

    def _build_layout(self):
        self._build_top_bar()

        main = tk.Frame(self.root, bg=TOKENS["bg"])
        main.pack(fill="both", expand=True, padx=10, pady=8)

        upper = tk.Frame(main, bg=TOKENS["bg"])
        upper.pack(fill="both", expand=True)

        left = tk.Frame(upper, bg=TOKENS["panel"], width=230)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self._build_left_sidebar(left)

        center = tk.Frame(upper, bg=TOKENS["bg"], padx=8)
        center.pack(side="left", fill="both", expand=True)
        self._build_center_thread(center)

        right = tk.Frame(upper, bg=TOKENS["panel"], width=360)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        self._build_right_review(right)

        self._build_bottom_panel(main)

    def _build_top_bar(self):
        bar = tk.Frame(self.root, bg=TOKENS["panel"], height=62)
        bar.pack(fill="x", padx=10, pady=(10, 0))
        bar.pack_propagate(False)

        left = tk.Frame(bar, bg=TOKENS["panel"])
        left.pack(side="left", fill="y", padx=12)
        tk.Label(left, text="Jarvis Engineering Workspace", fg=TOKENS["text"], bg=TOKENS["panel"],
                 font=("Consolas", 12, "bold")).pack(anchor="w")
        tk.Label(left, textvariable=self.project_var, fg=TOKENS["muted"], bg=TOKENS["panel"],
                 font=("Consolas", 9)).pack(anchor="w")

        mid = tk.Frame(bar, bg=TOKENS["panel"])
        mid.pack(side="left", padx=30)
        tk.Label(mid, text="Branch", fg=TOKENS["muted"], bg=TOKENS["panel"], font=("Consolas", 9)).grid(row=0, column=0, sticky="w")
        tk.Label(mid, textvariable=self.branch_var, fg=TOKENS["text"], bg=TOKENS["panel"], font=("Consolas", 9)).grid(row=1, column=0, sticky="w")
        tk.Label(mid, text="Mode", fg=TOKENS["muted"], bg=TOKENS["panel"], font=("Consolas", 9)).grid(row=0, column=1, sticky="w", padx=(16, 0))
        mode_box = ttk.Combobox(mid, textvariable=self.mode_var, values=["Safe", "Edit", "Review"], width=9, state="readonly")
        mode_box.grid(row=1, column=1, sticky="w", padx=(16, 0))

        right = tk.Frame(bar, bg=TOKENS["panel"])
        right.pack(side="right", padx=12)
        self._pill(right, "Provider", self.provider_var, TOKENS["accent"]).pack(side="left", padx=3)
        self._pill(right, "Model", self.model_var, TOKENS["accent"]).pack(side="left", padx=3)
        self._pill(right, "Gate", self.gate_var, TOKENS["success"]).pack(side="left", padx=3)
        self._pill(right, "Run", self.run_var, TOKENS["warn"]).pack(side="left", padx=3)

    def _pill(self, parent, key: str, var: tk.StringVar, color: str):
        box = tk.Frame(parent, bg=TOKENS["panel2"], highlightthickness=1, highlightbackground=TOKENS["border"])
        lbl = tk.Label(box, text=f"{key}: {var.get()}", fg=color, bg=TOKENS["panel2"], font=("Consolas", 8, "bold"), padx=7, pady=3)
        lbl.pack()

        def _sync(*_):
            lbl.config(text=f"{key}: {var.get()}")

        var.trace_add("write", _sync)
        return box

    def _build_left_sidebar(self, parent):
        tk.Label(parent, text="Navigation", fg=TOKENS["text"], bg=TOKENS["panel"],
                 font=("Consolas", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 8))
        self.nav = tk.Listbox(parent, bg=TOKENS["panel2"], fg=TOKENS["text"],
                              highlightthickness=1, highlightbackground=TOKENS["border"], bd=0,
                              selectbackground=TOKENS["accent"], selectforeground=TOKENS["bg"],
                              font=("Consolas", 10), activestyle="none")
        for item in ["Projects", "Tasks", "Runs", "Approvals", "History", "Settings"]:
            self.nav.insert("end", item)
        self.nav.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.nav.selection_set(1)

    def _build_center_thread(self, parent):
        task_box = tk.Frame(parent, bg=TOKENS["panel"], padx=10, pady=8)
        task_box.pack(fill="x")
        tk.Label(task_box, text="New Task", fg=TOKENS["muted"], bg=TOKENS["panel"], font=("Consolas", 9)).pack(anchor="w")

        row = tk.Frame(task_box, bg=TOKENS["panel"])
        row.pack(fill="x", pady=(4, 0))
        self.task_entry = tk.Entry(row, textvariable=self.task_input_var, bg=TOKENS["panel2"], fg=TOKENS["text"],
                                   insertbackground=TOKENS["text"], relief="solid", bd=1,
                                   highlightthickness=1, highlightbackground=TOKENS["border"],
                                   font=("Consolas", 11))
        self.task_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.task_entry.bind("<Return>", self.on_submit_task)
        tk.Button(row, text="Run", command=self.on_submit_task, bg=TOKENS["accent"], fg=TOKENS["bg"],
                  font=("Consolas", 9, "bold"), relief="flat", padx=12).pack(side="left", padx=(8, 0))

        thread = tk.Frame(parent, bg=TOKENS["bg"])
        thread.pack(fill="both", expand=True, pady=(8, 0))

        self.thread_scroll = tk.Scrollbar(thread)
        self.thread_scroll.pack(side="right", fill="y")
        self.thread_canvas = tk.Canvas(thread, bg=TOKENS["bg"], highlightthickness=1, highlightbackground=TOKENS["border"],
                                       yscrollcommand=self.thread_scroll.set)
        self.thread_canvas.pack(side="left", fill="both", expand=True)
        self.thread_scroll.config(command=self.thread_canvas.yview)
        self.thread_frame = tk.Frame(self.thread_canvas, bg=TOKENS["bg"])
        self.thread_canvas.create_window((0, 0), window=self.thread_frame, anchor="nw")
        self.thread_frame.bind("<Configure>", lambda _e: self.thread_canvas.configure(scrollregion=self.thread_canvas.bbox("all")))

        self.task_entry.focus_set()
        self.add_thread_card("system", "Task thread is ready. Submit a task to start plan/execution cards.")

    def _build_right_review(self, parent):
        tk.Label(parent, text="Review Pane", fg=TOKENS["text"], bg=TOKENS["panel"],
                 font=("Consolas", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 8))
        self.review_text = tk.Text(parent, bg=TOKENS["codebg"], fg=TOKENS["text"], wrap="word",
                                   font=("Consolas", 9), relief="solid", bd=1,
                                   highlightthickness=1, highlightbackground=TOKENS["border"])
        self.review_text.pack(fill="both", expand=True, padx=10)

        actions = tk.Frame(parent, bg=TOKENS["panel"])
        actions.pack(fill="x", padx=10, pady=8)
        tk.Button(actions, text="Approve", command=lambda: self.on_approval("approve"), bg=TOKENS["success"], fg=TOKENS["bg"], relief="flat").pack(side="left", padx=(0, 6))
        tk.Button(actions, text="Reject", command=lambda: self.on_approval("reject"), bg=TOKENS["danger"], fg=TOKENS["bg"], relief="flat").pack(side="left", padx=(0, 6))
        tk.Button(actions, text="Request changes", command=lambda: self.add_thread_card("approval", "request changes sent"),
                  bg=TOKENS["warn"], fg=TOKENS["bg"], relief="flat").pack(side="left")

    def _build_bottom_panel(self, parent):
        bottom = tk.Frame(parent, bg=TOKENS["bg"], height=190)
        bottom.pack(fill="x", pady=(8, 0))
        bottom.pack_propagate(False)

        tabs = ttk.Notebook(bottom)
        tabs.pack(fill="both", expand=True)

        self.panel_terminal = tk.Text(tabs, bg=TOKENS["codebg"], fg=TOKENS["text"], font=("Consolas", 9))
        self.panel_logs = tk.Text(tabs, bg=TOKENS["codebg"], fg=TOKENS["text"], font=("Consolas", 9))
        self.panel_replay = tk.Text(tabs, bg=TOKENS["codebg"], fg=TOKENS["text"], font=("Consolas", 9))
        self.panel_problems = tk.Text(tabs, bg=TOKENS["codebg"], fg=TOKENS["text"], font=("Consolas", 9))
        self.panel_metrics = tk.Text(tabs, bg=TOKENS["codebg"], fg=TOKENS["text"], font=("Consolas", 9))

        tabs.add(self.panel_terminal, text="Terminal")
        tabs.add(self.panel_logs, text="Logs")
        tabs.add(self.panel_replay, text="Replay Timeline")
        tabs.add(self.panel_problems, text="Problems")
        tabs.add(self.panel_metrics, text="Metrics")

    def add_thread_card(self, kind: str, text: str):
        colors = {
            "user": TOKENS["accent"],
            "plan": TOKENS["warn"],
            "tool": TOKENS["success"],
            "rethink": TOKENS["danger"],
            "memory": TOKENS["muted"],
            "subagent": TOKENS["accent"],
            "final": TOKENS["success"],
            "system": TOKENS["muted"],
            "approval": TOKENS["warn"],
        }
        card = tk.Frame(self.thread_frame, bg=TOKENS["panel"], highlightthickness=1, highlightbackground=TOKENS["border"])
        card.pack(fill="x", padx=6, pady=5)
        tk.Label(card, text=kind.upper(), fg=colors.get(kind, TOKENS["text"]), bg=TOKENS["panel"],
                 font=("Consolas", 8, "bold")).pack(anchor="w", padx=8, pady=(6, 0))
        tk.Label(card, text=text, fg=TOKENS["text"], bg=TOKENS["panel"], wraplength=620,
                 justify="left", anchor="w", font=("Consolas", 9)).pack(fill="x", padx=8, pady=(2, 8))
        self.root.after(10, lambda: self.thread_canvas.yview_moveto(1.0))

    def on_submit_task(self, _event=None):
        prompt = self.task_input_var.get().strip()
        if not prompt:
            self.add_thread_card("system", "Empty task. Please describe a task.")
            return

        self.task_input_var.set("")
        created = self.adapter.create_task(prompt)
        self.current_task_id = created.data.get("task_id", self.current_task_id)

        self.add_thread_card("user", prompt)
        self.add_thread_card("plan", "Plan card created: analyze -> execute -> review -> verify")

        events = self.adapter.get_task_events(self.current_task_id).data
        for ev in events:
            sig = (ev.get("type"), str(ev.get("detail")))
            if sig in self._seen_events:
                continue
            self._seen_events.add(sig)
            et = ev.get("type", "")
            detail = ev.get("detail", {})
            if et == "tool.called":
                self.add_thread_card("tool", f"{et}: {detail}")
            elif et.startswith("rethink"):
                self.add_thread_card("rethink", f"{et}: {detail}")
            elif et.startswith("task.completed"):
                self.add_thread_card("final", f"{et}: {detail}")
            else:
                self.add_thread_card("system", f"{et}: {detail}")

        self.refresh_all_panels()

    def on_approval(self, action: str):
        approvals = self.adapter.get_approvals().data
        if not approvals:
            self.add_thread_card("approval", "No pending approvals")
            return
        aid = approvals[0].get("approval_id", "approval_mock_1")
        if action == "approve":
            self.adapter.approve(aid)
            self.add_thread_card("approval", f"Approved {aid}")
        else:
            self.adapter.reject(aid)
            self.add_thread_card("approval", f"Rejected {aid}")
        self.refresh_all_panels()

    def refresh_all_panels(self):
        health = self.adapter.get_health().data
        self.gate_var.set(health.get("gate_status", "UNKNOWN"))
        self.run_var.set(health.get("run_status", "idle"))

        summary = self.adapter.get_operator_summary(self.current_task_id).data
        approvals = self.adapter.get_approvals().data
        replay = self.adapter.get_task_replay(self.current_task_id).data
        evidence = self.adapter.get_task_evidence(self.current_task_id).data

        lines = [
            "Changed files:",
            *[f"  - {x}" for x in summary.get("changed_files", [])],
            "",
            f"Diff summary: {summary.get('diff_summary', 'n/a')}",
            "Diff viewer: [placeholder]",
            "",
            "Tests run:",
            *[f"  - {t}" for t in summary.get("tests_run", [])],
            "",
            f"Risk summary: {summary.get('risk_summary', 'n/a')}",
            f"Rollback available: {summary.get('rollback_available', False)}",
            "",
            "Evidence links:",
            *[f"  - {link}" for link in summary.get("evidence_links", [])],
            "",
            "Approvals:",
            *[f"  - {a.get('approval_id')} [{a.get('risk_tier')}] {a.get('status')}" for a in approvals],
        ]
        self.review_text.delete("1.0", "end")
        self.review_text.insert("end", "\n".join(lines))

        self.panel_replay.delete("1.0", "end")
        self.panel_replay.insert("end", "\n".join([f"{i.get('index')}. {i.get('type')} @ {i.get('ts')}" for i in replay]))

        self.panel_terminal.delete("1.0", "end")
        self.panel_terminal.insert("end", "$ task run --mode safe\n")
        self.panel_logs.delete("1.0", "end")
        self.panel_logs.insert("end", "event stream loaded\n")
        self.panel_problems.delete("1.0", "end")
        self.panel_problems.insert("end", "No blocking problems\n")
        self.panel_metrics.delete("1.0", "end")
        self.panel_metrics.insert("end", f"events={len(replay)} evidence={len(evidence.get('links', []))}\n")


def main():
    root = tk.Tk()
    WorkspaceApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
