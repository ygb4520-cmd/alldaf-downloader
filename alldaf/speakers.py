"""Adding and removing speakers."""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from .config import BURGUNDY, CREAM, GOLD, INK, PANEL
from .net import ApiChanged, make_ctx, search_authors
from .util import parse_author_id


class SpeakerMixin:
    def refresh_speakers(self, select=None):
        names = [s["name"] for s in self.cfg["speakers"]]
        self.speaker["values"] = names
        if names:
            self.speaker.set(select if select in names else names[0])
        else:
            self.speaker.set("")

    def pick_author(self, authors):
        """Small dialog: choose one of several matching speakers. Returns the chosen dict or None."""
        win = tk.Toplevel(self.root)
        win.title("Choose speaker")
        win.configure(bg=CREAM)
        win.transient(self.root)
        win.resizable(False, False)
        ttk.Label(win, text="Which speaker?", style="Field.TLabel").pack(anchor="w", padx=14, pady=(12, 6))
        lb = tk.Listbox(win, height=min(10, len(authors)), width=46, exportselection=False, activestyle="none",
                        relief="flat", bg=PANEL, fg=INK, selectbackground=GOLD, selectforeground=BURGUNDY,
                        highlightthickness=1, highlightbackground="#e2d5bd", font=("Segoe UI", 10))
        for a in authors:
            lb.insert("end", f"{a['name']}   (ID {a['id']})")
        lb.selection_set(0)
        lb.pack(padx=14)
        result = [None]

        def ok(_e=None):
            sel = lb.curselection()
            result[0] = authors[sel[0]] if sel else None
            win.destroy()

        row = ttk.Frame(win)
        row.pack(fill="x", padx=14, pady=12)
        ttk.Button(row, text="Add", style="Gold.TButton", command=ok).pack(side="right")
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="right", padx=(0, 8))
        lb.bind("<Double-Button-1>", ok)
        win.bind("<Return>", ok)
        win.bind("<Escape>", lambda e: win.destroy())
        win.grab_set()
        lb.focus_set()
        self.root.wait_window(win)
        return result[0]

    def store_speaker(self, name, author_id):
        self.cfg["speakers"] = [s for s in self.cfg["speakers"] if s["name"] != name]
        self.cfg["speakers"].append({"name": name, "id": author_id})
        self.save_cfg()
        self.refresh_speakers(name)

    def add_speaker(self):
        q = simpledialog.askstring("Add speaker", "Type the speaker's name to look them up on alldaf.org,\n"
                                   "or paste their author page link / ID number:", parent=self.root)
        if not q or not q.strip():
            return
        q = q.strip()
        author_id = parse_author_id(q)
        if author_id is not None and (q.isdigit() or "/" in q):  # a link or bare ID: no search needed
            name = simpledialog.askstring("Add speaker", "Speaker name (as you want it shown):", parent=self.root)
            if name and name.strip():
                self.store_speaker(name.strip(), author_id)
            return
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        try:
            authors = search_authors(q, make_ctx(self.skip_ssl.get()))
        except ApiChanged as e:
            messagebox.showerror("Add speaker", str(e))
            return
        except Exception as e:
            messagebox.showerror("Add speaker", f"Couldn't search alldaf.org: {e}")
            return
        finally:
            self.root.config(cursor="")
        if not authors:
            messagebox.showinfo("Add speaker", f"No speaker found for '{q}'.\nTry a shorter name, or paste "
                                "the link to their author page on alldaf.org.")
            return
        chosen = self.pick_author(authors)
        if chosen:
            self.store_speaker(chosen["name"], chosen["id"])

    def remove_speaker(self):
        n = self.speaker.get()
        if n and messagebox.askyesno("Remove", f"Remove {n} from the list?"):
            self.cfg["speakers"] = [s for s in self.cfg["speakers"] if s["name"] != n]
            self.save_cfg()
            self.refresh_speakers()
