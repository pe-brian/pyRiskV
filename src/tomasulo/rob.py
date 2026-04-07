# tomasulo/rob.py


class ROBState():
    """États possibles d'une entrée dans le ROB."""
    ISSUE     = 'issue'      # émise, pas encore en exécution
    EXECUTE   = 'execute'    # en cours d'exécution
    WRITEBACK = 'writeback'  # résultat disponible, pas encore commité
    COMMIT    = 'commit'     # prête à être commitée


class ROBEntry():
    """
    Une entrée dans le Reorder Buffer.

    Le ROB garantit que les instructions se committent
    dans l'ordre du programme, même si elles s'exécutent
    dans le désordre.
    """
    def __init__(self):
        self.tag     = 0
        self.busy    = False         # entrée occupée ?
        self.state   = ROBState.ISSUE
        self.instr   = None          # instruction décodée (dict)
        self.dest    = 0             # registre architectural destination
        self.value   = 0             # résultat calculé
        self.ready   = False         # résultat disponible ?
        self.is_store = False        # c'est un store ?
        self.store_addr  = None      # adresse mémoire (pour SW)
        self.store_value = None      # valeur à écrire (pour SW)

    def reset(self):
        self.__init__()

    def __repr__(self):
        if not self.busy:
            return 'ROBEntry(libre)'
        name = self.instr['name'] if self.instr else '?'
        return (f"ROBEntry({name} → x{self.dest} "
                f"val={self.value} state={self.state} "
                f"ready={self.ready})")


class ReorderBuffer():
    """
    File circulaire FIFO qui maintient l'ordre du programme.

    Structure :
    ┌─────┬─────┬─────┬─────┬─────┬─────┐
    │  0  │  1  │  2  │  3  │  4  │  5  │
    └─────┴─────┴─────┴─────┴─────┴─────┘
      ↑ head                        ↑ tail
    (commit)                      (issue)

    - head : prochaine entrée à commiter
    - tail : prochaine entrée libre pour l'issue
    """

    def __init__(self, size=16):
        self.size    = size
        self.entries = [ROBEntry() for _ in range(size)]
        self.head    = 0   # prochain à commiter
        self.tail    = 0   # prochaine entrée libre
        self.count   = 0   # nombre d'entrées occupées
        self._committed_this_cycle = {}

        # stats
        self.total_commits  = 0
        self.total_squashes = 0  # instructions annulées (mauvaise prédiction)

    # ─── état ─────────────────────────────────────────────────────

    def clear_cycle_cache(self):
        self._committed_this_cycle.clear()

    def is_full(self):
        return self.count >= self.size

    def is_empty(self):
        return self.count == 0

    def tag_name(self, idx):
        """Retourne le nom du tag ROB pour l'affichage."""
        return f"ROB{idx}"

    # ─── issue ────────────────────────────────────────────────────

    def issue(self, instr, dest):
        """
        Alloue une entrée ROB pour une nouvelle instruction.
        Retourne le tag (index) alloué, ou None si plein.
        """
        if self.is_full():
            return None

        tag = self.tail
        entry = self.entries[tag]
        entry.tag       = tag
        entry.busy      = True
        entry.state     = ROBState.ISSUE
        entry.instr     = instr
        entry.dest      = dest
        entry.value     = 0
        entry.ready     = False
        entry.is_store  = instr['name'] in ('SW','SH','SB')
        entry.store_addr  = None
        entry.store_value = None

        self.tail  = (self.tail + 1) % self.size
        self.count += 1
        return tag

    # ─── writeback ────────────────────────────────────────────────

    def writeback(self, tag, value):
        """
        Une unité fonctionnelle a terminé — enregistre le résultat.
        """
        entry = self.entries[tag]
        entry.value = value
        entry.ready = True
        entry.state = ROBState.WRITEBACK

    def writeback_store(self, tag, addr, value):
        """Writeback spécial pour les stores."""
        entry = self.entries[tag]
        entry.store_addr  = addr
        entry.store_value = value
        entry.ready       = True
        entry.state       = ROBState.WRITEBACK

    # ─── commit ───────────────────────────────────────────────────

    def can_commit(self):
        """
        Vérifie si l'instruction en tête de ROB peut être commitée.
        Une instruction peut commiter si :
        - elle est prête (résultat disponible)
        - elle est en tête du ROB (ordre du programme respecté)
        """
        if self.is_empty():
            return False
        return self.entries[self.head].ready

    def commit(self):
        """
        Commite l'instruction en tête du ROB.
        Retourne l'entrée commitée.
        """
        if not self.can_commit():
            return None
        
        tag   = self.head
        entry = self.entries[self.head]
        entry.state = ROBState.COMMIT
        
        # sauvegarde la valeur AVANT reset pour le cache cycle
        self._committed_this_cycle[tag] = (entry.dest, entry.value)

        # libère l'entrée
        result = ROBEntry()
        result.busy        = True  # marque comme "en cours de commit"
        result.tag         = tag
        result.instr       = entry.instr
        result.dest        = entry.dest
        result.value       = entry.value
        result.is_store    = entry.is_store
        result.store_addr  = entry.store_addr
        result.store_value = entry.store_value

        entry.reset()

        self.head  = (self.head + 1) % self.size
        self.count -= 1
        self.total_commits += 1

        return result

    # ─── squash ───────────────────────────────────────────────────

    def squash(self):
        """
        Annule toutes les instructions dans le ROB.
        Utilisé après une mauvaise prédiction de branchement.
        """
        squashed = self.count
        for entry in self.entries:
            entry.reset()
        self.head  = 0
        self.tail  = 0
        self.count = 0
        self.total_squashes += squashed
        return squashed

    # ─── lookup ───────────────────────────────────────────────────

    def get_value(self, tag):
        """
        Retourne la valeur d'une entrée ROB si disponible.
        Consulte aussi le cache des valeurs commitées ce cycle
        pour éviter la fenêtre de course commit/issue.
        """
        entry = self.entries[tag]
        if entry.busy and entry.ready:
            return entry.value, True
        if tag in self._committed_this_cycle:
            return self._committed_this_cycle[tag][1], True
        return None, False

    # ─── affichage ────────────────────────────────────────────────

    def dump(self):
        print(f"─── ROB ({self.count}/{self.size}) ──────────────────────────────")
        for i in range(self.size):
            entry = self.entries[i]
            head  = '←HEAD' if i == self.head else ''
            tail  = '←TAIL' if i == self.tail else ''
            if entry.busy:
                name = entry.instr['name'] if entry.instr else '?'
                print(f"  [{i:2}] {name:<6} x{entry.dest:<2} "
                      f"val={entry.value:<10} "
                      f"state={entry.state:<10} "
                      f"ready={entry.ready} {head}{tail}")
            else:
                print(f"  [{i:2}] libre {head}{tail}")
        print(f"─────────────────────────────────────────────────────")

    def stats(self):
        print(f"  commits  : {self.total_commits}")
        print(f"  squashes : {self.total_squashes}")