def decode(instruction):
    """
    Décode une instruction RV32I.

    instruction : entier 32 bits (lu depuis la mémoire)
    retourne    : dict avec tous les champs décodés
    """

    # ─── champs communs ───────────────────────────────────────────
    opcode = instruction & 0x7F
    rd     = (instruction >> 7)  & 0x1F
    funct3 = (instruction >> 12) & 0x07
    rs1    = (instruction >> 15) & 0x1F
    rs2    = (instruction >> 20) & 0x1F
    funct7 = (instruction >> 25) & 0x7F

    # ─── immédiats selon le format ────────────────────────────────

    # Type I : bits [31:20]
    imm_i = instruction >> 20
    if imm_i & 0x800:
        imm_i -= 0x1000

    # Type S : bits [31:25] et [11:7]
    imm_s = ((instruction >> 25) << 5) | ((instruction >> 7) & 0x1F)
    if imm_s & 0x800:
        imm_s -= 0x1000

    # Type B : bits éparpillés — 12|10:5|4:1|11
    imm_b = (
        ((instruction >> 31) & 1) << 12 |
        ((instruction >> 7)  & 1) << 11 |
        ((instruction >> 25) & 0x3F) << 5 |
        ((instruction >> 8)  & 0xF)  << 1
    )
    if imm_b & 0x1000:
        imm_b -= 0x2000

    # Type U : bits [31:12]
    imm_u = instruction & 0xFFFFF000

    # Type J : bits éparpillés — 20|10:1|11|19:12
    imm_j = (
        ((instruction >> 31) & 1)    << 20 |
        ((instruction >> 12) & 0xFF) << 12 |
        ((instruction >> 20) & 1)    << 11 |
        ((instruction >> 21) & 0x3FF) << 1
    )
    if imm_j & 0x100000:
        imm_j -= 0x200000

    # ─── résultat par défaut ──────────────────────────────────────
    result = {
        'raw':    instruction,
        'opcode': opcode,
        'rd':     rd,
        'rs1':    rs1,
        'rs2':    rs2,
        'funct3': funct3,
        'funct7': funct7,
        'imm':    0,
        'name':   'UNKNOWN',
        'type':   '?',
    }

    # ─── décodage par opcode ──────────────────────────────────────

    # Type R — opérations registre à registre
    if opcode == 0x33:
        result['type'] = 'R'
        if funct7 == 0x01:  # extension M
            if   funct3 == 0x0: result['name'] = 'MUL'
            elif funct3 == 0x1: result['name'] = 'MULH'
            elif funct3 == 0x2: result['name'] = 'MULHSU'
            elif funct3 == 0x3: result['name'] = 'MULHU'
            elif funct3 == 0x4: result['name'] = 'DIV'
            elif funct3 == 0x5: result['name'] = 'DIVU'
            elif funct3 == 0x6: result['name'] = 'REM'
            elif funct3 == 0x7: result['name'] = 'REMU'
        else:               # RV32I
            if   funct3 == 0x0 and funct7 == 0x00: result['name'] = 'ADD'
            elif funct3 == 0x0 and funct7 == 0x20: result['name'] = 'SUB'
            elif funct3 == 0x4 and funct7 == 0x00: result['name'] = 'XOR'
            elif funct3 == 0x6 and funct7 == 0x00: result['name'] = 'OR'
            elif funct3 == 0x7 and funct7 == 0x00: result['name'] = 'AND'
            elif funct3 == 0x1 and funct7 == 0x00: result['name'] = 'SLL'
            elif funct3 == 0x5 and funct7 == 0x00: result['name'] = 'SRL'
            elif funct3 == 0x5 and funct7 == 0x20: result['name'] = 'SRA'
            elif funct3 == 0x2 and funct7 == 0x00: result['name'] = 'SLT'
            elif funct3 == 0x3 and funct7 == 0x00: result['name'] = 'SLTU'

    # Type I — arithmétique immédiate
    elif opcode == 0x13:
        result['type'] = 'I'
        result['imm']  = imm_i
        if   funct3 == 0x0: result['name'] = 'ADDI'
        elif funct3 == 0x4: result['name'] = 'XORI'
        elif funct3 == 0x6: result['name'] = 'ORI'
        elif funct3 == 0x7: result['name'] = 'ANDI'
        elif funct3 == 0x1: result['name'] = 'SLLI'
        elif funct3 == 0x5:
            result['name'] = 'SRLI' if funct7 == 0x00 else 'SRAI'
        elif funct3 == 0x2: result['name'] = 'SLTI'
        elif funct3 == 0x3: result['name'] = 'SLTIU'

    # Type I — load
    elif opcode == 0x03:
        result['type'] = 'I'
        result['imm']  = imm_i
        if   funct3 == 0x0: result['name'] = 'LB'
        elif funct3 == 0x1: result['name'] = 'LH'
        elif funct3 == 0x2: result['name'] = 'LW'
        elif funct3 == 0x4: result['name'] = 'LBU'
        elif funct3 == 0x5: result['name'] = 'LHU'

    # Type S — store
    elif opcode == 0x23:
        result['type'] = 'S'
        result['imm']  = imm_s
        if   funct3 == 0x0: result['name'] = 'SB'
        elif funct3 == 0x1: result['name'] = 'SH'
        elif funct3 == 0x2: result['name'] = 'SW'

    # Type B — branchement conditionnel
    elif opcode == 0x63:
        result['type'] = 'B'
        result['imm']  = imm_b
        if   funct3 == 0x0: result['name'] = 'BEQ'
        elif funct3 == 0x1: result['name'] = 'BNE'
        elif funct3 == 0x4: result['name'] = 'BLT'
        elif funct3 == 0x5: result['name'] = 'BGE'
        elif funct3 == 0x6: result['name'] = 'BLTU'
        elif funct3 == 0x7: result['name'] = 'BGEU'

    # Type U — LUI
    elif opcode == 0x37:
        result['type'] = 'U'
        result['imm']  = imm_u
        result['name'] = 'LUI'

    # Type U — AUIPC
    elif opcode == 0x17:
        result['type'] = 'U'
        result['imm']  = imm_u
        result['name'] = 'AUIPC'

    # Type J — JAL
    elif opcode == 0x6F:
        result['type'] = 'J'
        result['imm']  = imm_j
        result['name'] = 'JAL'

    # Type I — JALR
    elif opcode == 0x67:
        result['type'] = 'I'
        result['imm']  = imm_i
        result['name'] = 'JALR'

    # SYSTEM — ECALL / EBREAK
    elif opcode == 0x73:
        result['type'] = 'N'
        result['name'] = 'ECALL' if (instruction >> 20) == 0 else 'EBREAK'

    return result
