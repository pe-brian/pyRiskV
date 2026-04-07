def binarray(nb, bits=32):
    nb = nb & ((1 << bits) - 1)  # masque sur bits bits
    res = [(int(val) == 1) for val in list(bin(nb)[2:])]
    return fill(res, bits)

def fill(arr, bits=32):
    return [False] * (bits - len(arr)) + arr

def decrepr(arr):
    res = 0
    for k in range(len(arr)):
        if arr[len(arr) - 1 - k]:
            res += 2**k
    return str(res)

def binrepr(arr):
    res   = ''
    count = 0
    for bit in arr:
        if count == 8:
            res  += ' '
            count = 0
        res  += ('1' if bit else '0')
        count += 1
    return res

def to_signed(arr):
    """Interprète un binarray comme un entier signé (complément à 2)."""
    val = int(decrepr(arr))
    if arr[0]:  # bit de signe = 1
        val -= 2**len(arr)
    return val
