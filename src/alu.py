from basics import *
from foo import *

# ─── opérations bit à bit (niveau pédagogique) ────────────────────────

def add32(a, b):
    """Addition 32 bits. a, b : listes de 32 booléens."""
    r      = False
    result = []
    for k in range(31, -1, -1):
        R, r = ADD(a[k], b[k], r)
        result = [R] + result
    return result, r

def add64(a, b):
    """Addition 64 bits — utilisée pour la multiplication."""
    r      = False
    result = []
    for k in range(63, -1, -1):
        R, r = ADD(a[k], b[k], r)
        result = [R] + result
    return result, r

def neg32(b):
    """Complément à 2 — utilisé pour la soustraction."""
    not_b     = [NOT(x) for x in b]
    one       = binarray(1, 32)
    result, _ = add32(not_b, one)
    return result

def neg64(b):
    """Complément à 2 sur 64 bits."""
    not_b     = [NOT(x) for x in b]
    one       = [False] * 63 + [True]
    result, _ = add64(not_b, one)
    return result

def and32(a, b): return [AND(a[i], b[i]) for i in range(32)]
def or32(a, b):  return [OR(a[i],  b[i]) for i in range(32)]
def xor32(a, b): return [AND(NAND(a[i], b[i]), OR(a[i], b[i])) for i in range(32)]

def sll32(a, shamt):
    if shamt == 0: return a
    return a[shamt:] + [False] * shamt

def srl32(a, shamt):
    if shamt == 0: return a
    return [False] * shamt + a[:32 - shamt]

def sra32(a, shamt):
    if shamt == 0: return a
    sign = a[0]
    return [sign] * shamt + a[:32 - shamt]

def slt32(a, b):
    sub, _ = add32(a, neg32(b))
    return binarray(1 if sub[0] else 0, 32)

def sltu32(a, b):
    va = int(decrepr(a))
    vb = int(decrepr(b))
    return binarray(1 if va < vb else 0, 32)

# ─── extension M — multiplication ─────────────────────────────────────

def mul64(a, b):
    """
    Multiplication 32x32 → 64 bits, depuis les portes logiques.

    Principe : multiplication binaire scolaire.
    Pour chaque bit i de b :
      - si le bit est 1, on additionne a décalé de i positions
      - si le bit est 0, on n'additionne rien

    Exemple :
        1011 (11)
      × 0110 (6)
      ──────
        0000   ← bit 0 = 0
       1011    ← bit 1 = 1, décalé de 1
      1011     ← bit 2 = 1, décalé de 2
     0000      ← bit 3 = 0
     ────────
     1000010   (66)
    """
    result = [False] * 64

    for i in range(32):
        # on parcourt les bits de b du moins significatif au plus significatif
        bit_index = 31 - i  # bit i de b (b[31] est le LSB)
        if b[bit_index]:
            # décale a de i positions vers la gauche dans 64 bits
            # et additionne au résultat courant
            a_extended = [False] * 32 + list(a)  # a sur 64 bits
            a_shifted  = sll64(a_extended, i)
            result, _  = add64(result, a_shifted)

    return result  # 64 bits

def sll64(a, shamt):
    """Décalage gauche 64 bits."""
    if shamt == 0: return a
    return a[shamt:] + [False] * shamt

def mul32_signed(a, b):
    """
    Multiplication signée.
    On convertit en positif, multiplie, puis applique le signe.
    """
    # signe du résultat = XOR des signes
    sign_a   = a[0]
    sign_b   = b[0]
    sign_res = AND(NAND(sign_a, sign_b), OR(sign_a, sign_b))  # XOR

    # valeurs absolues
    abs_a = neg32(a) if sign_a else a
    abs_b = neg32(b) if sign_b else b

    result64 = mul64(abs_a, abs_b)

    # applique le signe au résultat
    if sign_res:
        result64 = neg64(result64)

    return result64

# ─── extension M — division ───────────────────────────────────────────

def divmod32u(a, b):
    if not any(b):
        return [True] * 32, list(a)

    quotient = [False] * 32
    reste    = [False] * 32

    for i in range(32):
        # décale le reste d'un bit à gauche, insère le bit i du dividende
        reste = reste[1:] + [a[i]]

        # soustrait le diviseur
        sub, _ = add32(reste, neg32(b))

        # si le bit de signe est 0 → reste >= b → soustraction valide
        if not sub[0]:
            reste       = sub
            quotient[i] = True

    return quotient, reste

def divmod32s(a, b):
    """
    Division signée 32 bits — retourne (quotient, reste).
    """
    # division par zéro
    if not any(b):
        quotient = [True] * 32
        reste    = list(a)
        return quotient, reste

    sign_a   = a[0]
    sign_b   = b[0]
    sign_q   = AND(NAND(sign_a, sign_b), OR(sign_a, sign_b))  # XOR

    abs_a = neg32(a) if sign_a else a
    abs_b = neg32(b) if sign_b else b

    q, r = divmod32u(abs_a, abs_b)

    # applique les signes
    if sign_q:
        q = neg32(q)
    if sign_a:
        r = neg32(r)

    return q, r

# ─── interface ALU ────────────────────────────────────────────────────

def ALU(a, b, op, shamt=0):
    """
    a, b   : entiers 32 bits (non signés)
    op     : string — nom de l'opération
    shamt  : décalage pour SLL/SRL/SRA

    retourne : entier 32 bits
    """
    ba = binarray(a & 0xFFFFFFFF, 32)
    bb = binarray(b & 0xFFFFFFFF, 32)

    # ── RV32I ─────────────────────────────────────────────────────
    if op == 'ADD':   return int(decrepr(add32(ba, bb)[0]))
    if op == 'SUB':   return int(decrepr(add32(ba, neg32(bb))[0]))
    if op == 'AND':   return int(decrepr(and32(ba, bb)))
    if op == 'OR':    return int(decrepr(or32(ba, bb)))
    if op == 'XOR':   return int(decrepr(xor32(ba, bb)))
    if op == 'SLL':   return int(decrepr(sll32(ba, shamt & 0x1F)))
    if op == 'SRL':   return int(decrepr(srl32(ba, shamt & 0x1F)))
    if op == 'SRA':   return int(decrepr(sra32(ba, shamt & 0x1F)))
    if op == 'SLT':   return int(decrepr(slt32(ba, bb)))
    if op == 'SLTU':  return int(decrepr(sltu32(ba, bb)))

    # ── RV32M — multiplication ────────────────────────────────────
    if op == 'MUL':
        # bits bas 32 du produit — non signé suffit pour les 32 bits bas
        result64 = mul64(ba, bb)
        return int(decrepr(result64[32:]))  # bits 31:0

    if op == 'MULH':
        # bits hauts 32 du produit signé × signé
        result64 = mul32_signed(ba, bb)
        return int(decrepr(result64[:32]))  # bits 63:32

    if op == 'MULHU':
        # bits hauts 32 du produit non signé × non signé
        result64 = mul64(ba, bb)
        return int(decrepr(result64[:32]))

    if op == 'MULHSU':
        # bits hauts 32 — signé × non signé
        # a est signé, b est non signé
        sign_a   = ba[0]
        abs_a    = neg32(ba) if sign_a else ba
        result64 = mul64(abs_a, bb)
        if sign_a:
            result64 = neg64(result64)
        return int(decrepr(result64[:32]))

    # ── RV32M — division ──────────────────────────────────────────
    if op == 'DIV':
        q, _ = divmod32s(ba, bb)
        return int(decrepr(q))

    if op == 'DIVU':
        q, _ = divmod32u(ba, bb)
        return int(decrepr(q))

    if op == 'REM':
        _, r = divmod32s(ba, bb)
        return int(decrepr(r))

    if op == 'REMU':
        _, r = divmod32u(ba, bb)
        return int(decrepr(r))

    raise Exception(f"ALU: opération inconnue '{op}'")