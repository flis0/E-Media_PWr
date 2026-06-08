#!/usr/bin/env python3
"""
GUI aplikacji PNG Analyzer — tkinter + matplotlib
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import json
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageTk
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    DEPS_OK = True
except ImportError as e:
    DEPS_OK = False
    MISSING = str(e)

from png_analyzer import PNGFile
from fft_module import compute_fft_spectrum, verify_fft_roundtrip, radial_profile


# ── Styl ─────────────────────────────────────────────────────────────────────
MONO = ("Courier New", 9)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PNG Analyzer")
        self.geometry("1200x700")

        self.png_file: PNGFile | None = None
        self.analysis: dict | None = None
        self.pil_image: "Image.Image | None" = None

        if not DEPS_OK:
            messagebox.showerror("Missing Dependencies",
                f"Install required libraries:\n{MISSING}\n\n"
                "pip install numpy pillow matplotlib")
            self.destroy()
            return

        self._build_ui()

    # ── UI Layout ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Toolbar
        toolbar = tk.Frame(self)
        toolbar.pack(fill="x", padx=4, pady=4)
        tk.Button(toolbar, text="Open PNG", command=self._open_file).pack(side="left", padx=2)
        tk.Button(toolbar, text="Anonymize", command=self._anonymize).pack(side="left", padx=2)
        tk.Button(toolbar, text="Save Report", command=self._save_report).pack(side="left", padx=2)
        self.status_var = tk.StringVar(value="No file loaded")
        tk.Label(toolbar, textvariable=self.status_var).pack(side="right", padx=4)

        # Main content
        paned = tk.PanedWindow(self, orient="horizontal", sashwidth=5)
        paned.pack(fill="both", expand=True, padx=4, pady=4)

        # Left: image preview + chunks tree
        left = tk.Frame(paned)
        paned.add(left, minsize=280, sticky="nsew")

        self.img_label = tk.Label(left, text="(no image)", bg="white", height=12)
        self.img_label.pack(fill="both", expand=True, padx=2, pady=4)

        tk.Label(left, text="Chunks", font=("", 10, "bold")).pack(anchor="w", padx=2, pady=(4,2))
        tree_frame = tk.Frame(left, height=150)
        tree_frame.pack(fill="both", padx=2, pady=2)

        cols = ("Type", "Length", "Offset", "Kind", "CRC")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=12)
        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=60)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

        # Right: tabs
        right = tk.Frame(paned)
        paned.add(right, minsize=500, sticky="nsew")

        nb = ttk.Notebook(right)
        nb.pack(fill="both", expand=True, pady=2)

        # Metadata tab
        self.meta_tab = tk.Frame(nb)
        nb.add(self.meta_tab, text="Metadata")
        self.meta_text = self._scrolled_text(self.meta_tab)

        # FFT tab
        self.fft_tab = tk.Frame(nb)
        nb.add(self.fft_tab, text="FFT Spectrum")
        tk.Button(self.fft_tab, text="Compute FFT", command=self._show_fft).pack(pady=6)
        self.fft_canvas_frame = tk.Frame(self.fft_tab)
        self.fft_canvas_frame.pack(fill="both", expand=True)

        # FFT Verification tab
        self.verify_tab = tk.Frame(nb)
        nb.add(self.verify_tab, text="FFT Verification")
        tk.Button(self.verify_tab, text="Run Tests", command=self._verify_fft).pack(pady=6)
        self.verify_text = self._scrolled_text(self.verify_tab)

        # Anonymization tab
        self.anon_tab = tk.Frame(nb)
        nb.add(self.anon_tab, text="Anonymization")
        self.anon_text = self._scrolled_text(self.anon_tab)

    def _scrolled_text(self, parent) -> scrolledtext.ScrolledText:
        st = scrolledtext.ScrolledText(parent, font=MONO, wrap=tk.NONE, state="disabled")
        st.pack(fill="both", expand=True, padx=4, pady=4)
        return st

    # ── Main Logic ─────────────────────────────────────────────────────────────

    def _open_file(self):
        path = filedialog.askopenfilename(
            title="Open PNG file",
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            self.png_file = PNGFile(path)
            self.analysis = self.png_file.analyze()
            self.pil_image = Image.open(path)
            self.status_var.set(f"{os.path.basename(path)} ({self.png_file.file_size:,} bytes)")
            self._populate_tree()
            self._populate_meta()
            self._show_preview()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        for cs in self.analysis["chunks_summary"]:
            kind = "Critical" if cs["critical"] else "Ancillary"
            crc_icon = "✓" if cs["crc_ok"] else "✗"
            self.tree.insert("", "end", values=(
                cs["type"], cs["length"], cs["offset"], kind, crc_icon
            ))

    def _show_preview(self):
        img = self.pil_image.copy()
        img.thumbnail((300, 240), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        self.img_label.configure(image=photo, text="")
        self.img_label.image = photo

    def _populate_meta(self):
        a = self.analysis
        lines = []

        # File info
        lines.append("FILE INFORMATION")
        lines.append("=" * 40)
        fi = a["file"]
        lines.append(f"Path:          {fi['path']}")
        lines.append(f"Size:          {fi['size_bytes']:,} bytes")
        lines.append(f"Valid PNG:     {'Yes' if fi['valid_signature'] else 'No'}")

        # IHDR
        lines.append("")
        lines.append("IHDR — Image Header (Critical)")
        lines.append("=" * 40)
        ih = a["ihdr"]
        if ih:
            lines.append(f"Width:         {ih['width']} px")
            lines.append(f"Height:        {ih['height']} px")
            lines.append(f"Bit depth:     {ih['bit_depth']} bits/channel")
            lines.append(f"Color type:    {ih['color_type_name']} (code {ih['color_type']})")
            lines.append(f"Compression:   {ih['compression_name']}")
            lines.append(f"Filter method: {ih['filter_name']}")
            lines.append(f"Interlace:     {ih['interlace_name']}")
            lines.append(f"Channels:      {ih['channels']}")

        # PLTE
        if a["plte"]:
            lines.append("")
            lines.append(f"PLTE — Palette ({len(a['plte'])} entries, Critical)")
            lines.append("=" * 40)
            for i, (r, g, b) in enumerate(a["plte"][:16]):
                lines.append(f"[{i:3d}] RGB({r:3d},{g:3d},{b:3d}) = #{r:02x}{g:02x}{b:02x}")
            if len(a["plte"]) > 16:
                lines.append(f"... and {len(a['plte'])-16} more")

        # Other critical chunks
        lines.append("")
        lines.append("OTHER CRITICAL CHUNKS")
        lines.append("=" * 40)
        idat_chunks = [c for c in a["chunks_summary"] if c["type"] == "IDAT"]
        if idat_chunks:
            total_idat_size = sum(c["length"] for c in idat_chunks)
            lines.append(f"IDAT (Image Data): {len(idat_chunks)} chunk(s), "
                        f"total {total_idat_size:,} bytes (compressed)")
        iend_chunks = [c for c in a["chunks_summary"] if c["type"] == "IEND"]
        if iend_chunks:
            lines.append(f"IEND (Image End): 1 chunk (file terminator)")

        # Ancillary chunks
        self._add_chunk_section(lines, "gAMA", a["gama"], {"gamma": "Gamma value"})
        self._add_chunk_section(lines, "pHYs", a["phys"], {"dpi_x": "DPI X", "dpi_y": "DPI Y"})
        self._add_chunk_section(lines, "tIME", a["time"], {"datetime": "Modification time (UTC)"})
        self._add_chunk_section(lines, "cHRM", a["chrm"], {})
        self._add_chunk_section(lines, "sRGB", a["srgb"], {"rendering_intent_name": "Intent"})
        self._add_chunk_section(lines, "bKGD", a["bkgd"], {})
        self._add_chunk_section(lines, "tRNS", a["trns"], {})

        # Text chunks
        for arr, label in [(a["text"], "tEXt"), (a["itxt"], "iTXt"), (a["ztxt"], "zTXt")]:
            if arr:
                lines.append("")
                lines.append(f"{label} — Text Metadata")
                lines.append("=" * 40)
                for item in arr:
                    if "error" not in item:
                        kw = item.get("keyword", "")
                        text = item.get("text", "")
                        lines.append(f"Key:   {kw}")
                        lines.append(f"Value: {text}")
                        lines.append("")

        # EXIF
        if a["exif"]:
            lines.append("")
            lines.append("eXIf — EXIF Metadata")
            lines.append("=" * 40)
            exif = a["exif"]
            if "error" in exif:
                lines.append(f"Error: {exif['error']}")
            elif "note" in exif:
                lines.append(f"Note: {exif['note']}")
            else:
                lines.append(f"Byte order: {exif.get('byte_order','')}")
                for tag, val in exif.get("tags", {}).items():
                    lines.append(f"{tag}: {val}")

        # Known but undecoded ancillary chunks
        known_undecoded = {"iCCP", "hIST", "sBIT", "sPLT"}
        found_known_undecoded = [c for c in a["chunks_summary"] 
                                 if not c["critical"] and c["type"] in known_undecoded]
        if found_known_undecoded:
            lines.append("")
            lines.append("Known Ancillary Chunks (Not Detailed)")
            lines.append("=" * 40)
            chunk_info = {
                "iCCP": "ICC color profile",
                "hIST": "Histogram (palette image)",
                "sBIT": "Significant bits",
                "sPLT": "Suggested palette",
            }
            for chunk in found_known_undecoded:
                desc = chunk_info.get(chunk["type"], "Unknown type")
                lines.append(f"{chunk['type']:4s} – {desc:<30s} ({chunk['length']:,} bytes)")

        # Unknown chunks
        if a["unknown_ancillary"]:
            lines.append("")
            lines.append("Unknown Ancillary Chunks")
            lines.append("=" * 40)
            for unk in a["unknown_ancillary"]:
                lines.append(f"Type: {unk['type']}  Length: {unk['length']}")

        self._set_text(self.meta_text, "\n".join(lines))

    def _add_chunk_section(self, lines, name, data, field_labels):
        if not data:
            return
        lines.append("")
        lines.append(f"{name}")
        lines.append("=" * 40)
        if "error" in data:
            lines.append(f"Error: {data['error']}")
            return
        for key, val in data.items():
            label = field_labels.get(key, key)
            lines.append(f"  {label:<28} {val}")

    # ── FFT ───────────────────────────────────────────────────────────────────

    def _show_fft(self):
        if self.pil_image is None:
            messagebox.showwarning("Warning", "Load a PNG file first")
            return

        for widget in self.fft_canvas_frame.winfo_children():
            widget.destroy()

        img_arr = np.array(self.pil_image)
        fft_data = compute_fft_spectrum(img_arr)
        radii, power = radial_profile(fft_data["magnitude"])

        fig, axes = plt.subplots(1, 3, figsize=(12, 4))
        fig.subplots_adjust(wspace=0.35)

        # Grayscale image
        ax0 = axes[0]
        ax0.imshow(fft_data["grayscale"], cmap="gray")
        ax0.set_title("Grayscale Image")
        ax0.axis("off")

        # Amplitude spectrum (log)
        ax1 = axes[1]
        im = ax1.imshow(fft_data["log_magnitude"], cmap="inferno", aspect="auto")
        ax1.set_title("Amplitude Spectrum (log)")
        ax1.set_xlabel("Frequency X")
        ax1.set_ylabel("Frequency Y")
        plt.colorbar(im, ax=ax1)

        # Radial profile
        ax2 = axes[2]
        ax2.plot(radii, power, linewidth=1.2)
        ax2.set_title("Radial Profile")
        ax2.set_xlabel("Distance from DC [px]")
        ax2.set_ylabel("Mean Amplitude")
        ax2.grid(True, alpha=0.3)

        canvas = FigureCanvasTkAgg(fig, master=self.fft_canvas_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        plt.close(fig)

    # ── FFT Verification ──────────────────────────────────────────────────────

    def _verify_fft(self):
        if self.pil_image is None:
            messagebox.showwarning("Warning", "Load a PNG file first")
            return

        img_arr = np.array(self.pil_image)
        v = verify_fft_roundtrip(img_arr)

        lines = [
            "FFT Verification Results",
            "=" * 40,
            "",
            "Method 1: Round-trip Test (FFT → IFFT)",
            "─" * 40,
            "IFFT(FFT(f)) should equal f (only float64 error)",
            "",
            f"Max absolute error:  {v['max_abs_error']:.2e}",
            f"Mean absolute error: {v['mean_abs_error']:.2e}",
            f"Threshold:           1e-6",
            f"Result:              {'✓ PASS' if v['passed'] else '✗ FAIL'}",
            "",
            "Method 2: Parseval Theorem",
            "─" * 40,
            "Σ|f(x,y)|² = (1/N)·Σ|F(u,v)|²",
            "Signal and spectrum energy should be equal.",
            "",
            f"Original energy:  {v['energy_original']:.6e}",
            f"Spectrum energy:  {v['energy_spectrum']:.6e}",
            f"Relative error:   {v['parseval_error']:.2e}",
            f"Result:           {'✓ PASS' if v['parseval_ok'] else '✗ FAIL'}",
            "",
            "Notes:",
            "─" * 40,
            "• Uses numpy.fft.fft2 (Cooley-Tukey algorithm)",
            "• Complexity: O(N·M·log(N·M)) instead of O(N²M²)",
            "• fftshift centers DC component (f=0) in the display",
            "• log₁₀ scaling allows visualization of wide dynamic range",
        ]
        self._set_text(self.verify_text, "\n".join(lines))

    # ── Anonymization ─────────────────────────────────────────────────────────

    def _anonymize(self):
        if self.png_file is None:
            messagebox.showwarning("Warning", "Load a PNG file first")
            return

        out_path = filedialog.asksaveasfilename(
            title="Save anonymized file",
            defaultextension=".png",
            initialfile="anonymized.png",
            filetypes=[("PNG", "*.png")]
        )
        if not out_path:
            return

        try:
            stats = self.png_file.anonymize(out_path)
            lines = [
                "Anonymization Results",
                "=" * 40,
                f"Output file:    {stats['output_path']}",
                f"Original size:  {stats['original_size']:,} bytes",
                f"New size:       {stats['new_size']:,} bytes",
                f"Saved:          {stats['saved_bytes']:,} bytes",
                "",
                "Removed chunks:",
            ]
            for ch in stats["removed_chunks"]:
                lines.append(f"  - {ch}")
            lines += [
                "",
                "Kept chunks:",
            ]
            for ch in stats["kept_chunks"]:
                lines.append(f"  + {ch}")

            self._set_text(self.anon_text, "\n".join(lines))
            messagebox.showinfo("Success", f"File saved:\n{out_path}")
        except Exception as e:
            messagebox.showerror("Anonymization Error", str(e))

    # ── Save Report ────────────────────────────────────────────────────────────

    def _save_report(self):
        if self.analysis is None:
            messagebox.showwarning("Warning", "Load a PNG file first")
            return
        path = filedialog.asksaveasfilename(
            title="Save JSON report",
            defaultextension=".json",
            initialfile="report.json",
            filetypes=[("JSON", "*.json")]
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.analysis, f, indent=2, ensure_ascii=False, default=str)
        messagebox.showinfo("Saved", f"Report saved:\n{path}")

    # ── Pomocnicze ────────────────────────────────────────────────────────────

    def _set_text(self, widget: scrolledtext.ScrolledText, content: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.update_idletasks()  # Force geometry update
        widget.see("1.0")  # Scroll to top
        widget.configure(state="disabled")


# ── CLI fallback ──────────────────────────────────────────────────────────────

def cli_main(path: str):
    """Tryb wiersza poleceń — wypisuje metadane i weryfikuje FFT."""
    import json
    from fft_module import compute_fft_spectrum, verify_fft_roundtrip
    from PIL import Image
    import numpy as np

    print(f"\n{'='*56}")
    print(f"  PNG Analyzer — {path}")
    print(f"{'='*56}\n")

    png = PNGFile(path)
    analysis = png.analyze()

    print(json.dumps(analysis, indent=2, ensure_ascii=False, default=str))

    print("\n── Weryfikacja FFT ──────────────────────────────────────")
    img = Image.open(path)
    v = verify_fft_roundtrip(np.array(img))
    print(f"  Round-trip maks. błąd: {v['max_abs_error']:.2e}  {'OK' if v['passed'] else 'FAIL'}")
    print(f"  Parseval błąd:         {v['parseval_error']:.2e}  {'OK' if v['parseval_ok'] else 'FAIL'}")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 2 and sys.argv[1] != "--gui":
        cli_main(sys.argv[1])
    else:
        app = App()
        app.mainloop()
