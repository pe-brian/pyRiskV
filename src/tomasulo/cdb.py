# tomasulo/cdb.py


class CDBResult():
    """Un résultat sur le Common Data Bus."""

    def __init__(self, tag, value, op=None):
        self.tag   = tag    # tag ROB du producteur
        self.value = value  # valeur calculée
        self.op    = op     # opération (pour debug)

    def __repr__(self):
        return f"CDB(ROB{self.tag} = {self.value} [{self.op}])"


class CommonDataBus():
    """
    Le Common Data Bus (CDB) — mécanisme de broadcast central.

    Quand une unité fonctionnelle termine, elle dépose
    son résultat sur le CDB. À ce moment :
    1. Toutes les RS qui attendaient ce tag reçoivent la valeur
    2. Le ROB est mis à jour
    3. La RAT est potentiellement mise à jour

    C'est le cœur de Tomasulo — sans CDB, pas d'out-of-order.

    Avec cdb_width > 1, plusieurs résultats peuvent être
    broadcastés par cycle (superscalaire).
    """

    def __init__(self, width=1):
        self.width   = width      # broadcasts simultanés par cycle
        self.pending = []         # résultats en attente de broadcast
        self.current = []         # résultats broadcastés ce cycle

        # stats
        self.total_broadcasts = 0
        self.cycles_with_broadcast = 0
        self.cycles_empty          = 0
        self.contention_cycles     = 0  # cycles où plus de résultats
                                        # que de largeur CDB

    # ─── dépôt d'un résultat ──────────────────────────────────────

    def produce(self, tag, value, op=None):
        """
        Une unité fonctionnelle dépose un résultat.
        Il sera broadcasté au prochain tick.
        """
        self.pending.append(CDBResult(tag, value, op))

    # ─── broadcast ────────────────────────────────────────────────

    def tick(self):
        """
        Broadcasté les résultats en attente.
        Limité à self.width résultats par cycle.

        Retourne la liste des résultats broadcastés ce cycle.
        """
        if len(self.pending) > self.width:
            self.contention_cycles += 1

        # prend au maximum 'width' résultats
        self.current  = self.pending[:self.width]
        self.pending  = self.pending[self.width:]

        if self.current:
            self.total_broadcasts      += len(self.current)
            self.cycles_with_broadcast += 1
        else:
            self.cycles_empty += 1

        return self.current

    # ─── application du broadcast ─────────────────────────────────

    def broadcast(self, rs_all, rob, rat=None):
        """
        Applique les résultats du cycle courant à :
        - toutes les RS (mise à jour des opérandes)
        - le ROB (marque les instructions comme terminées)
        - la RAT (optionnel — pour debug)

        Retourne la liste des résultats broadcastés.
        """
        results = self.tick()

        for result in results:
            # met à jour toutes les RS
            rs_all.update_cdb(result.tag, result.value)

            # met à jour le ROB
            rob.writeback(result.tag, result.value)

        return results

    def broadcast_store(self, tag, addr, value, rob):
        """Broadcast spécial pour les stores."""
        rob.writeback_store(tag, addr, value)

    # ─── état ─────────────────────────────────────────────────────

    def has_pending(self):
        return len(self.pending) > 0

    def is_busy(self):
        return len(self.current) > 0

    def clear(self):
        """Vide le CDB — utilisé après squash."""
        self.pending = []
        self.current = []

    # ─── affichage ────────────────────────────────────────────────

    def dump(self):
        print(f"─── CDB (width={self.width}) ──────────────────────────────")
        if self.current:
            print(f"  ce cycle     : {self.current}")
        else:
            print(f"  ce cycle     : vide")
        if self.pending:
            print(f"  en attente   : {self.pending}")
        print(f"─────────────────────────────────────────────────────")

    def stats(self):
        total_cycles = self.cycles_with_broadcast + self.cycles_empty
        util = (self.cycles_with_broadcast / total_cycles * 100
                if total_cycles else 0)
        print(f"  CDB broadcasts    : {self.total_broadcasts}")
        print(f"  CDB utilisation   : {util:.1f}%")
        print(f"  CDB contention    : {self.contention_cycles} cycles")