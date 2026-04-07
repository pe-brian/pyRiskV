# tomasulo/config.py

class TomasuloConfig():
    """
    Configuration complète du moteur Tomasulo.
    Tous les paramètres sont modifiables pour expérimenter.
    """

    def __init__(self):

        # ─── Reservation Stations ─────────────────────────────────
        self.rs_alu_size = 4
        self.rs_mul_size = 2
        self.rs_mem_size = 4

        # ─── Reorder Buffer ───────────────────────────────────────
        self.rob_size    = 16

        # ─── Register file physique ───────────────────────────────
        self.phys_regs   = 64

        # ─── Unités fonctionnelles ────────────────────────────────
        self.alu_units   = 2
        self.mul_units   = 1
        self.mem_units   = 1

        # ─── Superscalarité ───────────────────────────────────────
        self.issue_width  = 1  # instructions émises par cycle
        self.commit_width = 1  # instructions commitées par cycle

        # ─── Latences (cycles) ────────────────────────────────────
        self.latency = {
            'ADD':   1, 'SUB':   1, 'AND':  1,
            'OR':    1, 'XOR':   1, 'SLL':  1,
            'SRL':   1, 'SRA':   1, 'SLT':  1,
            'SLTU':  1, 'ADDI':  1, 'ANDI': 1,
            'ORI':   1, 'XORI':  1, 'SLTI': 1,
            'SLTIU': 1, 'SLLI':  1, 'SRLI': 1,
            'SRAI':  1, 'LUI':   1, 'AUIPC':1,
            'MUL':   3, 'MULH':  3, 'MULHU':3, 'MULHSU':3,
            'DIV':  20, 'DIVU': 20, 'REM': 20, 'REMU':  20,
            'LW':    3, 'LH':    3, 'LB':   3,
            'LHU':   3, 'LBU':   3,
            'SW':    3, 'SH':    3, 'SB':   3,
            'JAL':   1, 'JALR':  1,
            'BEQ':   1, 'BNE':   1, 'BLT':  1,
            'BGE':   1, 'BLTU':  1, 'BGEU': 1,
        }

        # ─── Common Data Bus ──────────────────────────────────────
        self.cdb_width = 1

    def get_latency(self, op):
        return self.latency.get(op, 1)

    def get_rs_for_op(self, op):
        if op in ('MUL','MULH','MULHU','MULHSU','DIV','DIVU','REM','REMU'):
            return 'mul'
        if op in ('LW','LH','LB','LHU','LBU','SW','SH','SB'):
            return 'mem'
        return 'alu'

    def rs_size(self, rs_name):
        return {
            'alu': self.rs_alu_size,
            'mul': self.rs_mul_size,
            'mem': self.rs_mem_size,
        }[rs_name]

    def dump(self):
        print(f"─── Tomasulo config ──────────────────────────────────")
        print(f"  RS ALU      : {self.rs_alu_size} entrées × {self.alu_units} unités")
        print(f"  RS MUL      : {self.rs_mul_size} entrées × {self.mul_units} unités")
        print(f"  RS MEM      : {self.rs_mem_size} entrées × {self.mem_units} unités")
        print(f"  ROB         : {self.rob_size} entrées")
        print(f"  Registres   : {self.phys_regs} physiques / 32 architecturaux")
        print(f"  issue width : {self.issue_width}")
        print(f"  commit width: {self.commit_width}")
        print(f"  CDB width   : {self.cdb_width}")
        print(f"  Latences    : MUL={self.get_latency('MUL')}cy "
              f"DIV={self.get_latency('DIV')}cy "
              f"LW={self.get_latency('LW')}cy")
        print(f"─────────────────────────────────────────────────────")
