import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from registers import Registers
from decoder import decode
from alu import ALU


class CPU():
    def __init__(self, mem, clock_hz=1_000_000):
        self.mem  = mem
        self.regs = Registers()
        self.regs.write(2, mem.size - 4)  # sp = sommet de la mémoire
        self.pc    = 0
        self.halt  = False
        self.cycles = 0
        self.clock_hz = clock_hz

        # cycles par type d'instruction (approximation)
        self._cycles_table = {
            'ADD': 1, 'SUB': 1, 'AND': 1, 'OR':  1, 'XOR':  1,
            'SLL': 1, 'SRL': 1, 'SRA': 1, 'SLT': 1, 'SLTU': 1,
            'ADDI':1, 'ANDI':1, 'ORI': 1, 'XORI':1, 'SLTI': 1,
            'SLLI':1, 'SRLI':1, 'SRAI':1,
            'LW':  3, 'LH':  3, 'LB':  3, 'LHU': 3, 'LBU':  3,
            'SW':  3, 'SH':  3, 'SB':  3,
            'BEQ': 1, 'BNE': 1, 'BLT': 1, 'BGE': 1, 'BLTU': 1, 'BGEU': 1,
            'JAL': 2, 'JALR':2,
            'LUI': 1, 'AUIPC':1,
            'ECALL': 1,
        }

    def elapsed_ns(self):
        return (self.cycles / self.clock_hz) * 1e9

    def elapsed_us(self):
        return (self.cycles / self.clock_hz) * 1e6

    def elapsed_ms(self):
        return (self.cycles / self.clock_hz) * 1e3

    # ─── fetch ────────────────────────────────────────────────────

    def fetch(self):
        instr   = self.mem.read_word(self.pc)
        self.pc += 4
        return instr

    # ─── execute ──────────────────────────────────────────────────

    def execute(self, decoded):
        name   = decoded['name']
        rd     = decoded['rd']
        rs1    = decoded['rs1']
        rs2    = decoded['rs2']
        imm    = decoded['imm']

        a = self.regs.read(rs1)
        b = self.regs.read(rs2)

        # ── Type R ────────────────────────────────────────────────
        if name == 'ADD':
            self.regs.write(rd, ALU(a, b, 'ADD'))
        elif name == 'SUB':
            self.regs.write(rd, ALU(a, b, 'SUB'))
        elif name == 'AND':
            self.regs.write(rd, ALU(a, b, 'AND'))
        elif name == 'OR':
            self.regs.write(rd, ALU(a, b, 'OR'))
        elif name == 'XOR':
            self.regs.write(rd, ALU(a, b, 'XOR'))
        elif name == 'SLL':
            self.regs.write(rd, ALU(a, b, 'SLL', b & 0x1F))
        elif name == 'SRL':
            self.regs.write(rd, ALU(a, b, 'SRL', b & 0x1F))
        elif name == 'SRA':
            self.regs.write(rd, ALU(a, b, 'SRA', b & 0x1F))
        elif name == 'SLT':
            self.regs.write(rd, ALU(a, b, 'SLT'))
        elif name == 'SLTU':
            self.regs.write(rd, ALU(a, b, 'SLTU'))

        # ── Extension M ───────────────────────────────────────────
        elif name == 'MUL':
            self.regs.write(rd, ALU(a, b, 'MUL'))
        elif name == 'MULH':
            self.regs.write(rd, ALU(a, b, 'MULH'))
        elif name == 'MULHU':
            self.regs.write(rd, ALU(a, b, 'MULHU'))
        elif name == 'MULHSU':
            self.regs.write(rd, ALU(a, b, 'MULHSU'))
        elif name == 'DIV':
            self.regs.write(rd, ALU(a, b, 'DIV'))
        elif name == 'DIVU':
            self.regs.write(rd, ALU(a, b, 'DIVU'))
        elif name == 'REM':
            self.regs.write(rd, ALU(a, b, 'REM'))
        elif name == 'REMU':
            self.regs.write(rd, ALU(a, b, 'REMU'))

        # ── Type I — arithmétique ──────────────────────────────────
        elif name == 'ADDI':
            self.regs.write(rd, ALU(a, imm, 'ADD'))
        elif name == 'ANDI':
            self.regs.write(rd, ALU(a, imm, 'AND'))
        elif name == 'ORI':
            self.regs.write(rd, ALU(a, imm, 'OR'))
        elif name == 'XORI':
            self.regs.write(rd, ALU(a, imm, 'XOR'))
        elif name == 'SLTI':
            self.regs.write(rd, ALU(a, imm, 'SLT'))
        elif name == 'SLTIU':
            self.regs.write(rd, ALU(a, imm, 'SLTU'))
        elif name == 'SLLI':
            self.regs.write(rd, ALU(a, 0, 'SLL', imm & 0x1F))
        elif name == 'SRLI':
            self.regs.write(rd, ALU(a, 0, 'SRL', imm & 0x1F))
        elif name == 'SRAI':
            self.regs.write(rd, ALU(a, 0, 'SRA', imm & 0x1F))

        # ── Type I — load ──────────────────────────────────────────
        elif name == 'LW':
            addr = (a + imm) & 0xFFFFFFFF
            self.regs.write(rd, self.mem.read_word(addr))

        elif name == 'LH':
            addr = (a + imm) & 0xFFFFFFFF
            val  = self.mem.read_half(addr)
            if val & 0x8000: val -= 0x10000
            self.regs.write(rd, val & 0xFFFFFFFF)

        elif name == 'LB':
            addr = (a + imm) & 0xFFFFFFFF
            val  = self.mem.read_byte(addr)
            if val & 0x80: val -= 0x100
            self.regs.write(rd, val & 0xFFFFFFFF)

        elif name == 'LHU':
            addr = (a + imm) & 0xFFFFFFFF
            self.regs.write(rd, self.mem.read_half(addr))

        elif name == 'LBU':
            addr = (a + imm) & 0xFFFFFFFF
            self.regs.write(rd, self.mem.read_byte(addr))

        # ── Type S — store ─────────────────────────────────────────
        elif name == 'SW':
            addr = (a + imm) & 0xFFFFFFFF
            self.mem.write_word(addr, b)

        elif name == 'SH':
            addr = (a + imm) & 0xFFFFFFFF
            self.mem.write_half(addr, b & 0xFFFF)

        elif name == 'SB':
            addr = (a + imm) & 0xFFFFFFFF
            self.mem.write_byte(addr, b & 0xFF)

        # ── Type B — branchement ───────────────────────────────────
        elif name == 'BEQ':
            if a == b:
                self.pc = (self.pc - 4 + imm) & 0xFFFFFFFF

        elif name == 'BNE':
            if a != b:
                self.pc = (self.pc - 4 + imm) & 0xFFFFFFFF

        elif name == 'BLT':
            a_s = a if a < 0x80000000 else a - 0x100000000
            b_s = b if b < 0x80000000 else b - 0x100000000
            if a_s < b_s:
                self.pc = (self.pc - 4 + imm) & 0xFFFFFFFF

        elif name == 'BGE':
            a_s = a if a < 0x80000000 else a - 0x100000000
            b_s = b if b < 0x80000000 else b - 0x100000000
            if a_s >= b_s:
                self.pc = (self.pc - 4 + imm) & 0xFFFFFFFF

        elif name == 'BLTU':
            if a < b:
                self.pc = (self.pc - 4 + imm) & 0xFFFFFFFF

        elif name == 'BGEU':
            if a >= b:
                self.pc = (self.pc - 4 + imm) & 0xFFFFFFFF

        # ── Type U ────────────────────────────────────────────────
        elif name == 'LUI':
            self.regs.write(rd, imm & 0xFFFFFFFF)

        elif name == 'AUIPC':
            self.regs.write(rd, (self.pc - 4 + imm) & 0xFFFFFFFF)

        # ── Type J ────────────────────────────────────────────────
        elif name == 'JAL':
            self.regs.write(rd, self.pc)
            self.pc = (self.pc - 4 + imm) & 0xFFFFFFFF

        elif name == 'JALR':
            next_pc = self.pc
            self.pc = (a + imm) & 0xFFFFFFFE
            self.regs.write(rd, next_pc)

        # ── SYSTEM ────────────────────────────────────────────────
        elif name == 'ECALL':
            self._ecall()

        elif name in ('HLT', 'EBREAK'):
            self.halt = True

        elif name == 'UNKNOWN':
            raise Exception(
                f"Instruction inconnue: {decoded['raw']:#010x} "
                f"au PC={self.pc - 4:#010x}"
            )

        # comptage des cycles
        self.cycles += self._cycles_table.get(name, 1)

    def _ecall(self):
        """
        Gestion simplifiée des appels système RISC-V Linux.
        a7 (x17) = numéro de syscall
        a0 (x10) = argument principal / valeur de retour
        """
        syscall = self.regs.read(17)

        if syscall == 93:    # exit
            self.halt = True

        elif syscall == 64:  # write (simplifié — affiche a0)
            val = self.regs.read(10)
            print(f"[out] {val}")

        else:
            print(f"[ecall] syscall {syscall} non implémenté")

    # ─── cycle principal ──────────────────────────────────────────

    def step(self):
        """Un seul cycle fetch/decode/execute."""
        instr   = self.fetch()
        decoded = decode(instr)
        self.execute(decoded)
        return decoded

    def run(self, max_steps=100000, debug=False):
        """Exécute jusqu'à HLT ou max_steps instructions."""
        steps = 0
        while not self.halt and steps < max_steps:
            pc_before = self.pc
            decoded   = self.step()

            if debug:
                name = decoded['name']
                rd   = decoded['rd']
                rs1  = decoded['rs1']
                rs2  = decoded['rs2']
                imm  = decoded['imm']
                print(
                    f"PC={pc_before:#010x} | {name:<6} | "
                    f"x{rd}={self.regs.read(rd):#010x}  "
                    f"x{rs1}={self.regs.read(rs1):#010x}  "
                    f"x{rs2}={self.regs.read(rs2):#010x}  "
                    f"imm={imm}"
                )

            steps += 1

        if steps == max_steps:
            print(f"[!] max_steps atteint ({max_steps})")

        return steps
