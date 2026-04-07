class StaticNotTaken():
    """
    Prédicteur statique — toujours non pris.
    Le plus simple possible.
    Bon pour : les if() rarement vrais.
    Mauvais pour : les boucles (toujours pris).
    """
    def __init__(self):
        self.predictions = 0
        self.misses      = 0
        self.name        = "static-not-taken"

    def predict(self, pc):
        self.predictions += 1
        return False  # toujours non pris

    def update(self, pc, taken):
        if taken:
            self.misses += 1

    def accuracy(self):
        if self.predictions == 0: return 0.0
        return (1 - self.misses / self.predictions) * 100

    def dump(self):
        print(f"  prédicteur   : {self.name}")
        print(f"  prédictions  : {self.predictions}")
        print(f"  erreurs      : {self.misses}")
        print(f"  précision    : {self.accuracy():.1f}%")


class StaticTaken():
    """
    Prédicteur statique — toujours pris.
    Bon pour : les boucles (presque toujours pris).
    Mauvais pour : les if() rarement vrais.
    """
    def __init__(self):
        self.predictions = 0
        self.misses      = 0
        self.name        = "static-taken"

    def predict(self, pc):
        self.predictions += 1
        return True  # toujours pris

    def update(self, pc, taken):
        if not taken:
            self.misses += 1

    def accuracy(self):
        if self.predictions == 0: return 0.0
        return (1 - self.misses / self.predictions) * 100

    def dump(self):
        print(f"  prédicteur   : {self.name}")
        print(f"  prédictions  : {self.predictions}")
        print(f"  erreurs      : {self.misses}")
        print(f"  précision    : {self.accuracy():.1f}%")


class Bimodal():
    """
    Prédicteur bimodal — table de compteurs saturants 2 bits.
    Chaque adresse de branchement a son propre compteur :
      00 = fortement non pris
      01 = faiblement non pris
      10 = faiblement pris
      11 = fortement pris
    
    Le compteur monte quand le saut est pris,
    descend quand il ne l'est pas.
    On prédit "pris" si compteur >= 2.
    
    L'hysterèse à 2 bits évite de changer de prédiction
    sur une seule exception — robuste aux boucles avec
    une dernière itération non prise.
    """
    def __init__(self, size=64):
        self.size        = size
        self.table       = [1] * size  # init à "faiblement non pris"
        self.predictions = 0
        self.misses      = 0
        self.name        = f"bimodal-{size}"

    def _index(self, pc):
        # utilise les bits bas du PC pour indexer la table
        return (pc >> 2) % self.size

    def predict(self, pc):
        self.predictions += 1
        idx = self._index(pc)
        return self.table[idx] >= 2  # pris si >= 2

    def update(self, pc, taken):
        idx = self._index(pc)
        if taken:
            self.table[idx] = min(3, self.table[idx] + 1)  # monte, max 3
        else:
            self.table[idx] = max(0, self.table[idx] - 1)  # descend, min 0

        predicted = self.table[idx] >= 2
        # on vérifie la prédiction AVANT la mise à jour
        # donc on recalcule depuis l'état précédent
        old = self.table[idx] + (1 if not taken else -1)
        old = max(0, min(3, old))
        if (old >= 2) != taken:
            self.misses += 1

    def accuracy(self):
        if self.predictions == 0: return 0.0
        return (1 - self.misses / self.predictions) * 100

    def dump(self):
        print(f"  prédicteur   : {self.name}")
        print(f"  table        : {self.size} entrées x 2 bits")
        print(f"  prédictions  : {self.predictions}")
        print(f"  erreurs      : {self.misses}")
        print(f"  précision    : {self.accuracy():.1f}%")


class GShare():
    """
    Prédicteur gshare — Global History Register + table de compteurs 2 bits.

    Principe :
      index = PC XOR GHR (Global History Register)

    Le GHR enregistre les N derniers branchements (1=pris, 0=non pris).
    Le XOR corrèle le comportement du branchement avec son contexte global.

    Inventé par Scott McFarling en 1993 — encore utilisé dans les CPUs modernes
    comme composante des prédicteurs hybrides.
    """
    def __init__(self, history_bits=4, table_size=64):
        self.history_bits = history_bits
        self.table_size   = table_size
        self.ghr          = 0                 # Global History Register
        self.mask         = (1 << history_bits) - 1  # masque sur history_bits
        self.table        = [1] * table_size  # compteurs 2 bits, init faiblement non pris
        self.predictions  = 0
        self.misses       = 0
        self.name         = f"gshare-{history_bits}bits"

    def _index(self, pc):
        # XOR entre les bits bas du PC et le GHR
        return ((pc >> 2) ^ self.ghr) % self.table_size

    def predict(self, pc):
        self.predictions += 1
        idx = self._index(pc)
        return self.table[idx] >= 2  # pris si compteur >= 2

    def update(self, pc, taken):
        idx = self._index(pc)

        # vérifie si la prédiction était correcte
        predicted = self.table[idx] >= 2
        if predicted != taken:
            self.misses += 1

        # met à jour le compteur saturant
        if taken:
            self.table[idx] = min(3, self.table[idx] + 1)
        else:
            self.table[idx] = max(0, self.table[idx] - 1)

        # met à jour le GHR — décale et insère le résultat
        self.ghr = ((self.ghr << 1) | (1 if taken else 0)) & self.mask

    def accuracy(self):
        if self.predictions == 0: return 0.0
        return (1 - self.misses / self.predictions) * 100

    def dump(self):
        print(f"  prédicteur   : {self.name}")
        print(f"  historique   : {self.history_bits} bits ({2**self.history_bits} contextes)")
        print(f"  table        : {self.table_size} entrées x 2 bits")
        print(f"  GHR final    : {bin(self.ghr)}")
        print(f"  prédictions  : {self.predictions}")
        print(f"  erreurs      : {self.misses}")
        print(f"  précision    : {self.accuracy():.1f}%")


class BTB():
    """
    Branch Target Buffer — cache des adresses cibles.
    Associe PC → adresse cible du branchement.
    Taille fixe avec remplacement FIFO simple.
    """
    def __init__(self, size=16):
        self.size    = size
        self.entries = {}  # pc → target

    def lookup(self, pc):
        """Retourne la cible si connue, None sinon."""
        return self.entries.get(pc, None)

    def update(self, pc, target):
        if pc not in self.entries and len(self.entries) >= self.size:
            if self.entries:  # ← vérifie que le dict n'est pas vide
                oldest = next(iter(self.entries))
                del self.entries[oldest]
        self.entries[pc] = target


class Tournament():
    """
    Prédicteur hybride dynamique — tournoi entre bimodal et gshare.

    Un méta-prédicteur (table de compteurs 2 bits) apprend dynamiquement
    quel prédicteur est le meilleur pour chaque branchement.

    0-1 → utilise bimodal (local, bon pour les boucles simples)
    2-3 → utilise gshare  (global, bon pour les branchements corrélés)

    Inventé par Digital Equipment Corporation pour l'Alpha 21264 (1996).
    """
    def __init__(self, size=64):
        self.size     = size
        self.bimodal  = Bimodal(size=size)
        self.gshare   = GShare(history_bits=4, table_size=size)
        self.selector = [1] * size  # init à "faiblement bimodal"
        self.predictions = 0
        self.misses      = 0
        self.name        = f"tournament-{size}"

        # stats par prédicteur
        self.used_bimodal = 0
        self.used_gshare  = 0

    def _index(self, pc):
        return (pc >> 2) % self.size

    def predict(self, pc):
        self.predictions += 1
        idx = self._index(pc)

        pred_bimodal = self.bimodal.predict(pc)
        pred_gshare  = self.gshare.predict(pc)

        # le sélecteur choisit
        if self.selector[idx] >= 2:
            self.used_gshare += 1
            return pred_gshare
        else:
            self.used_bimodal += 1
            return pred_bimodal

    def update(self, pc, taken):
        idx = self._index(pc)

        # résultats des deux prédicteurs AVANT mise à jour
        pred_bimodal = self.selector[idx] < 2  # ce qu'il aurait prédit
        pred_gshare  = self.selector[idx] >= 2

        # récupère les prédictions individuelles
        # on doit les recalculer avant update
        b_pred = self.bimodal.table[(pc >> 2) % self.size] >= 2
        g_pred = self.gshare.table[((pc >> 2) ^ self.gshare.ghr) % self.size] >= 2

        # met à jour le sélecteur
        if b_pred != taken and g_pred == taken:
            # gshare avait raison, bimodal avait tort → favorise gshare
            self.selector[idx] = min(3, self.selector[idx] + 1)
        elif g_pred != taken and b_pred == taken:
            # bimodal avait raison, gshare avait tort → favorise bimodal
            self.selector[idx] = max(0, self.selector[idx] - 1)
        # si les deux avaient raison ou tort → sélecteur inchangé

        # vérifie si la prédiction finale était correcte
        if self.selector[idx] >= 2:
            final_pred = g_pred
        else:
            final_pred = b_pred
        if final_pred != taken:
            self.misses += 1

        # met à jour les deux prédicteurs
        self.bimodal.update(pc, taken)
        self.gshare.update(pc, taken)

    def accuracy(self):
        if self.predictions == 0: return 0.0
        return (1 - self.misses / self.predictions) * 100

    def dump(self):
        total = self.used_bimodal + self.used_gshare
        pct_b = self.used_bimodal / total * 100 if total else 0
        pct_g = self.used_gshare  / total * 100 if total else 0
        print(f"  prédicteur   : {self.name}")
        print(f"  bimodal      : {self.used_bimodal} fois ({pct_b:.1f}%)")
        print(f"  gshare       : {self.used_gshare} fois ({pct_g:.1f}%)")
        print(f"  prédictions  : {self.predictions}")
        print(f"  erreurs      : {self.misses}")
        print(f"  précision    : {self.accuracy():.1f}%")