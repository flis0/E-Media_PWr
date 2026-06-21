import struct
import zlib
import rsa_cipher

PNG_SIG = b'\x89PNG\r\n\x1a\n'

def parse_png(filepath):
    with open(filepath, 'rb') as f:
        if f.read(8) != PNG_SIG:
            raise ValueError("Nieprawidlowy naglowek PNG")
        chunks = []
        while True:
            length_bytes = f.read(4)
            if not length_bytes: break
            length = struct.unpack('>I', length_bytes)[0]
            ctype = f.read(4)
            cdata = f.read(length)
            crc = f.read(4)
            chunks.append((ctype, cdata, crc))
    return chunks

def build_png(chunks, filepath):
    with open(filepath, 'wb') as f:
        f.write(PNG_SIG)
        for ctype, cdata, _ in chunks:
            crc = zlib.crc32(ctype + cdata) & 0xffffffff
            f.write(struct.pack('>I', len(cdata)))
            f.write(ctype)
            f.write(cdata)
            f.write(struct.pack('>I', crc))

def process_image_encrypt(in_path, out_path, key, mode="ECB", order="A", block_in=3):
    chunks = parse_png(in_path)
    idat_data = bytearray()
    other_chunks = []
    
    for ctype, cdata, crc in chunks:
        if ctype == b'IDAT':
            idat_data.extend(cdata)
        else:
            other_chunks.append((ctype, cdata, crc))
            
    raw_data = zlib.decompress(idat_data)
    
    if order == "A":
        processed_data, overflow, iv, pad_len = rsa_cipher.encrypt_blocks(raw_data, key[0], block_in, mode)
        final_idat = zlib.compress(processed_data)
    else:
        processed_data, overflow, iv, pad_len = rsa_cipher.encrypt_blocks(idat_data, key[0], block_in, mode)
        final_idat = processed_data 
        
    meta = mode.encode('ascii').ljust(3, b' ') + order.encode('ascii') + bytes([pad_len, len(iv) if iv else 0])
    if iv:
        meta += iv
    meta += overflow
    
    crpt_chunk = (b'crPT', meta, 0)
    
    final_chunks = []
    for c in other_chunks:
        if c[0] == b'IEND':
            final_chunks.append((b'IDAT', final_idat, 0))
            final_chunks.append(crpt_chunk)
        final_chunks.append(c)
        
    build_png(final_chunks, out_path)

def process_image_decrypt(in_path, out_path, key, block_in=3):
    chunks = parse_png(in_path)
    idat_data = bytearray()
    other_chunks = []
    crpt_data = None
    
    for ctype, cdata, crc in chunks:
        if ctype == b'IDAT':
            idat_data.extend(cdata)
        elif ctype == b'crPT':
            crpt_data = cdata
        else:
            other_chunks.append((ctype, cdata, crc))
            
    if not crpt_data:
        raise ValueError("Plik nie zawiera metadanych kryptograficznych (chunka crPT).")
        
    mode = crpt_data[:3].decode('ascii').strip()
    order = crpt_data[3:4].decode('ascii')
    pad_len = crpt_data[4]
    iv_len = crpt_data[5]
    
    offset = 6
    iv = crpt_data[offset:offset+iv_len] if iv_len > 0 else None
    offset += iv_len
    overflow = crpt_data[offset:]
    
    if order == "A":
        decompressed_idat = zlib.decompress(idat_data)
        decrypted_data = rsa_cipher.decrypt_blocks(decompressed_idat, overflow, key[1], block_in, iv, pad_len, mode)
        final_idat = zlib.compress(decrypted_data)
    else:
        decrypted_data = rsa_cipher.decrypt_blocks(idat_data, overflow, key[1], block_in, iv, pad_len, mode)
        final_idat = decrypted_data 
        
    final_chunks = []
    for c in other_chunks:
        if c[0] == b'IEND':
            final_chunks.append((b'IDAT', final_idat, 0))
        final_chunks.append(c)
    
    build_png(final_chunks, out_path)

def test_library_comparison(filepath):
    if not filepath:
        return "Blad: Brak pliku."
        
    try:
        from Crypto.PublicKey import RSA
        from Crypto.Cipher import PKCS1_OAEP
    except ImportError as e:
        return f"Blad: Brak biblioteki pycryptodome ({e})"
        
    chunks = parse_png(filepath)
    idat_data = bytearray()
    other_chunks = []
    
    for ctype, cdata, crc in chunks:
        if ctype == b'IDAT':
            idat_data.extend(cdata)
        else:
            other_chunks.append((ctype, cdata, crc))
            
    raw_data = zlib.decompress(idat_data)
    
    my_key = rsa_cipher.generate_keypair(1024)
    e, n = my_key[0]
    d, _ = my_key[1]
    
    lib_key = RSA.construct((n, e, d))
    cipher_rsa = PKCS1_OAEP.new(lib_key)
    
    lib_pixels = bytearray()
    chunk_size = 64 
    
    for i in range(0, len(raw_data), chunk_size):
        chunk = raw_data[i:i+chunk_size]
        ct = cipher_rsa.encrypt(chunk)
        lib_pixels.extend(ct[:len(chunk)])
        
    our_pixels, _, _, _ = rsa_cipher.encrypt_blocks(raw_data, my_key[0], block_in=chunk_size, mode="ECB")
    our_pixels = bytearray(our_pixels)
    
    diff_pixels = bytearray()
    for a, b in zip(our_pixels, lib_pixels):
        diff_pixels.append(abs(a - b))
        
    def save_variant(data, name):
        final_idat = zlib.compress(data)
        out_chunks = []
        for c in other_chunks:
            if c[0] == b'IEND':
                out_chunks.append((b'IDAT', final_idat, 0))
            out_chunks.append(c)
        build_png(out_chunks, name)
        
    save_variant(our_pixels, "cmp_own.png")
    save_variant(lib_pixels, "cmp_lib.png")
    save_variant(diff_pixels, "cmp_diff.png")
    
    return (
        "Zapisano pliki graficzne do porownania:\n"
        "1. cmp_own.png \n"
        "2. cmp_lib.png \n"
        "3. cmp_diff.png \n"
    )