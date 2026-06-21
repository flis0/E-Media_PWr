import secrets

def is_prime(n, k=10):
    if n < 2: return False
    for p in [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31]:
        if n % p == 0: return n == p
    s, d = 0, n - 1
    while d % 2 == 0:
        s, d = s + 1, d // 2
    for _ in range(k):
        x = pow(secrets.randbelow(n - 3) + 2, d, n)
        if x == 1 or x == n - 1: continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1: break
        else: return False
    return True

def get_prime(bits):
    while True:
        p = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if is_prime(p): return p

def generate_keypair(bits):
    p = get_prime(bits // 2)
    q = get_prime(bits - (bits // 2))
    n = p * q
    phi = (p - 1) * (q - 1)
    e = 65537
    d = pow(e, -1, phi)
    return (e, n), (d, n)

def encrypt_blocks(data, pub_key, block_in, mode="ECB"):
    e, n = pub_key
    block_out = (n.bit_length() + 7) // 8
    
    pixels, overflow = bytearray(), bytearray()
    pad_len = (block_in - (len(data) % block_in)) % block_in
    data = data + b'\x00' * pad_len
    
    iv = secrets.token_bytes(block_in) if mode == "CBC" else None
    prev = iv
    
    for i in range(0, len(data), block_in):
        block = data[i:i+block_in]
        if mode == "CBC":
            block = bytes(a ^ b for a, b in zip(block, prev))
            
        m = int.from_bytes(block, 'big')
        c = pow(m, e, n)
        c_bytes = c.to_bytes(block_out, 'big')
        
        over_len = block_out - block_in
        overflow.extend(c_bytes[:over_len])
        pixels.extend(c_bytes[over_len:])
        
        if mode == "CBC":
            prev = c_bytes[-block_in:]
            
    return bytes(pixels), bytes(overflow), iv, pad_len

def decrypt_blocks(pixels, overflow, priv_key, block_in, iv, pad_len, mode="ECB"):
    d, n = priv_key
    block_out = (n.bit_length() + 7) // 8
    over_len = block_out - block_in
    
    out = bytearray()
    prev = iv
    
    for i in range(0, len(pixels), block_in):
        c_bytes = overflow[i//block_in * over_len : (i//block_in + 1) * over_len] + pixels[i:i+block_in]
        c = int.from_bytes(c_bytes, 'big')
        m = pow(c, d, n)
        m_bytes = m.to_bytes(block_in, 'big')
        
        if mode == "CBC":
            m_bytes = bytes(a ^ b for a, b in zip(m_bytes, prev))
            prev = c_bytes[-block_in:]
            
        out.extend(m_bytes)
        
    if pad_len > 0:
        out = out[:-pad_len]
    return bytes(out)