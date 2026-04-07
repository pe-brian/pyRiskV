import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from branch_predictor import StaticNotTaken, StaticTaken, Bimodal, BTB
from registers import Registers
from decoder import decode
from alu import ALU


class Instruction():
    def __init__(self):
        self.raw              = 0
        self.decoded          = None
        self.alu_result       = 0
        self.mem_result       = 0
        self.pc               = 0
        self.nop              = True
        self.predicted        = False
        self.predicted_target = None

    def __repr__(self):
        if self.nop:
            return 'NOP'
        return self.decoded['name'] if self.decoded else '???'


class Pipeline():
    def __init__(self, mem, clock_hz=1_000_000, predictor=None, forwarding=True, btb_size=16):
        self.mem  = mem
        self.regs = Registers()
        self.regs.write(2, mem.size - 4)  # sp = sommet de la mémoire
        self.pc           = 0
        self.halt         = False
        self.IF_ID        = Instruction()
        self.ID_EX        = Instruction()
        self.EX_MEM       = Instruction()
        self.MEM_WB       = Instruction()
        self.cycles       = 0
        self.instructions = 0
        self.clock_hz     = clock_hz
        self.predictor    = predictor or StaticNotTaken()
        self.branch_penalties = 0  # cycles perdus à cause des branchements
        self.forwarding_enabled = forwarding
        self.btb_enabled        = True
        self.btb                = BTB(size=btb_size) if self.btb_enabled else None

    def elapsed_ns(self):
        return (self.cycles / self.clock_hz) * 1e9

    def elapsed_us(self):
        return (self.cycles / self.clock_hz) * 1e6

    def elapsed_ms(self):
        return (self.cycles / self.clock_hz) * 1e3

    def stage_fetch(self):
        if self.halt or self.pc >= self.mem.size:
            return Instruction()

        instr     = Instruction()
        # read_word peut retourner (valeur, latence) ou juste valeur
        result    = self.mem.read_word(self.pc, track=False) \
                    if hasattr(self.mem, '_access_latency') \
                    else self.mem.read_word(self.pc)
        instr.raw = result[0] if isinstance(result, tuple) else result
        instr.pc  = self.pc
        instr.nop = False

        # BTB
        if self.btb_enabled and self.btb:
            target = self.btb.lookup(self.pc)
        if target is not None:
            predicted              = self.predictor.predict(self.pc)
            instr.predicted        = predicted
            instr.predicted_target = target
            if predicted:
                self.pc = target
            else:
                self.pc += 4
        else:
            instr.predicted        = False
            instr.predicted_target = None
            self.pc += 4

        return instr

    def stage_decode(self, instr):
        if instr.nop:
            return instr
        instr.decoded      = decode(instr.raw)
        rs1                = instr.decoded['rs1']
        rs2                = instr.decoded['rs2']
        instr.decoded['a'] = 0
        instr.decoded['b'] = 0
        return instr

    def stage_execute(self, instr):
        if instr.nop:
            return instr
        d    = instr.decoded
        name = d['name']
        imm  = d['imm']
        a = self._forward(d['rs1'], self.regs.read(d['rs1']))
        b = self._forward(d['rs2'], self.regs.read(d['rs2']))
        instr.decoded['a'] = a  # ← sauvegarde la valeur forwarded
        instr.decoded['b'] = b  # ← sauvegarde la valeur forwarded
        if name in ('ADD','SUB','AND','OR','XOR','SLL','SRL','SRA','SLT','SLTU',
                    'MUL','MULH','MULHU','MULHSU','DIV','DIVU','REM','REMU'):
            shamt = b & 0x1F if name in ('SLL','SRL','SRA') else 0
            instr.alu_result = ALU(a, b, name, shamt)
        elif name in ('ADDI','ANDI','ORI','XORI','SLTI','SLTIU'):
            op_map = {
                'ADDI':  'ADD',
                'ANDI':  'AND',
                'ORI':   'OR',
                'XORI':  'XOR',
                'SLTI':  'SLT',
                'SLTIU': 'SLTU',
            }
            instr.alu_result = ALU(a, imm, op_map[name])
        elif name in ('SLLI','SRLI','SRAI'):
            instr.alu_result = ALU(a, 0, name[:-1], imm & 0x1F)
        elif name in ('LW','LH','LB','LHU','LBU','SW','SH','SB'):
            instr.alu_result = (a + imm) & 0xFFFFFFFF
        elif name in ('BEQ','BNE','BLT','BGE','BLTU','BGEU'):
            taken  = self._branch_taken(name, a, b)
            target = (instr.pc + imm) & 0xFFFFFFFF

            if self.btb_enabled and self.btb:
                self.btb.update(instr.pc, target)

            # si première rencontre — pas encore dans le BTB
            # on compte quand même la prédiction
            if not instr.predicted_target:
                self.predictor.predict(instr.pc)

            predicted = instr.predicted
            self.predictor.update(instr.pc, taken)

            if taken != predicted:
                self.pc    = target if taken else (instr.pc + 4)
                self.IF_ID = Instruction()
                self.branch_penalties += 1
        elif name == 'LUI':
            instr.alu_result = imm & 0xFFFFFFFF
        elif name == 'AUIPC':
            instr.alu_result = (instr.pc + imm) & 0xFFFFFFFF
        elif name == 'JAL':
            instr.alu_result = instr.pc + 4
            self.pc    = (instr.pc + imm) & 0xFFFFFFFF
            self.IF_ID = Instruction()
        elif name == 'JALR':
            instr.alu_result = instr.pc + 4
            self.pc    = (a + imm) & 0xFFFFFFFE
            self.IF_ID = Instruction()
        elif name == 'EBREAK':
            self.halt = True
            self.IF_ID = Instruction()
            self.ID_EX = Instruction()
        return instr
    
    def _forward(self, reg, val):
        NO_WRITEBACK = ('SW','SH','SB','BEQ','BNE','BLT','BGE',
                    'BLTU','BGEU','ECALL','EBREAK','UNKNOWN')
        LOADS = ('LW','LH','LB','LHU','LBU')

        # forwarding depuis EX_MEM — PAS pour les loads (donnée pas encore dispo)
        if not self.EX_MEM.nop and self.EX_MEM.decoded:
            name = self.EX_MEM.decoded.get('name', '')
            rd   = self.EX_MEM.decoded.get('rd', 0)
            if rd != 0 and rd == reg and name not in NO_WRITEBACK:
                if name not in LOADS:  # ← exclut les loads
                    return self.EX_MEM.alu_result

        # forwarding depuis MEM_WB — OK pour les loads (mem_result disponible)
        if not self.MEM_WB.nop and self.MEM_WB.decoded:
            name = self.MEM_WB.decoded.get('name', '')
            rd   = self.MEM_WB.decoded.get('rd', 0)
            if rd != 0 and rd == reg and name not in NO_WRITEBACK:
                if name in LOADS:
                    return self.MEM_WB.mem_result
                return self.MEM_WB.alu_result

        return val

    def _branch_taken(self, name, a, b):
        a_s = a if a < 0x80000000 else a - 0x100000000
        b_s = b if b < 0x80000000 else b - 0x100000000
        if name == 'BEQ':  return a == b
        if name == 'BNE':  return a != b
        if name == 'BLT':  return a_s < b_s
        if name == 'BGE':  return a_s >= b_s
        if name == 'BLTU': return a < b
        if name == 'BGEU': return a >= b
        return False

    def stage_memory(self, instr):
        if instr.nop:
            return instr

        name    = instr.decoded['name']
        addr    = instr.alu_result
        b       = instr.decoded['b']
        latency = 0

        if name == 'LW':
            result = self.mem.read_word(addr)
            if isinstance(result, tuple):
                val, latency = result
            else:
                val, latency = result, 0
            instr.mem_result = val
        elif name == 'LH':
            val = self.mem.read_half(addr)
            instr.mem_result = val - 0x10000 if val & 0x8000 else val
            latency = self.mem._access_latency(addr) if hasattr(self.mem, '_access_latency') else 0
        elif name == 'LB':
            val = self.mem.read_byte(addr)
            instr.mem_result = val - 0x100 if val & 0x80 else val
        elif name == 'LHU':
            instr.mem_result = self.mem.read_half(addr)
        elif name == 'LBU':
            instr.mem_result = self.mem.read_byte(addr)
        elif name == 'SW':
            latency = self.mem.write_word(addr, b) if hasattr(self.mem, '_access_latency') else 0
            if not hasattr(self.mem, '_access_latency'):
                self.mem.write_word(addr, b)
        elif name == 'SH':
            self.mem.write_half(addr, b & 0xFFFF)
        elif name == 'SB':
            self.mem.write_byte(addr, b & 0xFF)
        else:
            instr.mem_result = instr.alu_result

        # stall cycles supplémentaires pour la latence mémoire
        if latency > 1:
            self.cycles      += latency - 1
            if hasattr(self.mem, 'stall_cycles'):
                self.mem.stall_cycles += latency - 1

        return instr

    def stage_writeback(self, instr):
        if instr.nop:
            return
        name = instr.decoded['name']
        rd   = instr.decoded['rd']

        if name == 'ECALL':          # ← déplacé ici
            self._ecall()
            self.instructions += 1
            return

        if name in ('LW','LH','LB','LHU','LBU'):
            self.regs.write(rd, instr.mem_result & 0xFFFFFFFF)
        elif name not in ('SW','SH','SB','BEQ','BNE','BLT',
                        'BGE','BLTU','BGEU','EBREAK'):
            self.regs.write(rd, instr.alu_result)
        self.instructions += 1

    def _ecall(self):
        syscall = self.regs.read(17)
        if syscall == 93:
            self.halt  = True
            self.IF_ID = Instruction()
            self.ID_EX = Instruction()
        elif syscall == 64:
            print(f"[out] {self.regs.read(10)}")

    def detect_load_use_hazard(self):
        """
        Détecte un load-use hazard :
        une instruction LW en ID_EX suivie d'une instruction
        qui utilise son résultat en IF_ID.
        """
        if self.ID_EX.nop or self.IF_ID.nop:
            return False
        if self.IF_ID.decoded is None:
            return False

        producer = self.ID_EX.decoded
        consumer = self.IF_ID.decoded

        if producer is None:
            return False

        # le producteur est-il un load ?
        if producer['name'] not in ('LW','LH','LB','LHU','LBU'):
            return False

        rd  = producer.get('rd', 0)
        rs1 = consumer.get('rs1', 0)
        rs2 = consumer.get('rs2', 0)

        return rd != 0 and (rd == rs1 or rd == rs2)

    def tick(self):
        self.stage_writeback(self.MEM_WB)
        self.MEM_WB = self.stage_memory(self.EX_MEM)

        if self.detect_load_use_hazard():
            # stall — fige IF et ID, insère bulle en EX
            self.EX_MEM = self.stage_execute(Instruction())
            # IF_ID et ID_EX restent inchangés
        else:
            self.EX_MEM = self.stage_execute(self.ID_EX)
            self.ID_EX  = self.stage_decode(self.IF_ID)
            self.IF_ID  = self.stage_fetch()

        self.cycles += 1

    def run(self, max_cycles=500000, debug=False):
        drain = 0
        while self.cycles < max_cycles:
            if debug:
                print(f"cycle {self.cycles:4} | IF={self.IF_ID}  ID={self.ID_EX}  EX={self.EX_MEM}  MEM={self.MEM_WB}")
            self.tick()
            if self.halt:
                drain += 1
                if drain >= 4:
                    break
        ipc = self.instructions / self.cycles if self.cycles else 0
        freq = self.clock_hz / 1e6
        print(f"cycles       : {self.cycles}")
        print(f"instructions : {self.instructions}")
        print(f"IPC          : {ipc:.2f}  (ideal = 1.00)")
        print(f"fréquence    : {freq:.0f} MHz")
        print(f"temps simulé : {self.elapsed_us():.3f} µs")
        print()
        print("─── branch predictor ────────────────────────────────")
        self.predictor.dump()
        print(f"  pénalités    : {self.branch_penalties} cycles perdus")
        return self.cycles