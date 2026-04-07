# tomasulo/rs.py


class RSEntry():
    """
    Une entrée dans une Reservation Station.

    Chaque entrée attend que ses opérandes soient disponibles
    avant de pouvoir s'exécuter.

    Champs :
    - vj, vk  : valeurs des opérandes (si disponibles)
    - qj, qk  : tags ROB attendus (None = opérande disponible)
    - dest    : tag ROB destination
    - busy    : entrée occupée ?
    - ready   : tous les opérandes disponibles ?
    - cycles_left : cycles restants avant fin d'exécution
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.busy        = False
        self.op          = None    # opération (ADD, LW, etc.)
        self.vj          = 0      # valeur opérande 1
        self.vk          = 0      # valeur opérande 2
        self.qj          = None   # tag ROB attendu opérande 1
        self.qk          = None   # tag ROB attendu opérande 2
        self.dest        = None   # tag ROB destination
        self.imm         = 0      # immédiat
        self.instr       = None   # instruction décodée complète
        self.executing   = False  # en cours d'exécution ?
        self.cycles_left = 0      # cycles restants
        self.result      = None   # résultat calculé

    @property
    def ready(self):
        """Tous les opérandes sont disponibles."""
        return self.busy and self.qj is None and self.qk is None

    def __repr__(self):
        if not self.busy:
            return 'RSEntry(libre)'
        qj = f"ROB{self.qj}" if self.qj is not None else f"v={self.vj}"
        qk = f"ROB{self.qk}" if self.qk is not None else f"v={self.vk}"
        return (f"RSEntry({self.op} "
                f"j={qj} k={qk} "
                f"dest=ROB{self.dest} "
                f"exec={self.executing} "
                f"left={self.cycles_left})")


class ReservationStation():
    """
    File d'attente devant une unité fonctionnelle.

    Plusieurs instructions peuvent attendre simultanément.
    Dès qu'une instruction a tous ses opérandes, elle peut
    s'exécuter sur n'importe quelle unité fonctionnelle libre.
    """

    def __init__(self, name, size, num_units, latency_table):
        self.name         = name
        self.size         = size
        self.num_units    = num_units    # unités fonctionnelles disponibles
        self.latency_table = latency_table

        self.entries      = [RSEntry() for _ in range(size)]

        # stats
        self.total_issued    = 0
        self.total_executed  = 0
        self.stall_cycles    = 0  # cycles où toutes les RS étaient pleines

    # ─── état ─────────────────────────────────────────────────────

    def is_full(self):
        return all(e.busy for e in self.entries)

    def is_empty(self):
        return not any(e.busy for e in self.entries)

    def free_count(self):
        return sum(1 for e in self.entries if not e.busy)

    # ─── issue ────────────────────────────────────────────────────

    def issue(self, instr, dest, vj, vk, qj, qk, imm=0):
        """
        Émet une instruction dans la RS.
        Retourne l'index de l'entrée allouée, ou None si pleine.

        vj, vk : valeurs des opérandes (valides si qj/qk = None)
        qj, qk : tags ROB à attendre (None = opérande déjà disponible)
        dest   : tag ROB destination
        """
        for i, entry in enumerate(self.entries):
            if not entry.busy:
                entry.busy        = True
                entry.op          = instr['name']
                entry.instr       = instr
                entry.dest        = dest
                entry.vj          = vj
                entry.vk          = vk
                entry.qj          = qj
                entry.qk          = qk
                entry.imm         = imm
                entry.executing   = False
                entry.cycles_left = 0
                entry.result      = None
                self.total_issued += 1
                return i
        self.stall_cycles += 1
        return None

    # ─── CDB broadcast ────────────────────────────────────────────

    def update_cdb(self, tag, value):
        """
        Reçoit un résultat du Common Data Bus.
        Met à jour toutes les entrées qui attendaient ce tag.

        C'est le mécanisme clé de Tomasulo :
        le résultat est capturé directement sans passer
        par les registres architecturaux.
        """
        for entry in self.entries:
            if not entry.busy:
                continue
            if entry.qj == tag:
                entry.vj = value
                entry.qj = None   # opérande maintenant disponible
            if entry.qk == tag:
                entry.vk = value
                entry.qk = None

    # ─── sélection pour exécution ─────────────────────────────────

    def get_ready_entries(self):
        """
        Retourne les entrées prêtes à s'exécuter
        (tous opérandes disponibles, pas encore en exécution).
        Triées par ordre d'arrivée — oldest-first.
        """
        return [
                (i, e) for i, e in enumerate(self.entries)
                if e.busy and e.ready and not e.executing
            ]

    def start_execution(self, idx):
        """Lance l'exécution d'une entrée."""
        entry = self.entries[idx]
        entry.executing   = True
        entry.cycles_left = self.latency_table.get(entry.op, 1)
        self.total_executed += 1

    # ─── avance d'un cycle ────────────────────────────────────────

    def tick(self):
        """
        Avance d'un cycle toutes les instructions en exécution.
        Retourne la liste des entrées qui viennent de terminer :
        [(idx, entry), ...]
        """
        finished = []
        for i, entry in enumerate(self.entries):
            if not entry.busy or not entry.executing:
                continue
            entry.cycles_left -= 1
            if entry.cycles_left <= 0:
                finished.append((i, entry))
        return finished

    def free(self, idx):
        """Libère une entrée après exécution."""
        self.entries[idx].reset()

    # ─── squash ───────────────────────────────────────────────────

    def squash(self):
        """Annule toutes les entrées — après mauvaise prédiction."""
        for entry in self.entries:
            entry.reset()

    # ─── affichage ────────────────────────────────────────────────

    def dump(self):
        busy = sum(1 for e in self.entries if e.busy)
        print(f"─── RS {self.name} ({busy}/{self.size}) ─────────────────────────")
        for i, entry in enumerate(self.entries):
            if entry.busy:
                qj = f"ROB{entry.qj}" if entry.qj is not None \
                     else f"{entry.vj}"
                qk = f"ROB{entry.qk}" if entry.qk is not None \
                     else f"{entry.vk}"
                exe = f"exec({entry.cycles_left}cy)" \
                      if entry.executing else "wait"
                print(f"  [{i}] {entry.op:<6} "
                      f"j={qj:<10} k={qk:<10} "
                      f"→ROB{entry.dest} {exe}")
            else:
                print(f"  [{i}] libre")
        print(f"─────────────────────────────────────────────────────")

    def stats(self):
        print(f"  {self.name} issued   : {self.total_issued}")
        print(f"  {self.name} executed : {self.total_executed}")
        print(f"  {self.name} stalls   : {self.stall_cycles}")

    def resolve_pending(self, rob):
        """Après issue, résout les opérandes déjà disponibles dans le ROB."""
        for entry in self.entries:
            if not entry.busy:
                continue
            if entry.qj is not None:
                val, ready = rob.get_value(entry.qj)
                if ready:
                    entry.vj = val
                    entry.qj = None
            if entry.qk is not None:
                val, ready = rob.get_value(entry.qk)
                if ready:
                    entry.vk = val
                    entry.qk = None


class ReservationStations():
    """
    Gestionnaire de toutes les reservation stations.
    Regroupe ALU, MUL, MEM.
    """

    def __init__(self, cfg):
        self.alu = ReservationStation(
            'ALU', cfg.rs_alu_size,
            cfg.alu_units, cfg.latency
        )
        self.mul = ReservationStation(
            'MUL', cfg.rs_mul_size,
            cfg.mul_units, cfg.latency
        )
        self.mem = ReservationStation(
            'MEM', cfg.rs_mem_size,
            cfg.mem_units, cfg.latency
        )

        self._map = {
            'alu': self.alu,
            'mul': self.mul,
            'mem': self.mem,
        }

    def get(self, name):
        return self._map[name]

    def update_cdb(self, tag, value):
        """Broadcast CDB à toutes les RS."""
        for rs in self._map.values():
            rs.update_cdb(tag, value)

    def squash(self):
        """Squash toutes les RS."""
        for rs in self._map.values():
            rs.squash()

    def dump(self):
        for rs in self._map.values():
            rs.dump()

    def stats(self):
        for rs in self._map.values():
            rs.stats()

    def resolve_all_pending(self, rob):
        """Résout les opérandes dans toutes les RS."""
        for rs in self._map.values():
            rs.resolve_pending(rob)