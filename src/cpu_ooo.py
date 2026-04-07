# cpu_ooo.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from decoder import decode
from tomasulo.config import TomasuloConfig
from tomasulo.rob import ReorderBuffer
from tomasulo.rs import ReservationStations
from tomasulo.rat import RegisterAliasTable
from tomasulo.cdb import CommonDataBus
from tomasulo.functional_unit import FunctionalUnits


class CPUOutOfOrder():
    """
    CPU Out-of-Order avec algorithme de Tomasulo.

    Superscalarité : issue_width et commit_width configurables
    dans TomasuloConfig.

    Cycle par cycle :
    1. COMMIT    — commite jusqu'à commit_width instructions
    2. ISSUE     — émet jusqu'à issue_width instructions
    3. WRITEBACK — les unités fonctionnelles terminent → CDB
    4. EXECUTE   — lance les instructions prêtes dans les RS
    5. FETCH     — fetch la prochaine instruction
    """

    def __init__(self, mem, tomasulo_cfg=None, clock_hz=100_000_000):
        self.mem       = mem
        self.cfg       = tomasulo_cfg or TomasuloConfig()
        self.clock_hz  = clock_hz

        self.rob  = ReorderBuffer(self.cfg.rob_size)
        self.rs   = ReservationStations(self.cfg)
        self.rat  = RegisterAliasTable()
        self.cdb  = CommonDataBus(self.cfg.cdb_width)
        self.fu   = FunctionalUnits(self.cfg)

        self.pc        = 0
        self.halt      = False

        self.fetch_buffer      = []
        self.fetch_buffer_size = max(8, self.cfg.issue_width * 2)

        self.cycles                = 0
        self.instructions          = 0
        self.stall_cycles          = 0
        self.branch_mispredictions = 0

    def elapsed_us(self):
        return (self.cycles / self.clock_hz) * 1e6

    def _rs_name(self, op):
        return self.cfg.get_rs_for_op(op)

    def _resolve_operand(self, reg, tag):
        val, ready = self.rob.get_value(tag)
        if ready:
            return val, None
        if not self.rob.entries[tag].busy:
            return self.rat.arch_regs[reg], None
        return 0, tag

    # ─── FETCH ────────────────────────────────────────────────────

    def _fetch(self):
        while (not self.halt and
               len(self.fetch_buffer) < self.fetch_buffer_size and
               self.pc < self.mem.size):

            raw = self.mem.read_word(self.pc)
            if isinstance(raw, tuple):
                raw = raw[0]

            decoded       = decode(raw)
            decoded['pc'] = self.pc
            self.fetch_buffer.append(decoded)
            self.pc += 4

            if decoded['name'] in ('EBREAK', 'UNKNOWN'):
                break

    # ─── ISSUE (superscalaire) ────────────────────────────────────

    def _issue(self):
        """Émet jusqu'à issue_width instructions par cycle."""
        issued = 0
        for _ in range(self.cfg.issue_width):
            if not self._issue_one():
                break
            issued += 1
        return issued

    def _issue_one(self):
        """Émet une seule instruction."""
        if not self.fetch_buffer:
            return False

        instr = self.fetch_buffer[0]
        name  = instr['name']

        if name == 'ECALL':
            if self.rob.is_full():
                self.stall_cycles += 1
                return False
            rob_tag = self.rob.issue(instr, 0)
            if rob_tag is None:
                self.stall_cycles += 1
                return False
            self.rob.entries[rob_tag].ready = True
            self.fetch_buffer.pop(0)
            return True

        if name in ('EBREAK', 'UNKNOWN'):
            if self.rob.is_full():
                self.stall_cycles += 1
                return False
            rob_tag = self.rob.issue(instr, 0)
            if rob_tag is None:
                self.stall_cycles += 1
                return False
            self.rob.entries[rob_tag].ready = True
            self.fetch_buffer.pop(0)
            return True

        rs_name = self._rs_name(name)
        rs      = self.rs.get(rs_name)

        if rs.is_full() or self.rob.is_full():
            self.stall_cycles += 1
            return False

        rd      = instr.get('rd', 0)
        rob_tag = self.rob.issue(instr, rd)
        if rob_tag is None:
            self.stall_cycles += 1
            return False

        rs1 = instr.get('rs1', 0)
        rs2 = instr.get('rs2', 0)
        imm = instr.get('imm', 0)

        vj, qj = self.rat.read(rs1)
        vk, qk = self.rat.read(rs2)

        if qj is not None:
            vj, qj = self._resolve_operand(rs1, qj)
        if qk is not None:
            vk, qk = self._resolve_operand(rs2, qk)

        IMMEDIATE_OPS = {
            'ADDI', 'ANDI', 'ORI',  'XORI', 'SLTI', 'SLTIU',
            'SLLI', 'SRLI', 'SRAI',
            'LUI',  'AUIPC',
            'LW',   'LH',   'LB',   'LHU',  'LBU',
            'JAL',  'JALR',
        }

        if name in IMMEDIATE_OPS:
            vk = imm
            qk = None

        NO_DEST = {'SW','SH','SB','BEQ','BNE','BLT','BGE','BLTU','BGEU'}
        if rd != 0 and name not in NO_DEST:
            self.rat.rename(rd, rob_tag)

        rs.issue(instr, rob_tag, vj, vk, qj, qk, imm)
        self.fetch_buffer.pop(0)
        return True

    # ─── EXECUTE ──────────────────────────────────────────────────

    def _execute(self):
        for rs_name in ('alu', 'mul', 'mem'):
            rs    = self.rs.get(rs_name)
            ready = rs.get_ready_entries()
            for rs_idx, entry in ready:
                unit = self.fu.get_free(rs_name)
                if unit is None:
                    break
                latency           = self.cfg.get_latency(entry.op)
                entry.cycles_left = latency
                unit.start(rs_name, rs_idx, entry)
                entry.executing   = True

    # ─── WRITEBACK ────────────────────────────────────────────────

    def _writeback(self):
        finished = self.fu.tick(self.mem)
        for unit, result in finished:
            rs     = self.rs.get(unit.rs_name)
            rs_idx = unit.rs_idx
            op     = unit.op
            dest   = unit.dest

            if op in ('SW','SH','SB'):
                addr  = result
                value = unit.vk
                self.cdb.broadcast_store(dest, addr, value, self.rob)
                self.rob.entries[dest].ready       = True
                self.rob.entries[dest].state       = 'writeback'
                self.rob.entries[dest].store_addr  = addr
                self.rob.entries[dest].store_value = value
            else:
                self.cdb.produce(dest, result, op)

            rs.free(rs_idx)

        self.cdb.broadcast(self.rs, self.rob)

    # ─── COMMIT (superscalaire) ───────────────────────────────────

    def _commit(self):
        """Commite jusqu'à commit_width instructions par cycle."""
        committed = 0

        while (self.rob.can_commit() and
               not self.halt and
               committed < self.cfg.commit_width):

            entry = self.rob.commit()
            if entry is None:
                break

            name = entry.instr['name'] if entry.instr else ''
            rd   = entry.dest

            if entry.is_store:
                addr  = entry.store_addr
                value = entry.store_value
                if name == 'SW':
                    self.mem.write_word(addr, value)
                elif name == 'SH':
                    self.mem.write_half(addr, value & 0xFFFF)
                elif name == 'SB':
                    self.mem.write_byte(addr, value & 0xFF)

            elif name in ('BEQ','BNE','BLT','BGE','BLTU','BGEU'):
                pc_seq = (entry.instr['pc'] + 4) & 0xFFFFFFFF
                if entry.value != pc_seq:
                    self.pc = entry.value
                    self.fetch_buffer.clear()
                    self.rob.squash()
                    self.rs.squash()
                    self.fu.squash()
                    self.cdb.clear()
                    self.rat.squash()
                    self.branch_mispredictions += 1
                    self.instructions += 1
                    committed         += 1
                    return committed

            elif name == 'ECALL':
                self._handle_ecall()

            elif name in ('EBREAK', 'UNKNOWN'):
                self.halt = True

            elif name == 'JAL':
                if rd != 0:
                    self.rat.commit(rd, entry.value, entry.tag)
                target = (entry.instr['pc'] +
                          entry.instr.get('imm', 0)) & 0xFFFFFFFF
                self.pc = target
                self.fetch_buffer.clear()
                self.rob.squash()
                self.rs.squash()
                self.fu.squash()
                self.cdb.clear()
                self.rat.squash()
                self.instructions += 1
                committed         += 1
                return committed

            elif name == 'JALR':
                if rd != 0:
                    self.rat.commit(rd, entry.value, entry.tag)
                base   = self.rat.arch_regs[entry.instr.get('rs1', 0)]
                target = (base + entry.instr.get('imm', 0)) & 0xFFFFFFFE
                self.pc = target
                self.fetch_buffer.clear()
                self.rob.squash()
                self.rs.squash()
                self.fu.squash()
                self.cdb.clear()
                self.rat.squash()
                self.instructions += 1
                committed         += 1
                return committed

            else:
                self.rat.commit(rd, entry.value, entry.tag)

            self.instructions += 1
            committed         += 1

        return committed

    # ─── ECALL ────────────────────────────────────────────────────

    def _handle_ecall(self):
        syscall = self.rat.arch_regs[17]
        if syscall == 93:
            self.halt = True
        elif syscall == 64:
            val = self.rat.arch_regs[10]
            print(f"[out] {val}")

    # ─── cycle principal ──────────────────────────────────────────

    def tick(self, debug=False):
        self.rob.clear_cycle_cache()
        self._commit()
        self._issue()
        self._writeback()
        self._execute()
        self._fetch()
        self.cycles += 1
        if debug:
            self._debug_print()

    def run(self, max_cycles=500000, debug=False):
        drain = 0
        while self.cycles < max_cycles:
            self.tick(debug)
            if self.halt:
                drain += 1
                if drain >= self.cfg.rob_size:
                    break
        return self.cycles

    @property
    def regs(self):
        class RegProxy():
            def __init__(self, rat):
                self._rat = rat
            def read(self, idx):
                return self._rat.arch_regs[idx]
            def dump(self):
                self._rat.dump_full()
        return RegProxy(self.rat)

    def _debug_print(self):
        print(f"\n── cycle {self.cycles} ──────────────────────────────")
        print(f"  PC={self.pc:#010x} "
              f"fetch_buf={len(self.fetch_buffer)} "
              f"ROB={self.rob.count}/{self.rob.size} "
              f"committed={self.instructions}")
        self.rob.dump()
        self.rs.dump()
        self.cdb.dump()

    def dump_stats(self):
        print(f"\n─── Stats OoO (Tomasulo) ─────────────────────────────")
        ipc = self.instructions / self.cycles if self.cycles else 0
        print(f"  cycles       : {self.cycles}")
        print(f"  instructions : {self.instructions}")
        print(f"  IPC          : {ipc:.2f}")
        print(f"  issue width  : {self.cfg.issue_width}")
        print(f"  commit width : {self.cfg.commit_width}")
        print(f"  stalls issue : {self.stall_cycles}")
        print(f"  mispred.     : {self.branch_mispredictions}")
        self.cdb.stats()
        self.rs.stats()
        self.fu.stats()
        self.rat.stats()
        self.rob.stats()
        print(f"─────────────────────────────────────────────────────")
