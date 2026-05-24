#!/usr/bin/env python3
"""
Skrypt testowy — generuje testowe pliki PNG i weryfikuje działanie analizatora.
Nie wymaga GUI, działa w środowisku bez wyświetlacza.
"""

import struct
import zlib
import io
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from png_analyzer import PNGFile, PNG_SIGNATURE


# ── Pomocnik: budowanie chunka PNG ───────────────────────────────────────────

def make_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def make_ihdr(width, height, bit_depth=8, color_type=2) -> bytes:
    data = struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0)
    return make_chunk(b"IHDR", data)


def make_idat(width, height, color_type=2) -> bytes:
    """Generuje minimalny, poprawny strumień IDAT dla obrazu (gradient)."""
    channels = {0:1, 2:3, 3:1, 4:2, 6:4}[color_type]
    rows = []
    for y in range(height):
        row = bytearray([0])  # filter byte = None
        for x in range(width):
            if color_type == 2:  # RGB
                row += bytes([x % 256, y % 256, (x+y) % 256])
            else:
                row += bytes([x % 256] * channels)
        rows.append(bytes(row))
    raw = b"".join(rows)
    compressed = zlib.compress(raw, level=6)
    return make_chunk(b"IDAT", compressed)


def make_text(keyword: str, text: str) -> bytes:
    data = keyword.encode("latin-1") + b"\x00" + text.encode("latin-1")
    return make_chunk(b"tEXt", data)


def make_time(year=2025, month=3, day=5, h=12, m=0, s=0) -> bytes:
    data = struct.pack(">HBBBBB", year, month, day, h, m, s)
    return make_chunk(b"tIME", data)


def make_phys(ppux=3937, ppuy=3937, unit=1) -> bytes:  # 100 DPI
    data = struct.pack(">IIB", ppux, ppuy, unit)
    return make_chunk(b"pHYs", data)


def make_gama(gamma=45455) -> bytes:  # gamma = 1/2.2
    return make_chunk(b"gAMA", struct.pack(">I", gamma))


def build_test_png(path: str, width=64, height=64,
                   include_ancillary=True, multi_idat=False):
    """Buduje testowy plik PNG i zapisuje go."""
    buf = bytearray(PNG_SIGNATURE)
    buf += make_ihdr(width, height)

    if include_ancillary:
        buf += make_gama()
        buf += make_phys()
        buf += make_time()
        buf += make_text("Software", "PNG Analyzer Test v1.0")
        buf += make_text("Author", "E-media Projekt Testowy")
        buf += make_text("Comment", "Plik wygenerowany przez skrypt testowy.")

    if multi_idat:
        # Generuj dwa osobne IDAT (split stream — test steganografii struktury)
        channels = 3
        rows = []
        for y in range(height):
            row = bytearray([0])
            for x in range(width):
                row += bytes([x % 256, y % 256, (x+y) % 256])
            rows.append(bytes(row))
        raw = b"".join(rows)
        compressed = zlib.compress(raw, level=6)
        half = len(compressed) // 2
        buf += make_chunk(b"IDAT", compressed[:half])
        buf += make_chunk(b"IDAT", compressed[half:])
    else:
        buf += make_idat(width, height)

    buf += make_chunk(b"IEND", b"")

    with open(path, "wb") as f:
        f.write(buf)
    return path


# ── Testy ─────────────────────────────────────────────────────────────────────

def run_tests():
    import tempfile
    import json
    import numpy as np

    print("═" * 58)
    print("  PNG Analyzer — Testy automatyczne")
    print("═" * 58)

    results = []

    with tempfile.TemporaryDirectory() as tmpdir:

        # Test 1: Poprawna sygnatura
        p1 = build_test_png(f"{tmpdir}/basic.png")
        png = PNGFile(p1)
        ok = png.valid_signature
        print(f"\n[T1] Sygnatura PNG:          {'✔ OK' if ok else '✘ FAIL'}")
        results.append(("T1 Sygnatura", ok))

        # Test 2: Parsowanie IHDR
        a = png.analyze()
        ih = a["ihdr"]
        ok = ih["width"] == 64 and ih["height"] == 64 and ih["bit_depth"] == 8
        print(f"[T2] IHDR 64×64 8-bit RGB:  {'✔ OK' if ok else '✘ FAIL'}")
        results.append(("T2 IHDR", ok))

        # Test 3: Ancillary chunks
        types_found = {c["type"] for c in a["chunks_summary"]}
        ok = {"tEXt","tIME","pHYs","gAMA"}.issubset(types_found)
        print(f"[T3] Ancillary chunks:       {'✔ OK' if ok else '✘ FAIL'} ({types_found})")
        results.append(("T3 Ancillary", ok))

        # Test 4: Dekodowanie tEXt
        texts = a["text"]
        ok = any(t.get("keyword") == "Software" for t in texts)
        print(f"[T4] Dekodowanie tEXt:       {'✔ OK' if ok else '✘ FAIL'}")
        results.append(("T4 tEXt", ok))

        # Test 5: Dekodowanie tIME
        t = a["time"]
        ok = t.get("year") == 2025 and t.get("month") == 3
        print(f"[T5] Dekodowanie tIME:       {'✔ OK' if ok else '✘ FAIL'} ({t.get('datetime','')})")
        results.append(("T5 tIME", ok))

        # Test 6: Dekodowanie pHYs (DPI)
        ph = a["phys"]
        ok = abs(ph.get("dpi_x", 0) - 100.0) < 1
        print(f"[T6] pHYs → DPI≈100:        {'✔ OK' if ok else '✘ FAIL'} (dpi_x={ph.get('dpi_x')})")
        results.append(("T6 pHYs", ok))

        # Test 7: Anonimizacja — usunięcie ancillary
        anon_path = f"{tmpdir}/anon.png"
        stats = png.anonymize(anon_path)
        png2 = PNGFile(anon_path)
        a2 = png2.analyze()
        has_ancillary = any(not c["critical"] for c in a2["chunks_summary"])
        ok = not has_ancillary and stats["saved_bytes"] > 0
        print(f"[T7] Anonimizacja ancillary: {'✔ OK' if ok else '✘ FAIL'} "
              f"(zaoszczędzono {stats['saved_bytes']} B)")
        results.append(("T7 Anonimizacja", ok))

        # Test 8: Plik zanonimizowany jest poprawnym PNG
        ok8 = png2.valid_signature and any(c["type"]=="IHDR" for c in a2["chunks_summary"])
        print(f"[T8] Anonimizowany PNG OK:   {'✔ OK' if ok8 else '✘ FAIL'}")
        results.append(("T8 Anonimizowany PNG", ok8))

        # Test 9: Weryfikacja FFT (round-trip + Parseval)
        try:
            from PIL import Image
            from fft_module import verify_fft_roundtrip
            img = Image.open(p1)
            v = verify_fft_roundtrip(np.array(img))
            ok9 = v["passed"] and v["parseval_ok"]
            print(f"[T9] FFT round-trip+Parseval:{'✔ OK' if ok9 else '✘ FAIL'} "
                  f"(err={v['max_abs_error']:.1e}, parseval={v['parseval_error']:.1e})")
        except ImportError:
            ok9 = None
            print(f"[T9] FFT (pominięto — brak PIL/numpy)")
        results.append(("T9 FFT", ok9 is not False))

        # Test 10: Multi-IDAT zachowanie podczas anonimizacji
        p_multi = build_test_png(f"{tmpdir}/multi_idat.png", multi_idat=True)
        pm = PNGFile(p_multi)
        a_multi = pm.analyze()
        has_ancillary_multi = any(not c["critical"] for c in a_multi["chunks_summary"])
        pm.anonymize(f"{tmpdir}/multi_anon.png")
        pm2 = PNGFile(f"{tmpdir}/multi_anon.png")
        a_multi2 = pm2.analyze()
        has_ancillary_after = any(not c["critical"] for c in a_multi2["chunks_summary"])
        ok10 = has_ancillary_multi and not has_ancillary_after
        print(f"[T10] Anonimizacja multi-IDAT: {'✔ OK' if ok10 else '✘ FAIL'} "
              f"(ancillary removed)")
        results.append(("T10 Multi-IDAT anonimizacja", ok10))

    print()
    print("═" * 58)
    passed = sum(1 for _, ok in results if ok)
    print(f"  Wyniki: {passed}/{len(results)} testów zaliczonych")
    print("═" * 58)
    for name, ok in results:
        icon = "✔" if ok else "✘"
        print(f"  {icon} {name}")

    return all(ok for _, ok in results)


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
