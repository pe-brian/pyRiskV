import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from cache_l2 import CacheL2
from memory import Memory
from slow_memory import SlowMemory
from cache_l1 import CacheL1
from branch_predictor import (
    StaticNotTaken, StaticTaken, Bimodal, GShare, Tournament, BTB
)


class SimConfig():
    """
    Configuration cohérente du simulateur.
    Gère les dépendances et incompatibilités entre options.
    """

    MEMORY_MODES    = ('fast', 'slow', 'cache')
    PREDICTOR_MODES = ('not-taken', 'taken', 'bimodal', 'gshare', 'tournament')

    def __init__(self):
        # mémoire
        self.memory_mode  = 'fast'
        self.latency_miss = 50
        self.latency_hit  = 4
        self.cache_lines  = 64
        self.cache_line_size = 64

        # pipeline
        self.forwarding   = True
        self.btb          = True
        self.btb_size     = 16

        # prédicteur
        self.predictor_mode = 'not-taken'

        # gshare
        self.gshare_history = 4
        self.gshare_size    = 64

        # bimodal
        self.bimodal_size   = 64

        # fréquence processeur
        self.clock_hz = 100_000_000

        self.ooo          = False   # out-of-order désactivé par défaut
        self.tomasulo_cfg = None    # config Tomasulo (None = défaut)

    # ─── parsing ligne de commande ────────────────────────────────

    @classmethod
    def from_args(cls, args):
        cfg = cls()

        # mémoire
        if '--cache' in args:
            cfg.memory_mode = 'cache'    # L1 + L2 + RAM lente
        elif '--l2' in args:
            cfg.memory_mode = 'l2only'   # L2 seul + RAM lente
        elif '--slow-mem' in args:
            cfg.memory_mode = 'slow'

        # pipeline
        if '--no-forwarding' in args:
            cfg.forwarding = False
        if '--no-btb' in args:
            cfg.btb = False

        if '--ooo' in args:
            cfg.ooo = True

        # prédicteur
        if '--tournament' in args:
            cfg.predictor_mode = 'tournament'
        elif '--gshare' in args:
            cfg.predictor_mode = 'gshare'
        elif '--bimodal' in args:
            cfg.predictor_mode = 'bimodal'
        elif '--taken' in args:
            cfg.predictor_mode = 'taken'
        elif '--not-taken' in args:
            cfg.predictor_mode = 'not-taken'
            

        cfg.validate()
        return cfg

    # ─── validation ───────────────────────────────────────────────

    def validate(self):
        warnings = []

        # cache implique slow-mem — toujours cohérent
        # (le cache est construit sur une SlowMemory)

        # sans BTB, pas de fetch spéculatif → prédicteur inutile
        if not self.btb and self.predictor_mode != 'not-taken':
            warnings.append(
                f"[!] --no-btb : prédicteur '{self.predictor_mode}' "
                f"ignoré, utilise 'not-taken'"
            )
            self.predictor_mode = 'not-taken'

        # sans forwarding, les résultats peuvent être incorrects
        if not self.forwarding:
            warnings.append(
                "[!] --no-forwarding : les résultats peuvent être "
                "incorrects (data hazards non résolus)"
            )

        # OoO incompatible avec no-forwarding
        if self.ooo and not self.forwarding:
            warnings.append(
                "[!] --ooo : --no-forwarding ignoré "
                "(Tomasulo gère ses propres hazards)"
            )
            self.forwarding = True

        for w in warnings:
            print(w, file=sys.stderr)

        return warnings

    # ─── construction des composants ──────────────────────────────

    def build_memory(self, size):
        from cache_l1 import CacheL1
        from cache_l2 import CacheL2
        from slow_memory import SlowMemory
        from memory import Memory

        if self.memory_mode == 'cache':
            ram = SlowMemory(size, self.latency_miss, self.latency_hit)
            l2  = CacheL2(ram, hit_latency=10)
            return CacheL1(l2, hit_latency=1)
        elif self.memory_mode == 'l2only':
            ram = SlowMemory(size, self.latency_miss, self.latency_hit)
            return CacheL2(ram, hit_latency=10)
        elif self.memory_mode == 'slow':
            return SlowMemory(size, self.latency_miss, self.latency_hit)
        else:
            return Memory(size)

    def build_predictor(self):
        if self.predictor_mode == 'tournament':
            return Tournament()
        elif self.predictor_mode == 'gshare':
            return GShare(self.gshare_history, self.gshare_size)
        elif self.predictor_mode == 'bimodal':
            return Bimodal(self.bimodal_size)
        elif self.predictor_mode == 'taken':
            return StaticTaken()
        else:
            return StaticNotTaken()

    def build_pipeline(self, mem):
        if self.ooo:
            from cpu_ooo import CPUOutOfOrder
            from tomasulo.config import TomasuloConfig
            cfg = self.tomasulo_cfg or TomasuloConfig()
            return CPUOutOfOrder(mem, tomasulo_cfg=cfg, clock_hz=self.clock_hz)
        else:
            from cpu_pipeline import Pipeline
            return Pipeline(
                mem,
                clock_hz   = self.clock_hz,
                predictor  = self.build_predictor(),
                forwarding = self.forwarding,
                btb_size   = self.btb_size if self.btb else 0,
            )

    def build_cpu(self, mem):
        from cpu import CPU
        return CPU(mem)

    # ─── affichage ────────────────────────────────────────────────

    def dump(self):
        print(f"─── configuration ───────────────────────────────────")
        print(f"  mémoire      : {self.memory_mode}", end='')
        if self.memory_mode == 'slow':
            print(f" (miss={self.latency_miss}cy, hit={self.latency_hit}cy)", end='')
        elif self.memory_mode == 'cache':
            print(f" (L1+L2, miss={self.latency_miss}cy)", end='')
        elif self.memory_mode == 'l2only':
            print(f" (L2 seul, miss={self.latency_miss}cy)", end='')
        print()
        print(f"  forwarding   : {'oui' if self.forwarding else 'non'}")
        print(f"  BTB          : {'oui' if self.btb else 'non'}", end='')
        if self.btb:
            print(f" ({self.btb_size} entrées)", end='')
        print()
        print(f"  prédicteur   : {self.predictor_mode}")
        print(f"  out-of-order : {'oui (Tomasulo)' if self.ooo else 'non (in-order)'}")
        print(f"─────────────────────────────────────────────────────")

    @staticmethod
    def help():
        print("""
Options du simulateur :

  Mémoire :
    --fast          RAM rapide fictive (défaut)
    --slow-mem      RAM lente avec latence réaliste
    --l2            RAM lente + cache L2 (LRU 4-way, 64 Ko)
    --cache         RAM lente + cache L1 + L2 (hiérarchie complète)

  Pipeline :
    --no-forwarding  désactive le forwarding (résultats potentiellement incorrects)
    --no-btb         désactive le Branch Target Buffer

  Prédicteur de branchement :
    --not-taken     statique — toujours non pris (défaut)
    --taken         statique — toujours pris
    --bimodal       bimodal 64 entrées
    --gshare        gshare 4 bits d'historique
    --tournament    tournoi bimodal + gshare
              
    Out-of-order :
    --ooo           active l'exécution out-of-order (Tomasulo)

  Incompatibilités :
    --no-btb + --taken/bimodal/gshare/tournament → prédicteur ignoré
""")