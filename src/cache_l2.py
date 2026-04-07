class CacheL2():
    """
    Cache L2 — 4-way set-associative avec politique LRU et write-back.

    Paramètres typiques :
    - Taille     : 256 Ko (on simule 64 Ko)
    - Lignes     : 64 octets
    - Sets       : 256
    - Ways       : 4
    - Latence hit: 10 cycles

    Write-back : les lignes modifiées (dirty) ne sont écrites
    en RAM que lors de leur éviction — pas à chaque écriture.
    """

    LINE_SIZE   = 64   # octets par ligne
    NUM_SETS    = 256  # nombre de sets
    NUM_WAYS    = 4    # associativité
    HIT_LATENCY = 10   # cycles pour un hit L2

    def __init__(self, mem, hit_latency=10):
        self.mem         = mem
        self.hit_latency = hit_latency

        # structure : valid[set][way], tags[set][way], data[set][way][byte]
        self.valid = [[False] * self.NUM_WAYS for _ in range(self.NUM_SETS)]
        self.tags  = [[0]     * self.NUM_WAYS for _ in range(self.NUM_SETS)]
        self.data  = [[[0] * self.LINE_SIZE for _ in range(self.NUM_WAYS)]
                      for _ in range(self.NUM_SETS)]
        self.dirty = [[False] * self.NUM_WAYS for _ in range(self.NUM_SETS)]

        # LRU — pour chaque set, liste ordonnée des ways [MRU, ..., LRU]
        self.lru = [list(range(self.NUM_WAYS)) for _ in range(self.NUM_SETS)]

        # stats
        self.hits        = 0
        self.misses      = 0
        self.evictions   = 0
        self.writebacks  = 0
        self.cycles_lost = 0

    # ─── décomposition d'adresse ──────────────────────────────────

    def _offset(self, addr): return addr % self.LINE_SIZE
    def _index(self, addr):  return (addr // self.LINE_SIZE) % self.NUM_SETS
    def _tag(self, addr):    return addr // (self.LINE_SIZE * self.NUM_SETS)

    def _line_start_from(self, set_idx, way):
        """Reconstruit l'adresse de début d'une ligne depuis son tag."""
        return (self.tags[set_idx][way] * self.NUM_SETS + set_idx) * self.LINE_SIZE

    # ─── LRU ──────────────────────────────────────────────────────

    def _lru_touch(self, set_idx, way):
        """Marque 'way' comme MRU."""
        order = self.lru[set_idx]
        order.remove(way)
        order.insert(0, way)

    def _lru_victim(self, set_idx):
        """Retourne le way LRU (à évincer)."""
        return self.lru[set_idx][-1]

    # ─── lookup ───────────────────────────────────────────────────

    def _lookup(self, addr):
        """
        Cherche l'adresse dans le cache.
        Retourne le way si trouvé, -1 sinon.
        """
        idx = self._index(addr)
        tag = self._tag(addr)
        for way in range(self.NUM_WAYS):
            if self.valid[idx][way] and self.tags[idx][way] == tag:
                return way
        return -1

    # ─── éviction write-back ──────────────────────────────────────

    def _evict(self, set_idx, way):
        """
        Évicte une ligne — si dirty, écrit en RAM d'abord.
        """
        if self.valid[set_idx][way] and self.dirty[set_idx][way]:
            old_start = self._line_start_from(set_idx, way)
            for i in range(self.LINE_SIZE):
                self.mem.write_byte(old_start + i,
                                    self.data[set_idx][way][i])
            self.dirty[set_idx][way] = False
            self.writebacks += 1
        if self.valid[set_idx][way]:
            self.evictions += 1

    # ─── chargement d'une ligne ───────────────────────────────────

    def _load_line(self, addr):
        """
        Charge une ligne depuis la mémoire sous-jacente.
        Évicte le way LRU (avec write-back si dirty).
        Retourne (way, latency).
        """
        idx        = self._index(addr)
        tag        = self._tag(addr)
        line_start = addr - self._offset(addr)

        # choisit et évicte le way victime (LRU)
        way = self._lru_victim(idx)
        self._evict(idx, way)

        # charge depuis la mémoire sous-jacente
        for i in range(self.LINE_SIZE):
            self.data[idx][way][i] = self.mem.read_byte(line_start + i)

        self.valid[idx][way] = True
        self.tags[idx][way]  = tag
        self.dirty[idx][way] = False
        self._lru_touch(idx, way)

        # latence = latence de la mémoire sous-jacente
        if hasattr(self.mem, '_access_latency'):
            _, latency = self.mem.read_word(line_start, track=True)
        else:
            latency = self.hit_latency

        self.cycles_lost += latency
        return way, latency

    # ─── lecture ──────────────────────────────────────────────────

    def read_byte(self, addr):
        idx = self._index(addr)
        way = self._lookup(addr)
        if way == -1:
            self.misses += 1
            way, _ = self._load_line(addr)
        else:
            self.hits += 1
            self._lru_touch(idx, way)
            self.cycles_lost += self.hit_latency
        return self.data[idx][way][self._offset(addr)]

    def read_half(self, addr):
        b0 = self.read_byte(addr)
        b1 = self.read_byte(addr + 1)
        return b0 | (b1 << 8)

    def read_word(self, addr, track=True):
        if not track:
            return self.mem.read_word(addr, track=False) \
                if hasattr(self.mem, 'read_word') else \
                (self._read_word_raw(addr), 0)

        idx = self._index(addr)
        way = self._lookup(addr)
        if way == -1:
            self.misses  += 1
            way, latency  = self._load_line(addr)
        else:
            self.hits    += 1
            latency       = self.hit_latency
            self._lru_touch(idx, way)
            self.cycles_lost += latency

        off = self._offset(addr)
        val = (self.data[idx][way][off]         |
               self.data[idx][way][off+1] << 8  |
               self.data[idx][way][off+2] << 16 |
               self.data[idx][way][off+3] << 24)
        return val, latency

    def _read_word_raw(self, addr):
        b0 = self.mem.read_byte(addr)
        b1 = self.mem.read_byte(addr + 1)
        b2 = self.mem.read_byte(addr + 2)
        b3 = self.mem.read_byte(addr + 3)
        return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)

    # ─── écriture (write-back) ────────────────────────────────────

    def write_byte(self, addr, byte):
        idx = self._index(addr)
        way = self._lookup(addr)
        if way == -1:
            # ligne pas dans le cache — charge d'abord
            self.misses += 1
            way, _ = self._load_line(addr)
        else:
            self.hits += 1
            self._lru_touch(idx, way)

        self.data[idx][way][self._offset(addr)] = byte & 0xFF
        self.dirty[idx][way] = True  # marque dirty, pas d'écriture RAM

    def write_half(self, addr, half):
        self.write_byte(addr,     half & 0xFF)
        self.write_byte(addr + 1, (half >> 8) & 0xFF)

    def write_word(self, addr, word, track=True):
        idx = self._index(addr)
        way = self._lookup(addr)
        if way == -1:
            # ligne pas dans le cache — charge d'abord
            self.misses += 1
            way, _ = self._load_line(addr)
        else:
            self.hits += 1
            self._lru_touch(idx, way)

        off = self._offset(addr)
        self.data[idx][way][off]   =  word        & 0xFF
        self.data[idx][way][off+1] = (word >> 8)  & 0xFF
        self.data[idx][way][off+2] = (word >> 16) & 0xFF
        self.data[idx][way][off+3] = (word >> 24) & 0xFF
        self.dirty[idx][way] = True  # marque dirty, pas d'écriture RAM

        if track:
            self.cycles_lost += self.hit_latency
        return self.hit_latency

    # ─── interface compatible ─────────────────────────────────────

    @property
    def size(self):
        return self.mem.size

    def load_binary(self, path, start=0):
        return self.mem.load_binary(path, start)

    def _access_latency(self, addr):
        return self.mem._access_latency(addr) \
               if hasattr(self.mem, '_access_latency') else self.hit_latency

    # ─── stats ────────────────────────────────────────────────────

    def dump(self):
        total    = self.hits + self.misses
        hit_rate = self.hits / total * 100 if total else 0
        size_kb  = self.NUM_SETS * self.NUM_WAYS * self.LINE_SIZE // 1024
        print(f"─── cache L2 ────────────────────────────────────────")
        print(f"  taille       : {size_kb} Ko "
              f"({self.NUM_SETS} sets × {self.NUM_WAYS} ways × "
              f"{self.LINE_SIZE} octets)")
        print(f"  associativité: {self.NUM_WAYS}-way LRU")
        print(f"  hits         : {self.hits} ({hit_rate:.1f}%)")
        print(f"  misses       : {self.misses} ({100-hit_rate:.1f}%)")
        print(f"  évictions    : {self.evictions}")
        print(f"  writebacks   : {self.writebacks}")
        print(f"  cycles perdus: {self.cycles_lost}")
        print(f"─────────────────────────────────────────────────────")