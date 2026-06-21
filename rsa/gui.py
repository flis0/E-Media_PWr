import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import threading
import os
import json
import png_logic
import rsa_cipher

class RedirectText:
    def __init__(self, text_ctrl):
        self.output = text_ctrl
    def write(self, string):
        self.output.insert(tk.END, string)
        self.output.see(tk.END)
    def flush(self): pass

class RSAGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Szyfrowanie PNG RSA")
        self.root.geometry("700x700")
        
        self.keypair = None
        self.filepath = None
        
        self.setup_ui()
        import sys
        sys.stdout = RedirectText(self.log_area)

    def setup_ui(self):
        f1 = ttk.LabelFrame(self.root, text="Klucze", padding=10)
        f1.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(f1, text="Rozmiar (bity):").grid(row=0, column=0, padx=5, pady=5)
        self.bits_var = tk.IntVar(value=32)
        self.bits_combo = ttk.Combobox(f1, textvariable=self.bits_var, values=[16, 32, 64, 128, 256, 512, 1024], width=5, state="readonly")
        self.bits_combo.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Button(f1, text="Generuj", command=self.gen_key).grid(row=0, column=2, padx=5, pady=5)
        ttk.Button(f1, text="Zapisz do pliku", command=self.save_keys).grid(row=0, column=3, padx=5, pady=5)
        ttk.Button(f1, text="Wczytaj z pliku", command=self.load_keys).grid(row=0, column=4, padx=5, pady=5)
        self.lbl_key = ttk.Label(f1, text="Brak kluczy", foreground="red")
        self.lbl_key.grid(row=0, column=5, padx=10, pady=5)

        f2 = ttk.LabelFrame(self.root, text="Plik", padding=10)
        f2.pack(fill="x", padx=10, pady=5)
        ttk.Button(f2, text="Wybierz plik", command=self.sel_file).pack(side="left")
        self.lbl_file = ttk.Label(f2, text="Brak")
        self.lbl_file.pack(side="left", padx=15)

        f3 = ttk.LabelFrame(self.root, text="Parametry Szyfrowania", padding=10)
        f3.pack(fill="x", padx=10, pady=5)
        
        self.mode_var = tk.StringVar(value="ECB")
        ttk.Label(f3, text="Tryb:").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(f3, text="ECB", variable=self.mode_var, value="ECB").grid(row=0, column=1, sticky="w", padx=10)
        ttk.Radiobutton(f3, text="CBC", variable=self.mode_var, value="CBC").grid(row=0, column=2, sticky="w", padx=10)

        self.order_var = tk.StringVar(value="A")
        ttk.Label(f3, text="Kolejnosc:").grid(row=1, column=0, sticky="w", pady=10)
        ttk.Radiobutton(f3, text="Szyfrowanie -> Kompresja", variable=self.order_var, value="A").grid(row=1, column=1, columnspan=2, sticky="w", padx=10)
        ttk.Radiobutton(f3, text="Kompresja -> Szyfrowanie", variable=self.order_var, value="B").grid(row=2, column=1, columnspan=2, sticky="w", padx=10)

        f4 = ttk.Frame(self.root)
        f4.pack(fill="x", padx=10, pady=10)
        ttk.Button(f4, text="Szyfruj", command=self.encrypt_btn).pack(side="left", padx=5)
        ttk.Button(f4, text="Deszyfruj", command=self.decrypt_btn).pack(side="left", padx=5)
        ttk.Button(f4, text="Test biblioteki", command=self.compare_lib).pack(side="right", padx=5)

        self.log_area = scrolledtext.ScrolledText(self.root, height=15, font=("Consolas", 9))
        self.log_area.pack(fill="both", expand=True, padx=10, pady=10)

    def run(self, task):
        threading.Thread(target=task, daemon=True).start()

    def gen_key(self):
        def task():
            bits = self.bits_var.get()
            print(f"\n> Generowanie kluczy RSA ({bits}-bit)...")
            self.keypair = rsa_cipher.generate_keypair(bits)
            self.lbl_key.config(text="Zaladowano", foreground="green")
            print(f"N (Modul): {self.keypair[0][1]}")
            print(f"E (Klucz publiczny): {self.keypair[0][0]}")
            print(f"D (Klucz prywatny): {self.keypair[1][0]}")
        self.run(task)

    def save_keys(self):
        if not self.keypair:
            print("\nBlad: Brak wygenerowanych kluczy do zapisania.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if path:
            data = {
                "e": self.keypair[0][0],
                "n": self.keypair[0][1],
                "d": self.keypair[1][0]
            }
            with open(path, "w") as f:
                json.dump(data, f)
            print(f"\n> Zapisano klucze do pliku: {os.path.basename(path)}")

    def load_keys(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if path:
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                self.keypair = ((data["e"], data["n"]), (data["d"], data["n"]))
                self.lbl_key.config(text="Zaladowano z pliku", foreground="green")
                print(f"\n> Wczytano klucze z pliku: {os.path.basename(path)}")
                print(f"N (Modul): {data['n']}")
                print(f"E (Klucz publiczny): {data['e']}")
                print(f"D (Klucz prywatny): {data['d']}")
            except Exception as e:
                print(f"\nBlad odczytu pliku: {e}")

    def sel_file(self):
        path = filedialog.askopenfilename(filetypes=[("PNG files", "*.png")])
        if path:
            self.filepath = path
            self.lbl_file.config(text=os.path.basename(path))

    def encrypt_btn(self):
        if not self.filepath or not self.keypair:
            print("\nBlad: Brak pliku lub kluczy.")
            return
        def task():
            m = self.mode_var.get()
            o = self.order_var.get()
            out = f"enc_{m}_{o}.png"
            print(f"\n> Szyfrowanie {m}_{o}...")
            try:
                png_logic.process_image_encrypt(self.filepath, out, self.keypair, mode=m, order=o)
                print(f"Zapisano zaszyfrowany plik: {out}")
            except Exception as e:
                print(f"Blad: {e}")
        self.run(task)

    def decrypt_btn(self):
        if not self.filepath or not self.keypair:
            print("\nBlad: Wybierz ZASZYFROWANY plik PNG i wczytaj klucze.")
            return
        def task():
            out_file = "decrypted.png"
            print(f"\n> Deszyfracja {os.path.basename(self.filepath)}...")
            try:
                png_logic.process_image_decrypt(self.filepath, out_file, self.keypair)
                print(f"Zapisano odszyfrowany plik: {out_file}")
            except Exception as e:
                print(f"Blad: {e}")
        self.run(task)

    def compare_lib(self):
        if not self.filepath:
            print("\nBlad: Wybierz plik do pobrania probki.")
            return
        def task():
            print("\n" + "-"*30)
            print("> Generowanie testu...")
            res = png_logic.test_library_comparison(self.filepath)
            print(res)
            print("-" * 30 + "\n")
        self.run(task)

if __name__ == "__main__":
    root = tk.Tk()
    app = RSAGUI(root)
    root.mainloop()