# tomasulo/functional_unit.py

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from alu import ALU


class FunctionalUnit():
    """
    Une unité fonctionnelle — exécute une instruction.

    Chaque unité est soit libre soit occupée pendant
    un certain nombre de cycles (latence de l'instruction).

    Les unités fonctionnelles sont indépendantes —
    plusieurs peuvent s'exécuter en parallèle.
    """

    def __init__(self, name, unit_id):
        self.name        = name
        self.unit_id     = unit_id
        self.busy        = False
        self.rs_idx      = None   # index dans la RS
        self.rs_name     = None   # nom de la RS ('alu', 'mul', 'mem')
        self.op          = None
        self.vj          = 0
        self.vk          = 0
        self.imm         = 0
        self.dest        = None   # tag ROB
        self.instr       = None
        self.cycles_left = 0
        self.result      = None

        # stats
        self.total_executed = 0
        self.busy_cycles    = 0
        self.idle_cycles    = 0

    def is_free(self):
        return not self.busy

    def start(self, rs_name, rs_idx, entry):
        """Lance l'exécution d'une entrée RS."""
        self.busy        = True
        self.rs_name     = rs_name
        self.rs_idx      = rs_idx
        self.op          = entry.op
        self.vj          = entry.vj
        self.vk          = entry.vk
        self.imm         = entry.imm
        self.dest        = entry.dest
        self.instr       = entry.instr
        self.cycles_left = entry.cycles_left
        self.result      = None
        self.total_executed += 1

    def tick(self, mem=None):
        """
        Avance d'un cycle.
        Retourne le résultat si terminé, None sinon.
        """
        if not self.busy:
            self.idle_cycles += 1
            return None

        self.busy_cycles += 1
        self.cycles_left -= 1

        if self.cycles_left > 0:
            return None

        self.result = self._execute(mem)
        self.busy   = False
        return self.result

    def _execute(self, mem=None):
        """Exécute l'opération et retourne le résultat."""
        op  = self.op
        a   = self.vj
        b   = self.vk
        imm = self.imm

        # ── Type R ────────────────────────────────────────────────
        if op in ('ADD','SUB','AND','OR','XOR','SLT','SLTU'):
            return ALU(a, b, op)

        if op in ('SLL','SRL','SRA'):
            return ALU(a, b, op, b & 0x1F)

        # ── Type I — arithmétique ──────────────────────────────────
        if op == 'ADDI':  return ALU(a, imm, 'ADD')
        if op == 'ANDI':  return ALU(a, imm, 'AND')
        if op == 'ORI':   return ALU(a, imm, 'OR')
        if op == 'XORI':  return ALU(a, imm, 'XOR')
        if op == 'SLTI':  return ALU(a, imm, 'SLT')
        if op == 'SLTIU': return ALU(a, imm, 'SLTU')
        if op == 'SLLI':  return ALU(a, 0, 'SLL', imm & 0x1F)
        if op == 'SRLI':  return ALU(a, 0, 'SRL', imm & 0x1F)
        if op == 'SRAI':  return ALU(a, 0, 'SRA', imm & 0x1F)

        # ── Type U ────────────────────────────────────────────────
        if op == 'LUI':
            return imm & 0xFFFFFFFF
        if op == 'AUIPC':
            pc = self.instr.get('pc', 0) if self.instr else 0
            return (pc + imm) & 0xFFFFFFFF

        # ── Extension M ───────────────────────────────────────────
        if op in ('MUL','MULH','MULHU','MULHSU',
                  'DIV','DIVU','REM','REMU'):
            return ALU(a, b, op)

        # ── Mémoire ───────────────────────────────────────────────
        if op in ('LW','LH','LB','LHU','LBU','SW','SH','SB'):
            addr = (a + imm) & 0xFFFFFFFF
            if mem is None:
                return addr
            if op == 'LW':
                result = mem.read_word(addr)
                return result[0] if isinstance(result, tuple) else result
            if op == 'LH':
                val = mem.read_half(addr)
                return val - 0x10000 if val & 0x8000 else val
            if op == 'LB':
                val = mem.read_byte(addr)
                return val - 0x100 if val & 0x80 else val
            if op == 'LHU':
                return mem.read_half(addr)
            if op == 'LBU':
                return mem.read_byte(addr)
            if op in ('SW','SH','SB'):
                return addr  # l'écriture se fait au commit

        # ── Branchements ──────────────────────────────────────────
        if op in ('BEQ','BNE','BLT','BGE','BLTU','BGEU'):
            return self._eval_branch(op, a, b, imm)

        # ── Sauts ─────────────────────────────────────────────────
        if op in ('JAL','JALR'):
            pc = self.instr.get('pc', 0) if self.instr else 0
            return (pc + 4) & 0xFFFFFFFF

        return 0

    def _eval_branch(self, op, a, b, imm):
        """Évalue un branchement — retourne l'adresse cible."""
        a_s = a if a < 0x80000000 else a - 0x100000000
        b_s = b if b < 0x80000000 else b - 0x100000000
        pc  = self.instr.get('pc', 0) if self.instr else 0

        taken = {
            'BEQ':  a == b,
            'BNE':  a != b,
            'BLT':  a_s < b_s,
            'BGE':  a_s >= b_s,
            'BLTU': a < b,
            'BGEU': a >= b,
        }.get(op, False)

        if taken:
            return (pc + imm) & 0xFFFFFFFF
        return (pc + 4) & 0xFFFFFFFF

    def dump(self):
        if self.busy:
            print(f"  {self.name}[{self.unit_id}] "
                  f"{self.op} → ROB{self.dest} "
                  f"({self.cycles_left}cy restants)")
        else:
            print(f"  {self.name}[{self.unit_id}] libre")

    def stats(self):
        total = self.busy_cycles + self.idle_cycles
        util  = self.busy_cycles / total * 100 if total else 0
        print(f"  {self.name}[{self.unit_id}] "
              f"exécuté={self.total_executed} "
              f"utilisation={util:.1f}%")


class FunctionalUnits():
    """Gestionnaire de toutes les unités fonctionnelles."""

    def __init__(self, cfg):
        self.alu_units = [
            FunctionalUnit('ALU', i)
            for i in range(cfg.alu_units)
        ]
        self.mul_units = [
            FunctionalUnit('MUL', i)
            for i in range(cfg.mul_units)
        ]
        self.mem_units = [
            FunctionalUnit('MEM', i)
            for i in range(cfg.mem_units)
        ]
        self._map = {
            'alu': self.alu_units,
            'mul': self.mul_units,
            'mem': self.mem_units,
        }

    def get_free(self, rs_name):
        """Retourne une unité fonctionnelle libre pour cette RS."""
        for unit in self._map[rs_name]:
            if unit.is_free():
                return unit
        return None

    def tick(self, mem=None):
        """
        Avance toutes les unités d'un cycle.
        Retourne les résultats terminés ce cycle.
        """
        finished = []
        for units in self._map.values():
            for unit in units:
                result = unit.tick(mem)
                if result is not None:
                    finished.append((unit, result))
        return finished

    def squash(self):
        """Annule toutes les unités en cours."""
        for units in self._map.values():
            for unit in units:
                unit.busy        = False
                unit.cycles_left = 0
                unit.result      = None

    def dump(self):
        print(f"─── Unités fonctionnelles ────────────────────────────")
        for units in self._map.values():
            for unit in units:
                unit.dump()
        print(f"─────────────────────────────────────────────────────")

    def stats(self):
        print(f"─── Stats unités fonctionnelles ──────────────────────")
        for units in self._map.values():
            for unit in units:
                unit.stats()
        print(f"─────────────────────────────────────────────────────")