class Memory():
    def __init__(self, size=4096):
        """
        size : nombre d'octets
        RISC-V adresse octet par octet, en little-endian.
        """
        self.size = size
        self.data = [0] * size

    def _check(self, addr):
        if addr < 0 or addr >= self.size:
            raise Exception(f"Out of memory: addr={addr:#010x}, size={self.size}")

    # ─── accès octet ──────────────────────────────────────────────

    def read_byte(self, addr):
        self._check(addr)
        return self.data[addr]

    def write_byte(self, addr, byte):
        self._check(addr)
        self.data[addr] = byte & 0xFF

    # ─── accès 16 bits (halfword) ─────────────────────────────────

    def read_half(self, addr):
        b0 = self.read_byte(addr)
        b1 = self.read_byte(addr + 1)
        return b0 | (b1 << 8)

    def write_half(self, addr, half):
        self.write_byte(addr,     half & 0xFF)
        self.write_byte(addr + 1, (half >> 8) & 0xFF)

    # ─── accès 32 bits (word) ─────────────────────────────────────

    def read_word(self, addr):
        b0 = self.read_byte(addr)
        b1 = self.read_byte(addr + 1)
        b2 = self.read_byte(addr + 2)
        b3 = self.read_byte(addr + 3)
        return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)

    def write_word(self, addr, word):
        self.write_byte(addr,     word & 0xFF)
        self.write_byte(addr + 1, (word >> 8)  & 0xFF)
        self.write_byte(addr + 2, (word >> 16) & 0xFF)
        self.write_byte(addr + 3, (word >> 24) & 0xFF)

    # ─── chargement binaire ───────────────────────────────────────

    def load_binary(self, path, start=0):
        """Charge un fichier .bin en mémoire à partir de l'adresse start."""
        with open(path, 'rb') as f:
            data = f.read()
        for i, byte in enumerate(data):
            self.write_byte(start + i, byte)
        return len(data)

    def dump(self, start=0, length=64):
        """Affiche length octets depuis start, format hexdump."""
        print(f"─── mémoire [{start:#06x} - {start+length:#06x}] ───")
        for i in range(0, length, 16):
            addr = start + i
            hex_part = ' '.join(f'{self.read_byte(addr+j):02x}'
                                for j in range(16) if addr+j < self.size)
            print(f"  {addr:#06x}  {hex_part}")
        print("─" * 40)
