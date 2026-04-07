class Registers():
    def __init__(self):
        self.regs = [0] * 32  # 32 registres de 32 bits

        # noms symboliques RISC-V ABI
        self.names = {
            0:  'zero', 1:  'ra',  2:  'sp',  3:  'gp',
            4:  'tp',   5:  't0',  6:  't1',  7:  't2',
            8:  's0',   9:  's1',  10: 'a0',  11: 'a1',
            12: 'a2',   13: 'a3',  14: 'a4',  15: 'a5',
            16: 'a6',   17: 'a7',  18: 's2',  19: 's3',
            20: 's4',   21: 's5',  22: 's6',  23: 's7',
            24: 's8',   25: 's9',  26: 's10', 27: 's11',
            28: 't3',   29: 't4',  30: 't5',  31: 't6',
        }

    def read(self, addr):
        if addr == 0:
            return 0  # x0 hardwired à 0
        return self.regs[addr] & 0xFFFFFFFF

    def write(self, addr, value):
        if addr == 0:
            return  # x0 en lecture seule — ignoré silencieusement
        self.regs[addr] = value & 0xFFFFFFFF

    def dump(self):
        print("─── registres ───────────────────────────────────────────")
        for i in range(0, 32, 2):
            n0   = self.names[i]
            n1   = self.names[i + 1]
            v0   = self.read(i)
            v1   = self.read(i + 1)
            print(f"  x{i:<2} ({n0:<4}) = {v0:#010x} ({v0:<12})  "
                  f"x{i+1:<2} ({n1:<4}) = {v1:#010x} ({v1})")
        print("─────────────────────────────────────────────────────────")
