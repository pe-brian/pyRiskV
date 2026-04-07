class SlowMemory():
    """
    Simulation d'une RAM avec latence réaliste.

    Une vraie DDR4 à 3200 MHz vue depuis un CPU à 100 MHz :
    - Latence initiale (row miss) : ~50 cycles CPU
    - Accès burst (row hit)       :  ~4 cycles CPU

    Principe du row buffer :
    La RAM est organisée en lignes (rows) de 64 octets.
    Quand on accède à une ligne pour la première fois,
    il faut l'ouvrir — c'est lent (row miss).
    Les accès suivants dans la même ligne sont rapides (row hit).
    C'est exactement ce qu'exploite le cache L1.
    """

    ROW_SIZE = 64  # octets par ligne RAM — standard DDR

    def __init__(self, size=16384,
                 latency_miss=50,   # cycles pour un row miss
                 latency_hit=4):    # cycles pour un row hit (burst)
        self.size         = size
        self.latency_miss = latency_miss
        self.latency_hit  = latency_hit
        self.data         = [0] * size

        # état du row buffer
        self.open_row     = -1   # ligne actuellement ouverte (-1 = aucune)

        # stats
        self.accesses     = 0
        self.row_hits     = 0
        self.row_misses   = 0
        self.cycles_lost  = 0
        self.stall_cycles = 0    # cycles de stall en cours

    def _check(self, addr):
        if addr < 0 or addr >= self.size:
            raise Exception(f"Out of memory: addr={addr:#010x}, size={self.size}")

    def _row(self, addr):
        return addr // self.ROW_SIZE

    def _access_latency(self, addr):
        """Calcule la latence et met à jour les stats."""
        self.accesses += 1
        row = self._row(addr)
        if row == self.open_row:
            self.row_hits   += 1
            self.cycles_lost += self.latency_hit
            return self.latency_hit
        else:
            self.row_misses  += 1
            self.open_row    = row
            self.cycles_lost += self.latency_miss
            return self.latency_miss

    # ─── accès octet ──────────────────────────────────────────────

    def read_byte(self, addr):
        self._check(addr)
        return self.data[addr]

    def write_byte(self, addr, byte):
        self._check(addr)
        self.data[addr] = byte & 0xFF

    # ─── accès 16 bits ────────────────────────────────────────────

    def read_half(self, addr):
        b0 = self.read_byte(addr)
        b1 = self.read_byte(addr + 1)
        return b0 | (b1 << 8)

    def write_half(self, addr, half):
        self.write_byte(addr,     half & 0xFF)
        self.write_byte(addr + 1, (half >> 8) & 0xFF)

    # ─── accès 32 bits avec latence ───────────────────────────────

    def read_word(self, addr, track=True):
        """
        track=True  → accès avec latence (données)
        track=False → accès sans latence (fetch instructions)
        """
        b0 = self.read_byte(addr)
        b1 = self.read_byte(addr + 1)
        b2 = self.read_byte(addr + 2)
        b3 = self.read_byte(addr + 3)
        if track:
            return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24), self._access_latency(addr)
        return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24), 0

    def write_word(self, addr, word, track=True):
        self.write_byte(addr,     word & 0xFF)
        self.write_byte(addr + 1, (word >> 8)  & 0xFF)
        self.write_byte(addr + 2, (word >> 16) & 0xFF)
        self.write_byte(addr + 3, (word >> 24) & 0xFF)
        if track:
            return self._access_latency(addr)
        return 0

    # ─── chargement binaire ───────────────────────────────────────

    def load_binary(self, path, start=0):
        with open(path, 'rb') as f:
            data = f.read()
        for i, byte in enumerate(data):
            self.write_byte(start + i, byte)
        return len(data)

    # ─── stats ────────────────────────────────────────────────────

    def dump(self):
        total = self.row_hits + self.row_misses
        hit_rate = self.row_hits / total * 100 if total else 0
        print(f"─── mémoire RAM ─────────────────────────────────────")
        print(f"  accès total  : {self.accesses}")
        print(f"  row hits     : {self.row_hits} ({hit_rate:.1f}%)")
        print(f"  row misses   : {self.row_misses} ({100-hit_rate:.1f}%)")
        print(f"  cycles perdus: {self.cycles_lost}")
        print(f"─────────────────────────────────────────────────────")