#!/usr/bin/env python3
import struct
import zlib
import os
import sys
import io
import datetime
from pathlib import Path

# ── Stałe PNG ────────────────────────────────────────────────────────────────
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'

COLOR_TYPE_NAMES = {
    0: "Grayscale",
    2: "RGB (Truecolor)",
    3: "Indexed-color (Palette)",
    4: "Grayscale + Alpha",
    6: "RGBA (Truecolor + Alpha)",
}

COMPRESSION_METHODS = {0: "Deflate/Inflate"}
FILTER_METHODS      = {0: "Adaptive filtering"}
INTERLACE_METHODS   = {0: "No interlace", 1: "Adam7 interlace"}


# ─────────────────────────────────────────────────────────────────────────────
# Klasy danych
# ─────────────────────────────────────────────────────────────────────────────

class PNGChunk:
    """Reprezentacja pojedynczego chunka PNG."""
    def __init__(self, length: int, chunk_type: bytes, data: bytes, crc: int, offset: int):
        self.length     = length
        self.chunk_type = chunk_type
        self.type_str   = chunk_type.decode("ascii", errors="replace")
        self.data       = data
        self.crc        = crc
        self.offset     = offset          # pozycja początku chunka w pliku
        self.crc_ok     = (zlib.crc32(chunk_type + data) & 0xFFFFFFFF) == crc

    def is_critical(self) -> bool:
        # Bit 5 pierwszego bajtu nazwy: 0 = critical, 1 = ancillary
        return (self.chunk_type[0] & 0x20) == 0

    def is_ancillary(self) -> bool:
        return not self.is_critical()

    def __repr__(self):
        return f"<PNGChunk type={self.type_str!r} len={self.length} offset={self.offset}>"


class PNGFile:
    """Kompletna analiza pliku PNG."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.file_size = os.path.getsize(filepath)
        self.chunks: list[PNGChunk] = []
        self.valid_signature = False
        self.raw_bytes: bytes = b""

        self._parse()

    # ── Parsowanie ────────────────────────────────────────────────────────────

    def _parse(self):
        with open(self.filepath, "rb") as f:
            self.raw_bytes = f.read()

        data = self.raw_bytes

        # Sygnatura
        self.valid_signature = data[:8] == PNG_SIGNATURE

        pos = 8
        while pos < len(data):
            if pos + 12 > len(data):
                break  # urwany chunk
            length = struct.unpack(">I", data[pos:pos+4])[0]
            ctype  = data[pos+4:pos+8]
            cdata  = data[pos+8:pos+8+length]
            crc    = struct.unpack(">I", data[pos+8+length:pos+12+length])[0]
            chunk  = PNGChunk(length, ctype, cdata, crc, offset=pos)
            self.chunks.append(chunk)
            pos += 12 + length

    # ── Wygodne właściwości ───────────────────────────────────────────────────

    @property
    def ihdr(self) -> PNGChunk | None:
        for c in self.chunks:
            if c.type_str == "IHDR":
                return c
        return None

    def chunks_of_type(self, t: str) -> list[PNGChunk]:
        return [c for c in self.chunks if c.type_str == t]

    @property
    def critical_chunks(self) -> list[PNGChunk]:
        return [c for c in self.chunks if c.is_critical()]

    @property
    def ancillary_chunks(self) -> list[PNGChunk]:
        return [c for c in self.chunks if c.is_ancillary()]

    # ── Dekodowanie IHDR ──────────────────────────────────────────────────────

    def decode_ihdr(self) -> dict:
        c = self.ihdr
        if c is None or len(c.data) < 13:
            return {}
        w, h = struct.unpack(">II", c.data[:8])
        bit_depth   = c.data[8]
        color_type  = c.data[9]
        compression = c.data[10]
        filter_m    = c.data[11]
        interlace   = c.data[12]
        return {
            "width":       w,
            "height":      h,
            "bit_depth":   bit_depth,
            "color_type":  color_type,
            "color_type_name": COLOR_TYPE_NAMES.get(color_type, f"Unknown ({color_type})"),
            "compression": compression,
            "compression_name": COMPRESSION_METHODS.get(compression, f"Unknown ({compression})"),
            "filter_method": filter_m,
            "filter_name": FILTER_METHODS.get(filter_m, f"Unknown ({filter_m})"),
            "interlace":   interlace,
            "interlace_name": INTERLACE_METHODS.get(interlace, f"Unknown ({interlace})"),
            "channels":    self._channels(color_type),
            "bit_depth_per_pixel": bit_depth * self._channels(color_type),
        }

    @staticmethod
    def _channels(color_type: int) -> int:
        return {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type, 0)

    # ── Dekodowanie PLTE ──────────────────────────────────────────────────────

    def decode_plte(self) -> list[tuple[int,int,int]]:
        chunks = self.chunks_of_type("PLTE")
        if not chunks:
            return []
        data = chunks[0].data
        return [(data[i], data[i+1], data[i+2]) for i in range(0, len(data)-2, 3)]

    # ── Dekodowanie ancillary chunks ──────────────────────────────────────────

    def decode_text_chunk(self, chunk: PNGChunk) -> dict:
        """tEXt: keyword\x00text (Latin-1)"""
        try:
            sep = chunk.data.index(b'\x00')
            keyword = chunk.data[:sep].decode("latin-1")
            text    = chunk.data[sep+1:].decode("latin-1")
            return {"keyword": keyword, "text": text}
        except Exception as e:
            return {"error": str(e)}

    def decode_itxt_chunk(self, chunk: PNGChunk) -> dict:
        """iTXt: keyword\x00compression_flag\x00compression_method\x00language\x00translated_keyword\x00text"""
        try:
            data = chunk.data
            sep0 = data.index(b'\x00')
            keyword   = data[:sep0].decode("latin-1")
            comp_flag = data[sep0+1]
            comp_meth = data[sep0+2]
            rest      = data[sep0+3:]
            sep1      = rest.index(b'\x00')
            language  = rest[:sep1].decode("latin-1")
            rest2     = rest[sep1+1:]
            sep2      = rest2.index(b'\x00')
            trans_kw  = rest2[:sep2].decode("utf-8", errors="replace")
            text_bytes = rest2[sep2+1:]
            if comp_flag == 1:
                text_bytes = zlib.decompress(text_bytes)
            text = text_bytes.decode("utf-8", errors="replace")
            return {
                "keyword": keyword,
                "compression": comp_flag,
                "language": language,
                "translated_keyword": trans_kw,
                "text": text,
            }
        except Exception as e:
            return {"error": str(e)}

    def decode_ztxt_chunk(self, chunk: PNGChunk) -> dict:
        """zTXt: keyword\x00\x00compressed_text"""
        try:
            sep = chunk.data.index(b'\x00')
            keyword = chunk.data[:sep].decode("latin-1")
            # bajt metody kompresji
            comp_method = chunk.data[sep+1]
            compressed  = chunk.data[sep+2:]
            text        = zlib.decompress(compressed).decode("latin-1", errors="replace")
            return {"keyword": keyword, "compression_method": comp_method, "text": text}
        except Exception as e:
            return {"error": str(e)}

    def decode_bkgd(self, chunk: PNGChunk, ihdr_info: dict) -> dict:
        """bKGD: kolor tła"""
        ct = ihdr_info.get("color_type", -1)
        try:
            if ct in (0, 4):   # grayscale
                v = struct.unpack(">H", chunk.data)[0]
                return {"gray": v}
            elif ct in (2, 6): # RGB
                r, g, b = struct.unpack(">HHH", chunk.data)
                return {"red": r, "green": g, "blue": b}
            elif ct == 3:      # indexed
                return {"palette_index": chunk.data[0]}
        except Exception as e:
            return {"error": str(e)}
        return {}

    def decode_gama(self, chunk: PNGChunk) -> dict:
        """gAMA: gamma × 100000"""
        try:
            raw = struct.unpack(">I", chunk.data)[0]
            return {"gamma_raw": raw, "gamma": raw / 100000.0}
        except Exception as e:
            return {"error": str(e)}

    def decode_chrm(self, chunk: PNGChunk) -> dict:
        """cHRM: chromatyczność punktu białego i kanałów RGB"""
        try:
            vals = struct.unpack(">8I", chunk.data)
            keys = ["white_x","white_y","red_x","red_y","green_x","green_y","blue_x","blue_y"]
            return {k: v/100000.0 for k, v in zip(keys, vals)}
        except Exception as e:
            return {"error": str(e)}

    def decode_phys(self, chunk: PNGChunk) -> dict:
        """pHYs: piksele na jednostkę"""
        try:
            px, py, unit = struct.unpack(">IIB", chunk.data)
            unit_name = {0: "unknown", 1: "meter"}.get(unit, f"unknown ({unit})")
            result = {"pixels_per_unit_x": px, "pixels_per_unit_y": py,
                      "unit": unit_name}
            if unit == 1:
                result["dpi_x"] = round(px * 0.0254, 1)
                result["dpi_y"] = round(py * 0.0254, 1)
            return result
        except Exception as e:
            return {"error": str(e)}

    def decode_time(self, chunk: PNGChunk) -> dict:
        """tIME: czas ostatniej modyfikacji"""
        try:
            year, month, day, hour, minute, second = struct.unpack(">HBBBBB", chunk.data)
            return {
                "year": year, "month": month, "day": day,
                "hour": hour, "minute": minute, "second": second,
                "datetime": f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}",
            }
        except Exception as e:
            return {"error": str(e)}

    def decode_srgb(self, chunk: PNGChunk) -> dict:
        """sRGB: intent renderowania"""
        intents = {0:"Perceptual", 1:"Relative colorimetric", 2:"Saturation", 3:"Absolute colorimetric"}
        try:
            ri = chunk.data[0]
            return {"rendering_intent": ri, "rendering_intent_name": intents.get(ri, f"Unknown ({ri})")}
        except Exception as e:
            return {"error": str(e)}

    def decode_trns(self, chunk: PNGChunk, ihdr_info: dict) -> dict:
        """tRNS: przezroczystość"""
        ct = ihdr_info.get("color_type", -1)
        try:
            if ct == 0:
                v = struct.unpack(">H", chunk.data)[0]
                return {"gray_transparent": v}
            elif ct == 2:
                r, g, b = struct.unpack(">HHH", chunk.data)
                return {"red": r, "green": g, "blue": b}
            elif ct == 3:
                return {"alpha_palette": list(chunk.data)}
        except Exception as e:
            return {"error": str(e)}
        return {}

    def decode_exif(self, chunk: PNGChunk) -> dict:
        """eXIf chunk — parsowanie podstawowych tagów EXIF (bez zewnętrznych bibliotek)"""
        try:
            data = chunk.data
            # Sprawdź orientację nagłówka TIFF
            if data[:2] == b'II':
                endian = '<'
            elif data[:2] == b'MM':
                endian = '>'
            else:
                return {"raw_hex": data[:64].hex(), "note": "Unrecognized EXIF/TIFF header"}

            magic = struct.unpack_from(endian + 'H', data, 2)[0]
            if magic != 42:
                return {"error": "Not a valid TIFF magic number"}

            ifd_offset = struct.unpack_from(endian + 'I', data, 4)[0]
            tags = self._parse_ifd(data, ifd_offset, endian)
            return {"tags": tags, "byte_order": "little-endian" if endian == '<' else "big-endian"}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _parse_ifd(data: bytes, offset: int, endian: str) -> dict:
        EXIF_TAGS = {
            0x010E: "ImageDescription",  0x010F: "Make",        0x0110: "Model",
            0x0112: "Orientation",       0x011A: "XResolution", 0x011B: "YResolution",
            0x0128: "ResolutionUnit",    0x0131: "Software",    0x0132: "DateTime",
            0x013B: "Artist",            0x8298: "Copyright",   0x8769: "ExifIFD",
            0x8825: "GPSIFD",
        }
        tags = {}
        try:
            num_entries = struct.unpack_from(endian + 'H', data, offset)[0]
            for i in range(num_entries):
                entry_offset = offset + 2 + i * 12
                tag  = struct.unpack_from(endian + 'H', data, entry_offset)[0]
                typ  = struct.unpack_from(endian + 'H', data, entry_offset+2)[0]
                cnt  = struct.unpack_from(endian + 'I', data, entry_offset+4)[0]
                val_offset = entry_offset + 8

                tag_name = EXIF_TAGS.get(tag, f"Tag_0x{tag:04X}")

                # Odczyt wartości
                if typ == 2:   # ASCII
                    size = cnt
                    if size > 4:
                        off2 = struct.unpack_from(endian + 'I', data, val_offset)[0]
                        value = data[off2:off2+size].decode("ascii", errors="replace").rstrip('\x00')
                    else:
                        value = data[val_offset:val_offset+size].decode("ascii", errors="replace").rstrip('\x00')
                elif typ == 3 and cnt == 1:  # SHORT
                    value = struct.unpack_from(endian + 'H', data, val_offset)[0]
                elif typ == 4 and cnt == 1:  # LONG
                    value = struct.unpack_from(endian + 'I', data, val_offset)[0]
                elif typ == 5 and cnt >= 1:  # RATIONAL
                    off2 = struct.unpack_from(endian + 'I', data, val_offset)[0]
                    num = struct.unpack_from(endian + 'I', data, off2)[0]
                    den = struct.unpack_from(endian + 'I', data, off2+4)[0]
                    value = f"{num}/{den}" + (f" ({num/den:.4f})" if den else "")
                else:
                    value = f"<typ={typ}, cnt={cnt}>"

                tags[tag_name] = value
        except Exception as e:
            tags["parse_error"] = str(e)
        return tags

    # ── Pełna analiza ─────────────────────────────────────────────────────────

    def analyze(self) -> dict:
        """Zwraca słownik z wszystkimi wyekstrahowanymi informacjami."""
        ihdr_info = self.decode_ihdr()
        result = {
            "file": {
                "path":       self.filepath,
                "size_bytes": self.file_size,
                "valid_signature": self.valid_signature,
            },
            "ihdr": ihdr_info,
            "chunks_summary": [],
            "plte":    [],
            "text":    [],
            "itxt":    [],
            "ztxt":    [],
            "bkgd":    {},
            "gama":    {},
            "chrm":    {},
            "phys":    {},
            "time":    {},
            "srgb":    {},
            "trns":    {},
            "exif":    {},
            "unknown_ancillary": [],
        }

        known_ancillary = {"tEXt","iTXt","zTXt","bKGD","gAMA","cHRM","pHYs","tIME","sRGB","tRNS","eXIf","hIST","sBIT","sPLT","iCCP"}

        for c in self.chunks:
            result["chunks_summary"].append({
                "type":     c.type_str,
                "length":   c.length,
                "offset":   c.offset,
                "critical": c.is_critical(),
                "crc_ok":   c.crc_ok,
            })

        result["plte"] = self.decode_plte()

        for c in self.ancillary_chunks:
            t = c.type_str
            if t == "tEXt":
                result["text"].append(self.decode_text_chunk(c))
            elif t == "iTXt":
                result["itxt"].append(self.decode_itxt_chunk(c))
            elif t == "zTXt":
                result["ztxt"].append(self.decode_ztxt_chunk(c))
            elif t == "bKGD":
                result["bkgd"] = self.decode_bkgd(c, ihdr_info)
            elif t == "gAMA":
                result["gama"] = self.decode_gama(c)
            elif t == "cHRM":
                result["chrm"] = self.decode_chrm(c)
            elif t == "pHYs":
                result["phys"] = self.decode_phys(c)
            elif t == "tIME":
                result["time"] = self.decode_time(c)
            elif t == "sRGB":
                result["srgb"] = self.decode_srgb(c)
            elif t == "tRNS":
                result["trns"] = self.decode_trns(c, ihdr_info)
            elif t == "eXIf":
                result["exif"] = self.decode_exif(c)
            elif t not in known_ancillary:
                result["unknown_ancillary"].append({
                    "type":   t,
                    "length": c.length,
                    "offset": c.offset,
                    "data_hex": c.data[:32].hex() + ("..." if c.length > 32 else ""),
                })

        return result

    # ── Anonimizacja ──────────────────────────────────────────────────────────

    def anonymize(self, output_path: str) -> dict:
        """
        Anonimizacja pliku PNG — usuwa wszystkie ancillary chunks.
        Zachowuje integralność obrazu poprzez pozostawienie critical chunks.
        """
        removed = []
        kept    = []

        for c in self.chunks:
            if c.is_critical():
                kept.append(c)
            else:
                removed.append(c.type_str)

        # Zapis
        out = bytearray(PNG_SIGNATURE)
        for c in kept:
            out += struct.pack(">I", c.length)
            out += c.chunk_type
            out += c.data
            out += struct.pack(">I", c.crc)

        with open(output_path, "wb") as f:
            f.write(out)

        return {
            "output_path":   output_path,
            "original_size": self.file_size,
            "new_size":      len(out),
            "saved_bytes":   self.file_size - len(out),
            "removed_chunks": removed,
            "kept_chunks":   [c.type_str for c in kept],
        }
