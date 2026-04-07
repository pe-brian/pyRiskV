class CacheL1():
    """
    Cache L1 à correspondance directe (direct-mapped).

    Paramètres typiques d'un vrai L1 :
    - Taille : 32 Ko
    - Lignes : 64 octets
    - Latence hit  : 4 cycles
    - Latence miss : latence RAM (50-200 cycles)

    Pour notre simulateur (mémoire limitée) :
    - 64 entrées × 64 octets = 4 Ko
    - Correspondance directe — chaque adresse a une seule place possible

    Fonctionnalités :
    - Write-back  : les lignes dirty ne sont écrites en RAM qu'à l'éviction
    - Prefetching : sur un miss, charge aussi la ligne suivante en avance
    """

    LINE_SIZE   = 64    # octets par ligne
    NUM_LINES   = 64    # nombre de lignes dans le cache
    HIT_LATENCY = 1     # cycles pour un cache hit

    def __init__(self, mem, hit_latency=1, prefetch=True):
        self.mem         = mem
        self.hit_latency = hit_latency
        self.prefetch    = prefetch

        # entrées du cache
        self.valid = [False] * self.NUM_LINES
        self.tags  = [0]     * self.NUM_LINES
        self.data  = [[0] * self.LINE_SIZE for _ in range(self.NUM_LINES)]
        self.dirty = [False] * self.NUM_LINES

        # stats
        self.hits          = 0
        self.misses        = 0
        self.writebacks    = 0
        self.prefetch_hits = 0   # lignes préchargées utilisées
        self.prefetch_miss = 0   # lignes préchargées non utilisées (évincées)
        self.cycles_lost   = 0

    # ─── décomposition d'adresse ──────────────────────────────────

    def _offset(self, addr):
        return addr % self.LINE_SIZE

    def _index(self, addr):
        return (addr // self.LINE_SIZE) % self.NUM_LINES

    def _tag(self, addr):
        return addr // (self.LINE_SIZE * self.NUM_LINES)

    # ─── lookup ───────────────────────────────────────────────────

    def _lookup(self, addr):
        """Retourne True si l'adresse est dans le cache."""
        idx = self._index(addr)
        tag = self._tag(addr)
        return self.valid[idx] and self.tags[idx] == tag

    # ─── éviction write-back ──────────────────────────────────────

    def _evict(self, idx):
        """Évicte la ligne idx — write-back si dirty."""
        if self.valid[idx] and self.dirty[idx]:
            old_start = (self.tags[idx] * self.NUM_LINES + idx) * self.LINE_SIZE
            for i in range(self.LINE_SIZE):
                self.mem.write_byte(old_start + i, self.data[idx][i])
            self.dirty[idx] = False
            self.writebacks += 1

    # ─── chargement d'une ligne ───────────────────────────────────

    def _load_line(self, addr):
        """
        Charge une ligne complète depuis la RAM.
        Évicte la ligne existante avec write-back si dirty.
        Lance le prefetch de la ligne suivante si activé.
        """
        idx        = self._index(addr)
        tag        = self._tag(addr)
        line_start = addr - self._offset(addr)

        # éviction write-back si nécessaire
        self._evict(idx)

        # charge 64 octets depuis la RAM
        for i in range(self.LINE_SIZE):
            self.data[idx][i] = self.mem.read_byte(line_start + i)

        self.valid[idx] = True
        self.tags[idx]  = tag
        self.dirty[idx] = False

        # paye la latence RAM
        _, latency = self.mem.read_word(line_start, track=True)
        self.cycles_lost += latency

        # prefetch la ligne suivante si activé
        if self.prefetch:
            next_addr = line_start + self.LINE_SIZE
            if next_addr < self.mem.size and not self._lookup(next_addr):
                self._prefetch_line(next_addr)

        return latency

    # ─── prefetch d'une ligne ─────────────────────────────────────

    def _prefetch_line(self, addr):
        """
        Charge une ligne en avance — sans compter comme un miss.
        Transparent pour les stats de hit/miss.
        """
        idx        = self._index(addr)
        tag        = self._tag(addr)
        line_start = addr - self._offset(addr)

        # si la ligne va évincer une dirty — write-back
        self._evict(idx)

        for i in range(self.LINE_SIZE):
            self.data[idx][i] = self.mem.read_byte(line_start + i)

        self.valid[idx] = True
        self.tags[idx]  = tag
        self.dirty[idx] = False

    # ─── lecture ──────────────────────────────────────────────────

    def read_byte(self, addr):
        if not self._lookup(addr):
            self._load_line(addr)
            self.misses += 1
        else:
            self.hits += 1
            self.cycles_lost += self.hit_latency
        idx = self._index(addr)
        return self.data[idx][self._offset(addr)]

    def read_half(self, addr):
        b0 = self.read_byte(addr)
        b1 = self.read_byte(addr + 1)
        return b0 | (b1 << 8)

    def read_word(self, addr, track=True):
        if not track:
            return self.mem.read_word(addr, track=False)

        if not self._lookup(addr):
            latency = self._load_line(addr)
            self.misses += 1
        else:
            self.hits        += 1
            latency           = self.hit_latency
            self.cycles_lost += latency

        idx = self._index(addr)
        off = self._offset(addr)
        val = (self.data[idx][off]         |
               self.data[idx][off+1] << 8  |
               self.data[idx][off+2] << 16 |
               self.data[idx][off+3] << 24)
        return val, latency

    # ─── écriture (write-back) ────────────────────────────────────

    def write_byte(self, addr, byte):
        if not self._lookup(addr):
            self._load_line(addr)
            self.misses += 1
        else:
            self.hits += 1
        idx = self._index(addr)
        self.data[idx][self._offset(addr)] = byte & 0xFF
        self.dirty[idx] = True

    def write_half(self, addr, half):
        self.write_byte(addr,     half & 0xFF)
        self.write_byte(addr + 1, (half >> 8) & 0xFF)

    def write_word(self, addr, word, track=True):
        if not self._lookup(addr):
            self._load_line(addr)
            self.misses += 1
        else:
            self.hits += 1

        idx = self._index(addr)
        off = self._offset(addr)
        self.data[idx][off]   =  word        & 0xFF
        self.data[idx][off+1] = (word >> 8)  & 0xFF
        self.data[idx][off+2] = (word >> 16) & 0xFF
        self.data[idx][off+3] = (word >> 24) & 0xFF
        self.dirty[idx] = True

        if track:
            self.cycles_lost += self.hit_latency
        return self.hit_latency

    # ─── interface compatible Memory ──────────────────────────────

    @property
    def size(self):
        return self.mem.size

    def load_binary(self, path, start=0):
        return self.mem.load_binary(path, start)

    def _access_latency(self, addr):
        return self.mem._access_latency(addr)

    # ─── stats ────────────────────────────────────────────────────

    def dump(self):
        total    = self.hits + self.misses
        hit_rate = self.hits / total * 100 if total else 0
        print(f"─── cache L1 ────────────────────────────────────────")
        print(f"  taille       : {self.NUM_LINES * self.LINE_SIZE // 1024} Ko "
              f"({self.NUM_LINES} lignes × {self.LINE_SIZE} octets)")
        print(f"  prefetch     : {'oui' if self.prefetch else 'non'}")
        print(f"  hits         : {self.hits} ({hit_rate:.1f}%)")
        print(f"  misses       : {self.misses} ({100-hit_rate:.1f}%)")
        print(f"  writebacks   : {self.writebacks}")
        if self.prefetch:
            print(f"  préchargées  : {self.prefetch_hits + self.prefetch_miss}")
        print(f"  cycles perdus: {self.cycles_lost}")
        print(f"─────────────────────────────────────────────────────")