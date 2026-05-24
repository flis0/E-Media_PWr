#!/usr/bin/env python3
"""
Moduł transformacji Fouriera dla obrazów PNG.
Wyświetla widmo amplitudowe 2D oraz weryfikuje poprawność transformacji.
"""

import numpy as np


def compute_fft_spectrum(image_array: np.ndarray) -> dict:
    """
    Oblicza widmo Fouriera obrazu.

    Parametry
    ---------
    image_array : np.ndarray
        Tablica pikseli (H×W lub H×W×C), dtype uint8.

    Zwraca
    ------
    dict z polami:
        grayscale     – obraz szarości (H×W float)
        magnitude     – moduł widma (H×W float, wycentrowany)
        log_magnitude – log10(1+magnitude), do wyświetlenia
        phase         – faza widma (H×W float, wycentrowany)
        fft_complex   – wynik np.fft.fftshift(np.fft.fft2(gray))
        shape         – (H, W)
    """
    # Konwersja do szarości
    if image_array.ndim == 2:
        gray = image_array.astype(np.float64)
    elif image_array.shape[2] == 4:
        # RGBA → gray (pomijamy kanał alfa)
        gray = 0.299 * image_array[:,:,0] + \
               0.587 * image_array[:,:,1] + \
               0.114 * image_array[:,:,2]
    else:
        gray = 0.299 * image_array[:,:,0] + \
               0.587 * image_array[:,:,1] + \
               0.114 * image_array[:,:,2]

    # 2D FFT + wycentrowanie (składowa DC w środku)
    fft_raw    = np.fft.fft2(gray)
    fft_center = np.fft.fftshift(fft_raw)

    magnitude     = np.abs(fft_center)
    log_magnitude = np.log10(1.0 + magnitude)
    phase         = np.angle(fft_center)

    return {
        "grayscale":     gray,
        "magnitude":     magnitude,
        "log_magnitude": log_magnitude,
        "phase":         phase,
        "fft_complex":   fft_center,
        "shape":         gray.shape,
    }


def verify_fft_roundtrip(image_array: np.ndarray) -> dict:
    """
    Weryfikacja poprawności FFT przez IFFT (transformację odwrotną).

    Stosujemy test round-trip: IFFT(FFT(obraz)) ≈ obraz
    Błąd numeryczny powinien być bardzo mały (< 1e-8 na piksel).

    Zwraca
    ------
    dict z polami:
        max_abs_error   – maksymalny błąd bezwzględny
        mean_abs_error  – średni błąd bezwzględny
        passed          – bool, czy błąd jest poniżej progu 1e-6
        energy_original – energia sygnału oryginalnego
        energy_spectrum – energia widma (twierdzenie Parsevala)
        parseval_error  – względna różnica energii (twierdzenie Parsevala)
        parseval_ok     – bool
    """
    if image_array.ndim == 2:
        gray = image_array.astype(np.float64)
    elif image_array.shape[2] >= 3:
        gray = (0.299*image_array[:,:,0] +
                0.587*image_array[:,:,1] +
                0.114*image_array[:,:,2]).astype(np.float64)
    else:
        gray = image_array[:,:,0].astype(np.float64)

    H, W = gray.shape

    # Round-trip test
    fft_val  = np.fft.fft2(gray)
    restored = np.fft.ifft2(fft_val).real
    diff     = np.abs(gray - restored)

    max_err  = float(diff.max())
    mean_err = float(diff.mean())
    passed   = max_err < 1e-6

    # Twierdzenie Parsevala: Σ|f(x,y)|² = (1/N) Σ|F(u,v)|²
    energy_original = float(np.sum(gray ** 2))
    energy_spectrum = float(np.sum(np.abs(fft_val) ** 2) / (H * W))
    parseval_err    = abs(energy_original - energy_spectrum) / max(energy_original, 1e-10)
    parseval_ok     = parseval_err < 1e-6

    return {
        "max_abs_error":   max_err,
        "mean_abs_error":  mean_err,
        "passed":          passed,
        "energy_original": energy_original,
        "energy_spectrum": energy_spectrum,
        "parseval_error":  parseval_err,
        "parseval_ok":     parseval_ok,
    }


def radial_profile(magnitude: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Profil radialny widma (uśrednienie po okręgach).
    Przydatne do porównania charakterystyk różnych obrazów.

    Zwraca (radii, power) — tablice 1D.
    """
    H, W = magnitude.shape
    cy, cx = H // 2, W // 2
    y, x   = np.indices((H, W))
    r      = np.sqrt((x - cx)**2 + (y - cy)**2).astype(int)

    max_r = min(cx, cy)
    radii  = np.arange(0, max_r)
    power  = np.zeros(max_r)

    for ri in radii:
        mask = (r == ri)
        if mask.any():
            power[ri] = magnitude[mask].mean()

    return radii, power
