"""
QuickInvoice - a simple invoice maker for Windows.

Fill in the customer, add lines of work (prices optional), and get a clean
PDF invoice with your logo at the top.

Copyright (C) 2026 NullHarp
https://github.com/nullifiedharp/QuickInvoice

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See the LICENSE file for details.
"""

import json
import os
import re
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk

APP_NAME = "QuickInvoice"
VERSION = "1.0.0"

# ----------------------------------------------------------------- paths --

def resource_path(rel):
    """Path to a bundled file, working both from source and from the .exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def app_data_dir():
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_output_dir():
    return str(Path.home() / "Documents" / "Invoices")


# -------------------------------------------------------------- settings --

DEFAULT_SETTINGS = {
    "business": {"name": "", "address": "", "phone": "", "email": ""},
    "logo": "",
    "currency": "$",
    "next_number": 1,
    "output_dir": "",
    "notes": "Thank you for your business!",
}


def load_settings():
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        with open(app_data_dir() / "settings.json", encoding="utf-8") as f:
            saved = json.load(f)
        s.update({k: v for k, v in saved.items() if k != "business"})
        s["business"].update(saved.get("business", {}))
    except (OSError, ValueError):
        pass
    if not s["output_dir"]:
        s["output_dir"] = default_output_dir()
    return s


def save_settings(s):
    try:
        with open(app_data_dir() / "settings.json", "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    except OSError as e:
        messagebox.showwarning(APP_NAME, f"Couldn't save settings:\n{e}")


# ----------------------------------------------------------------- money --

_MONEY_RE = re.compile(r"\d+(\.\d{1,2})?|\.\d{1,2}")


def parse_money(text):
    """'$1,250.50' -> Decimal('1250.50'). Blank -> None. Junk -> ValueError."""
    t = (text or "").strip().replace(",", "").replace(" ", "")
    if not t:
        return None
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg, t = True, t[1:-1]
    if t.startswith("-"):
        neg, t = True, t[1:]
    t = re.sub(r"^[^\d.\-]+", "", t)          # leading currency symbol
    if t.startswith("-"):
        neg, t = True, t[1:]
    t = t.rstrip("$€£¥")                      # trailing currency symbol
    if not _MONEY_RE.fullmatch(t):
        raise ValueError(text)
    v = Decimal(t)
    return -v if neg else v


def fmt_money(value, symbol="$"):
    sign = "-" if value < 0 else ""
    return f"{sign}{symbol}{abs(value):,.2f}"


# ------------------------------------------------------------------- PDF --

def build_pdf(path, inv):
    """
    inv = {
      business: {name, address, phone, email}, logo: path-or-"",
      customer: {name, address, email, phone},
      number, date, due, currency,
      items: [(description, Decimal-or-None), ...],
      total: Decimal, notes: str
    }
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (HRFlowable, Image as RLImage, KeepTogether,
                                    Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    ink = colors.HexColor("#1d2330")
    grey = colors.HexColor("#6b7280")
    accent = colors.HexColor("#1f3a5f")
    stripe = colors.HexColor("#f2f4f8")
    rule = colors.HexColor("#d5d9e0")
    sym = inv.get("currency", "$")

    def style(name, **kw):
        base = dict(fontName="Helvetica", fontSize=10, leading=14, textColor=ink)
        base.update(kw)
        return ParagraphStyle(name, **base)

    body = style("body")
    small = style("small", fontSize=9, leading=12.5, textColor=grey)
    label = style("label", fontName="Helvetica-Bold", fontSize=8.5, leading=11,
                  textColor=grey)
    biz_name = style("biz", fontName="Helvetica-Bold", fontSize=16, leading=20)
    title = style("title", fontName="Helvetica-Bold", fontSize=26, leading=30,
                  textColor=accent, alignment=TA_RIGHT)
    meta = style("meta", alignment=TA_RIGHT, leading=15)
    th = style("th", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white)
    th_r = style("thr", fontName="Helvetica-Bold", fontSize=9,
                 textColor=colors.white, alignment=TA_RIGHT)
    amt = style("amt", alignment=TA_RIGHT)

    def p(text, st=body):
        return Paragraph(escape(text).replace("\n", "<br/>"), st)

    def lines(*parts):
        return "\n".join(x.strip() for x in parts if x and x.strip())

    page_w = letter[0] - 1.5 * inch - 12      # frame has 6pt padding each side
    biz = inv["business"]
    cust = inv["customer"]

    # --- header: logo + business on the left, INVOICE + numbers on the right
    left = []
    logo = inv.get("logo")
    if logo and os.path.exists(logo):
        try:
            with Image.open(logo) as im:
                w, h = im.size
            s = min((2.8 * inch) / w, (1.1 * inch) / h)
            img = RLImage(logo, width=w * s, height=h * s)
            img.hAlign = "LEFT"
            left += [img, Spacer(1, 8)]
            if biz.get("name"):
                left.append(p(biz["name"], style("bn", fontName="Helvetica-Bold")))
        except Exception:
            logo = None
    if not (logo and left):
        left = [p(biz.get("name") or " ", biz_name), Spacer(1, 4)]
    contact = lines(biz.get("address", ""), biz.get("phone", ""), biz.get("email", ""))
    if contact:
        left.append(p(contact, small))

    meta_txt = f"<b>Invoice #</b>&nbsp;&nbsp;{escape(inv['number'])}"
    if inv.get("date"):
        meta_txt += f"<br/><b>Date</b>&nbsp;&nbsp;{escape(inv['date'])}"
    if inv.get("due"):
        meta_txt += f"<br/><b>Due</b>&nbsp;&nbsp;{escape(inv['due'])}"
    right = [Paragraph("INVOICE", title), Spacer(1, 6), Paragraph(meta_txt, meta)]

    header = Table([[left, right]], colWidths=[page_w * 0.6, page_w * 0.4])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    story = [header, Spacer(1, 16),
             HRFlowable(width="100%", thickness=1, color=rule), Spacer(1, 14)]

    # --- bill to
    story.append(Paragraph("BILL TO", label))
    story.append(Spacer(1, 3))
    story.append(p(cust.get("name", ""), style("cn", fontName="Helvetica-Bold",
                                               fontSize=12, leading=16)))
    cinfo = lines(cust.get("address", ""), cust.get("phone", ""), cust.get("email", ""))
    if cinfo:
        story.append(p(cinfo))
    story.append(Spacer(1, 20))

    # --- line items (amount column only when at least one line has a price)
    items = inv["items"]
    priced = any(v is not None for _, v in items)
    if priced:
        data = [[Paragraph("DESCRIPTION", th), Paragraph("AMOUNT", th_r)]]
        for desc, v in items:
            data.append([p(desc), Paragraph("" if v is None else fmt_money(v, sym), amt)])
        widths = [page_w - 1.6 * inch, 1.6 * inch]
    else:
        data = [[Paragraph("DESCRIPTION OF WORK", th)]]
        data += [[p(desc)] for desc, _ in items]
        widths = [page_w]

    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), accent),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, stripe]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, rule),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.append(table)

    # --- total
    total = Table([["TOTAL", fmt_money(inv["total"], sym)]],
                  colWidths=[1.4 * inch, 1.6 * inch], hAlign="RIGHT")
    total.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), accent),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
    ]))
    story += [Spacer(1, 10), total]

    # --- notes
    if inv.get("notes", "").strip():
        story.append(Spacer(1, 26))
        story.append(KeepTogether([Paragraph("NOTES", label), Spacer(1, 3),
                                   p(inv["notes"].strip(), small)]))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(grey)
        canvas.drawRightString(letter[0] - 0.75 * inch, 0.5 * inch,
                               f"Invoice {inv['number']}  ·  Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        path, pagesize=letter,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.7 * inch, bottomMargin=0.8 * inch,
        title=f"Invoice {inv['number']}", author=biz.get("name", ""),
        creator=f"{APP_NAME} {VERSION}",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def open_file(path):
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606 - opening the user's own file
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError:
        pass


# ------------------------------------------------------------------- GUI --

BG = "#1e1f22"
CARD = "#2b2d31"
FIELD = "#383a40"
FIELD_RO = "#30323a"
FIELD_BAD = "#5a2a2e"
FG = "#e8e8ea"
MUTED = "#9a9ca3"
ACCENT = "#4f8cff"
ACCENT_HOVER = "#6aa0ff"
GOOD = "#3fb27f"

FONT = ("Segoe UI", 12)
FONT_SMALL = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 12, "bold")
FONT_HEAD = ("Segoe UI", 14, "bold")


def make_entry(parent, var=None, width=20, **kw):
    return tk.Entry(parent, textvariable=var, width=width, font=FONT, bg=FIELD,
                    fg=FG, insertbackground=FG, relief="flat",
                    disabledbackground=FIELD_RO, readonlybackground=FIELD_RO,
                    highlightthickness=1, highlightbackground=FIELD,
                    highlightcolor=ACCENT, **kw)


def make_text(parent, height=3, width=30):
    return tk.Text(parent, height=height, width=width, font=FONT, bg=FIELD, fg=FG,
                   insertbackground=FG, relief="flat", wrap="word",
                   highlightthickness=1, highlightbackground=FIELD,
                   highlightcolor=ACCENT, padx=4, pady=3)


def make_button(parent, text, command, primary=False, **kw):
    bg = ACCENT if primary else FIELD
    hover = ACCENT_HOVER if primary else "#474a52"
    b = tk.Button(parent, text=text, command=command, bg=bg, fg="white" if primary else FG,
                  activebackground=hover, activeforeground="white", relief="flat",
                  font=FONT_BOLD if primary else FONT, cursor="hand2",
                  padx=14, pady=6 if primary else 3, bd=0, **kw)
    b.bind("<Enter>", lambda e: b.configure(bg=hover))
    b.bind("<Leave>", lambda e: b.configure(bg=bg))
    return b


def make_label(parent, text="", font=FONT, fg=FG, bg=CARD, **kw):
    return tk.Label(parent, text=text, font=font, fg=fg, bg=bg, **kw)


def get_text(widget):
    return widget.get("1.0", "end").strip()


def set_text(widget, value):
    widget.delete("1.0", "end")
    widget.insert("1.0", value or "")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.title(f"{APP_NAME}  —  Simple Invoices")
        self.geometry("880x900")
        self.minsize(720, 560)
        self.configure(bg=BG)
        try:
            self._icon = tk.PhotoImage(file=resource_path("assets/icon.png"))
            self.iconphoto(True, self._icon)
        except tk.TclError:
            pass

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar", background=FIELD, troughcolor=BG,
                        bordercolor=BG, arrowcolor=FG, lightcolor=FIELD, darkcolor=FIELD)

        self.rows = []
        self._auto_total = False
        self._logo_preview = None

        self._build_actions()
        self._build_scroll_area()
        self._build_form()
        self.new_invoice(confirm=False)

        if not self.settings["business"]["name"]:
            self.after(400, self.edit_business)

    # ---------------------------------------------------------- layout --
    def _build_actions(self):
        bar = tk.Frame(self, bg=BG, pady=12, padx=18)
        bar.pack(side="bottom", fill="x")
        make_button(bar, "Create Invoice PDF", self.create_pdf, primary=True).pack(side="right")
        make_button(bar, "Start New Invoice", self.new_invoice).pack(side="left")
        make_button(bar, "Open Invoices Folder", self.open_folder).pack(side="left", padx=8)

    def _build_scroll_area(self):
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=BG)
        win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(win, width=e.width))
        self.bind_all("<MouseWheel>", self._on_wheel)

    def _on_wheel(self, e):
        if self.canvas.winfo_exists() and str(e.widget).startswith(str(self)):
            if self.canvas.yview() != (0.0, 1.0):
                self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def _card(self, title, hint=None):
        card = tk.Frame(self.body, bg=CARD, padx=18, pady=14)
        card.pack(fill="x", padx=18, pady=(14, 0))
        head = tk.Frame(card, bg=CARD)
        head.pack(fill="x", pady=(0, 10))
        make_label(head, title, FONT_HEAD).pack(side="left")
        if hint:
            make_label(head, hint, FONT_SMALL, MUTED).pack(side="left", padx=10, pady=(3, 0))
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x")
        return inner

    def _build_form(self):
        # --- your business + logo
        c = self._card("Your Business", "shown at the top of every invoice")
        self.logo_label = make_label(c, "No logo", FONT_SMALL, MUTED, width=22, height=4,
                                     bg=FIELD)
        self.logo_label.grid(row=0, column=0, rowspan=3, sticky="w")
        btns = tk.Frame(c, bg=CARD)
        btns.grid(row=0, column=1, rowspan=3, sticky="w", padx=14)
        make_button(btns, "Choose Logo…", self.choose_logo).pack(anchor="w", pady=2, fill="x")
        make_button(btns, "Remove Logo", self.remove_logo).pack(anchor="w", pady=2, fill="x")
        make_button(btns, "Edit My Business Info…", self.edit_business).pack(anchor="w", pady=2, fill="x")
        self.biz_summary = make_label(c, "", FONT_SMALL, MUTED, justify="left", anchor="nw")
        self.biz_summary.grid(row=0, column=2, rowspan=3, sticky="nw")
        c.columnconfigure(2, weight=1)
        self._refresh_business()

        # --- invoice details
        c = self._card("Invoice Details")
        self.number_var = tk.StringVar()
        self.date_var = tk.StringVar()
        self.due_var = tk.StringVar()
        for col, (txt, var, w) in enumerate([("Invoice #", self.number_var, 10),
                                             ("Date", self.date_var, 14),
                                             ("Due Date (optional)", self.due_var, 18)]):
            make_label(c, txt, FONT_SMALL, MUTED).grid(row=0, column=col, sticky="w", padx=(0, 16))
            make_entry(c, var, w).grid(row=1, column=col, sticky="w", padx=(0, 16), ipady=3)

        # --- bill to
        c = self._card("Bill To", "the customer")
        self.cust_name = tk.StringVar()
        self.cust_email = tk.StringVar()
        self.cust_phone = tk.StringVar()
        make_label(c, "Name", FONT_SMALL, MUTED).grid(row=0, column=0, sticky="w")
        make_entry(c, self.cust_name, 34).grid(row=1, column=0, sticky="we", ipady=3)
        make_label(c, "Address", FONT_SMALL, MUTED).grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.cust_addr = make_text(c, 3, 34)
        self.cust_addr.grid(row=3, column=0, rowspan=3, sticky="nwe")
        make_label(c, "Email", FONT_SMALL, MUTED).grid(row=0, column=1, sticky="w", padx=(18, 0))
        make_entry(c, self.cust_email, 28).grid(row=1, column=1, sticky="we", padx=(18, 0), ipady=3)
        make_label(c, "Phone", FONT_SMALL, MUTED).grid(row=2, column=1, sticky="w", padx=(18, 0), pady=(8, 0))
        make_entry(c, self.cust_phone, 28).grid(row=3, column=1, sticky="nwe", padx=(18, 0), ipady=3)
        c.columnconfigure(0, weight=1)
        c.columnconfigure(1, weight=1)

        # --- work / services
        c = self._card("Work Done", "one line per job · prices are optional")
        head = tk.Frame(c, bg=CARD)
        head.pack(fill="x")
        make_label(head, "Description", FONT_SMALL, MUTED).pack(side="left")
        make_label(head, "Price", FONT_SMALL, MUTED, width=13, anchor="w").pack(side="right", padx=(0, 44))
        self.rows_frame = tk.Frame(c, bg=CARD)
        self.rows_frame.pack(fill="x", pady=(2, 6))
        make_button(c, "+ Add Line", lambda: self.add_row(focus=True)).pack(anchor="w")

        # --- total
        tot = tk.Frame(c, bg=CARD)
        tot.pack(fill="x", pady=(14, 0))
        right = tk.Frame(tot, bg=CARD)
        right.pack(side="right")
        make_label(right, "TOTAL", FONT_HEAD).pack(side="left", padx=(0, 10))
        self.total_var = tk.StringVar()
        self.total_entry = make_entry(right, self.total_var, 13, justify="right")
        self.total_entry.configure(font=FONT_HEAD)
        self.total_entry.pack(side="left", ipady=4, padx=(0, 44))
        left = tk.Frame(tot, bg=CARD)
        left.pack(side="left", fill="x", expand=True)
        self.total_hint = make_label(left, "", FONT_SMALL, MUTED, justify="left", anchor="w",
                                     wraplength=380)
        self.total_hint.pack(anchor="w")
        self.manual_var = tk.BooleanVar(value=False)
        tk.Checkbutton(left, text="Let me type the total myself", variable=self.manual_var,
                       command=self.recalc, bg=CARD, fg=FG, selectcolor=FIELD,
                       activebackground=CARD, activeforeground=FG, font=FONT_SMALL,
                       cursor="hand2").pack(anchor="w", pady=(4, 0))

        # --- notes
        c = self._card("Notes", "optional · payment terms, thank-you, etc.")
        self.notes = make_text(c, 3)
        self.notes.pack(fill="x")

        tk.Frame(self.body, bg=BG, height=14).pack()

    # ------------------------------------------------------ line items --
    def add_row(self, desc="", price="", focus=False):
        f = tk.Frame(self.rows_frame, bg=CARD)
        f.pack(fill="x", pady=3)
        dv, pv = tk.StringVar(value=desc), tk.StringVar(value=price)
        de = make_entry(f, dv, 40)
        pe = make_entry(f, pv, 13, justify="right")
        row = {"frame": f, "desc": dv, "price": pv, "de": de, "pe": pe}
        x = tk.Button(f, text="✕", command=lambda: self.remove_row(row), bg=CARD, fg=MUTED,
                      activebackground=FIELD_BAD, activeforeground="white", relief="flat",
                      font=FONT, cursor="hand2", bd=0, width=2)
        x.pack(side="right", padx=(8, 0))
        pe.pack(side="right", ipady=3, padx=(10, 0))
        de.pack(side="left", fill="x", expand=True, ipady=3)
        pv.trace_add("write", lambda *_: self.recalc())
        de.bind("<Return>", lambda e: pe.focus_set())
        pe.bind("<Return>", lambda e: self._next_row(row))
        self.rows.append(row)
        if focus:
            de.focus_set()
            self.after(50, lambda: self.canvas.yview_moveto(1.0) if self.rows[-1] is row else None)
        self.recalc()
        return row

    def _next_row(self, row):
        i = self.rows.index(row)
        if i == len(self.rows) - 1:
            self.add_row(focus=True)
        else:
            self.rows[i + 1]["de"].focus_set()

    def remove_row(self, row):
        if len(self.rows) == 1:
            row["desc"].set("")
            row["price"].set("")
            return
        row["frame"].destroy()
        self.rows.remove(row)
        self.recalc()

    def clear_rows(self):
        for r in self.rows:
            r["frame"].destroy()
        self.rows = []

    # ----------------------------------------------------------- total --
    def recalc(self):
        if not hasattr(self, "total_entry"):
            return
        sym = self.settings["currency"]
        total, priced, bad = Decimal("0"), False, False
        for r in self.rows:
            try:
                v = parse_money(r["price"].get())
                r["pe"].configure(bg=FIELD)
            except ValueError:
                v, bad = None, True
                r["pe"].configure(bg=FIELD_BAD)
            if v is not None:
                priced = True
                total += v

        if priced and not self.manual_var.get():
            self.total_entry.configure(state="normal")
            self.total_var.set(fmt_money(total, sym))
            self.total_entry.configure(state="readonly")
            self._auto_total = True
            hint = "Added up automatically from the prices above."
        else:
            if self._auto_total and not self.manual_var.get():
                self.total_var.set("")          # prices were all removed
            self._auto_total = False
            self.total_entry.configure(state="normal")
            hint = ("Type the total you want on the invoice." if self.manual_var.get()
                    else "No prices on the lines — type one flat total here.")
        if bad:
            hint += "  A price in red isn't a number."
        self.total_hint.configure(text=hint)

    # -------------------------------------------------------- business --
    def _refresh_business(self):
        b = self.settings["business"]
        txt = "\n".join(x for x in [b.get("name", ""), b.get("address", ""),
                                    b.get("phone", ""), b.get("email", "")] if x)
        self.biz_summary.configure(text=txt or "Click “Edit My Business Info…” to add\n"
                                               "your name, address and phone.")
        self._show_logo()

    def _show_logo(self):
        path = self.settings.get("logo")
        if path and os.path.exists(path):
            try:
                with Image.open(path) as im:
                    im = im.convert("RGBA")
                    im.thumbnail((180, 80))
                    self._logo_preview = ImageTk.PhotoImage(im)
                self.logo_label.configure(image=self._logo_preview, text="", width=180, height=80)
                return
            except Exception:
                pass
        self._logo_preview = None
        self.logo_label.configure(image="", text="No logo", width=22, height=4)

    def choose_logo(self):
        path = filedialog.askopenfilename(
            title="Choose your logo",
            filetypes=[("Pictures", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tif *.tiff"),
                       ("All files", "*.*")])
        if not path:
            return
        try:
            with Image.open(path) as im:
                im = im.convert("RGBA")
                bbox = im.getbbox()               # trim empty transparent edges
                if bbox:
                    im = im.crop(bbox)
                if max(im.size) > 1600:
                    im.thumbnail((1600, 1600))
                dest = app_data_dir() / "logo.png"
                im.save(dest, "PNG")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"That picture couldn't be opened.\n\n{e}")
            return
        self.settings["logo"] = str(dest)
        save_settings(self.settings)
        self._show_logo()

    def remove_logo(self):
        self.settings["logo"] = ""
        save_settings(self.settings)
        self._show_logo()

    def edit_business(self):
        win = tk.Toplevel(self, bg=CARD, padx=20, pady=16)
        win.title("My Business Info")
        win.transient(self)
        win.resizable(False, False)
        b = self.settings["business"]

        make_label(win, "This is saved, so you only fill it in once.", FONT_SMALL,
                   MUTED).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        name = tk.StringVar(value=b.get("name", ""))
        phone = tk.StringVar(value=b.get("phone", ""))
        email = tk.StringVar(value=b.get("email", ""))
        cur = tk.StringVar(value=self.settings.get("currency", "$"))
        out = tk.StringVar(value=self.settings.get("output_dir", default_output_dir()))

        def lbl(r, t):
            make_label(win, t, FONT_SMALL, MUTED).grid(row=r, column=0, sticky="nw",
                                                       pady=5, padx=(0, 12))
        lbl(1, "Business / Your Name")
        e_name = make_entry(win, name, 38)
        e_name.grid(row=1, column=1, columnspan=2, sticky="we", ipady=3)
        lbl(2, "Address")
        addr = make_text(win, 3, 38)
        set_text(addr, b.get("address", ""))
        addr.grid(row=2, column=1, columnspan=2, sticky="we", pady=4)
        lbl(3, "Phone")
        make_entry(win, phone, 38).grid(row=3, column=1, columnspan=2, sticky="we", ipady=3, pady=4)
        lbl(4, "Email")
        make_entry(win, email, 38).grid(row=4, column=1, columnspan=2, sticky="we", ipady=3, pady=4)
        lbl(5, "Default Notes")
        notes = make_text(win, 2, 38)
        set_text(notes, self.settings.get("notes", ""))
        notes.grid(row=5, column=1, columnspan=2, sticky="we", pady=4)
        lbl(6, "Currency Symbol")
        make_entry(win, cur, 4).grid(row=6, column=1, sticky="w", ipady=3, pady=4)
        lbl(7, "Save Invoices To")
        make_entry(win, out, 30).grid(row=7, column=1, sticky="we", ipady=3, pady=4)

        def browse():
            d = filedialog.askdirectory(parent=win, initialdir=out.get())
            if d:
                out.set(d)
        make_button(win, "Browse…", browse).grid(row=7, column=2, padx=(8, 0))

        def save():
            old_notes = self.settings.get("notes", "")
            self.settings["business"] = {"name": name.get().strip(),
                                         "address": get_text(addr),
                                         "phone": phone.get().strip(),
                                         "email": email.get().strip()}
            self.settings["currency"] = cur.get().strip() or "$"
            self.settings["output_dir"] = out.get().strip() or default_output_dir()
            self.settings["notes"] = get_text(notes)
            save_settings(self.settings)
            if get_text(self.notes) in ("", old_notes):
                set_text(self.notes, self.settings["notes"])
            self._refresh_business()
            self.recalc()
            win.destroy()

        bar = tk.Frame(win, bg=CARD)
        bar.grid(row=8, column=0, columnspan=3, sticky="e", pady=(14, 0))
        make_button(bar, "Cancel", win.destroy).pack(side="right", padx=(8, 0))
        make_button(bar, "Save", save, primary=True).pack(side="right")
        win.bind("<Escape>", lambda e: win.destroy())
        win.grab_set()
        e_name.focus_set()

    # --------------------------------------------------------- actions --
    def _has_content(self):
        return bool(self.cust_name.get().strip() or get_text(self.cust_addr)
                    or any(r["desc"].get().strip() or r["price"].get().strip()
                           for r in self.rows))

    def new_invoice(self, confirm=True):
        if confirm and self._has_content() and not messagebox.askyesno(
                APP_NAME, "Clear the form and start a new invoice?"):
            return
        self.number_var.set(str(self.settings.get("next_number", 1)).zfill(4))
        self.date_var.set(date.today().strftime("%m/%d/%Y"))
        self.due_var.set("")
        self.cust_name.set("")
        self.cust_email.set("")
        self.cust_phone.set("")
        set_text(self.cust_addr, "")
        set_text(self.notes, self.settings.get("notes", ""))
        self.manual_var.set(False)
        self.total_entry.configure(state="normal")
        self.total_var.set("")
        self._auto_total = False
        self.clear_rows()
        for _ in range(3):
            self.add_row()
        self.canvas.yview_moveto(0)

    def open_folder(self):
        d = self.settings["output_dir"]
        os.makedirs(d, exist_ok=True)
        open_file(d)

    def _fail(self, msg, widget=None):
        messagebox.showwarning(APP_NAME, msg)
        if widget is not None:
            widget.focus_set()

    def create_pdf(self):
        number = self.number_var.get().strip()
        if not number:
            return self._fail("Please give the invoice a number.")
        if not self.cust_name.get().strip():
            return self._fail("Please enter the customer's name.")

        items = []
        for i, r in enumerate(self.rows, 1):
            d, ptxt = r["desc"].get().strip(), r["price"].get().strip()
            if not d and not ptxt:
                continue
            try:
                pv = parse_money(ptxt)
            except ValueError:
                return self._fail(f"Line {i}: “{ptxt}” isn't a price.\n"
                                  "Use numbers only, like 150 or 1,250.00", r["pe"])
            if not d:
                return self._fail(f"Line {i} has a price but no description.", r["de"])
            items.append((d, pv))
        if not items:
            return self._fail("Add at least one line describing the work.",
                              self.rows[0]["de"] if self.rows else None)

        if any(v is not None for _, v in items) and not self.manual_var.get():
            total = sum((v for _, v in items if v is not None), Decimal("0"))
        else:
            try:
                total = parse_money(self.total_var.get())
            except ValueError:
                total = None
            if total is None:
                return self._fail("Please type the total amount (numbers only).",
                                  self.total_entry)

        out_dir = self.settings["output_dir"]
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            return self._fail(f"Couldn't create the invoices folder:\n{out_dir}\n\n{e}")
        safe = lambda s: re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s).strip()[:60]
        path = os.path.join(out_dir, f"Invoice {safe(number)} - {safe(self.cust_name.get())}.pdf")
        if os.path.exists(path) and not messagebox.askyesno(
                APP_NAME, f"“{os.path.basename(path)}” already exists.\nReplace it?"):
            return

        inv = {
            "business": self.settings["business"],
            "logo": self.settings.get("logo", ""),
            "customer": {"name": self.cust_name.get().strip(),
                         "address": get_text(self.cust_addr),
                         "email": self.cust_email.get().strip(),
                         "phone": self.cust_phone.get().strip()},
            "number": number,
            "date": self.date_var.get().strip(),
            "due": self.due_var.get().strip(),
            "currency": self.settings["currency"],
            "items": items,
            "total": total,
            "notes": get_text(self.notes),
        }
        try:
            build_pdf(path, inv)
        except PermissionError:
            return self._fail("Couldn't save the PDF — is that invoice open in another "
                              "program? Close it and try again.")
        except Exception as e:
            return self._fail(f"Something went wrong making the PDF:\n\n{e}")

        if number.isdigit():
            self.settings["next_number"] = max(int(self.settings.get("next_number", 1)),
                                               int(number) + 1)
            save_settings(self.settings)
        open_file(path)
        messagebox.showinfo(APP_NAME, f"Invoice saved:\n\n{path}\n\n"
                                      "Click “Start New Invoice” when you're ready for the next one.")


if __name__ == "__main__":
    if sys.platform == "win32":
        try:  # crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    App().mainloop()
