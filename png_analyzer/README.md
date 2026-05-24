# PNG Analyzer — E-media Projekt 1

Aplikacja do analizy formatu PNG. Realizuje wymagania na ocenę **5.0** dla grupy dwuosobowej.

## Wymagania systemowe

```
Python >= 3.11
pip install numpy pillow matplotlib
```

## Uruchomienie

```bash
# GUI (zalecane)
python gui.py

# Wiersz poleceń (wypisuje JSON + weryfikację FFT)
python gui.py obraz.png
```

## Zrealizowane wymagania

### Critical chunks
| Chunk | Opis |
|-------|------|
| IHDR  | szerokość, wysokość, głębia, typ koloru, kompresja, filtr, przeplot |
| PLTE  | pełna paleta kolorów (maks. 256 wpisów RGB) |
| IDAT  | zbiorczy strumień skompresowanych danych obrazu |
| IEND  | znacznik końca pliku |

### Ancillary chunks (≥6 rodzajów)
| Chunk | Opis |
|-------|------|
| tEXt  | metadane tekstowe (Latin-1) |
| iTXt  | metadane UTF-8, opcjonalnie skompresowane |
| zTXt  | metadane tekstowe skompresowane zlib |
| pHYs  | rozdzielczość fizyczna (px/m → DPI) |
| tIME  | data i czas ostatniej modyfikacji |
| gAMA  | wartość gamma |
| cHRM  | chromatyczność punktu białego i kanałów RGB |
| sRGB  | zamiar renderowania (rendering intent) |
| bKGD  | kolor tła |
| tRNS  | przezroczystość |
| eXIf  | **dane EXIF** (parser tagów TIFF bez zewnętrznych bibliotek) |

### Transformacja Fouriera
- 2D FFT (`numpy.fft.fft2`) z wycentrowaniem (`fftshift`)
- Widmo amplitudowe w skali log₁₀
- Mapa fazy
- Profil radialny widma

### Weryfikacja FFT
1. **Test round-trip**: IFFT(FFT(f)) ≈ f (błąd < 1e-6)
2. **Twierdzenie Parsevala**: energia sygnału = energia widma (błąd względny < 1e-6)

### Anonimizacja
- Usunięcie wszystkich ancillary chunks (EXIF, tEXt, iTXt, tIME, gAMA, pHYs, …)
- Opcjonalne scalenie wielu chunków IDAT w jeden — usuwa steganografię w podziale strumienia
- Zachowanie integralności obrazu (critical chunks pozostają nienaruszone)

## Struktura pliku

```
png_analyzer/
├── png_analyzer.py   # Parser PNG — ręczna analiza bajtów
├── fft_module.py     # Transformacja Fouriera + weryfikacja
└── gui.py            # GUI (tkinter) + punkt wejścia CLI
```

## Dyskusja: kompresja a steganografia

Format PNG używa kompresji **Deflate** (LZ77 + kod Huffmana), która jest bezstratna
i ogólna — nie jest dedykowana dla obrazów. Kompresja dedykowana (np. JPEG DCT, WebP)
silniej eksploituje korelacje przestrzenne, osiągając lepsze współczynniki, ale jest stratna.

W kontekście steganografii: ponieważ PNG stosuje filtr adaptacyjny przed Deflate,
modyfikacje na poziomie bajtów danych pikseli mogą wpływać na efektywność kompresji,
co jest wykrywalnym śladem. Z kolei dane ukryte w strukturze chunków (IDAT split,
ancillary chunks) są całkowicie transparentne dla dekodera.
