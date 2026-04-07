# tomasulo/rat.py


class RegisterAliasTable():
    """
    Register Alias Table (RAT) — cœur du register renaming.

    Problème résolu :
        ADD x1, x2, x3   # écrit x1
        ADD x1, x4, x5   # écrit x1 aussi → WAW hazard
        ADD x6, x1, x7   # lit x1 → WAR hazard

    Solution — chaque écriture va dans un nouveau tag ROB.
    La RAT dit "pour le registre architectural x1,
    le résultat en attente est dans ROB3" :

        rat[1] = 3   → x1 attend le résultat de ROB3

    Quand ROB3 commite, rat[1] est remis à None
    (x1 est à jour dans le register file architectural).

    Deux types de hazards éliminés :
    - WAW : chaque écriture a son propre tag ROB
    - WAR : on lit le tag, pas la valeur — la valeur
            peut être écrasée sans problème

    Seul RAW subsiste — c'est une vraie dépendance.
    """

    def __init__(self, num_arch_regs=32):
        self.num_arch_regs = num_arch_regs

        # rat[reg] = tag ROB en attente, ou None si à jour
        self.table = [None] * num_arch_regs

        # registre file architectural — valeurs commitées
        self.arch_regs = [0] * num_arch_regs

        # stats
        self.total_renames  = 0
        self.total_reads    = 0
        self.raw_stalls     = 0   # lectures qui ont trouvé un tag (RAW)

    # ─── lecture d'un opérande ────────────────────────────────────

    def read(self, reg):
        """
        Lit la valeur ou le tag d'un registre architectural.

        Retourne (value, tag) :
        - Si tag is None  → valeur disponible dans value
        - Si tag is not None → valeur pas encore disponible,
                               il faut attendre ROB[tag]

        x0 est toujours 0 (hardwired).
        """
        self.total_reads += 1

        if reg == 0:
            return 0, None  # x0 toujours 0

        tag = self.table[reg]
        if tag is not None:
            # RAW hazard — résultat pas encore disponible
            self.raw_stalls += 1
            return 0, tag   # retourne le tag à attendre
        else:
            # valeur disponible dans le register file
            return self.arch_regs[reg], None

    # ─── renommage à l'issue ──────────────────────────────────────

    def rename(self, reg, rob_tag):
        """
        Associe le registre architectural 'reg' au tag ROB 'rob_tag'.
        Appelé quand une instruction est émise (issue).

        Après ce renommage, toute lecture de 'reg' retournera
        rob_tag jusqu'à ce que l'instruction commite.

        x0 est ignoré — on n'écrit jamais dans x0.
        """
        if reg == 0:
            return
        self.table[reg]    = rob_tag
        self.total_renames += 1

    # ─── commit ───────────────────────────────────────────────────

    def commit(self, reg, value, rob_tag):
        """
        Commite le résultat d'une instruction.
        Met à jour le register file architectural.

        Si le tag ROB courant dans la RAT correspond à rob_tag,
        on libère le renommage (la valeur est maintenant dans
        arch_regs et à jour).

        Si le tag ne correspond pas, c'est qu'une instruction
        plus récente a déjà renommé ce registre — on ne libère
        pas le renommage.

        x0 est ignoré.
        """
        if reg == 0:
            return

        self.arch_regs[reg] = value & 0xFFFFFFFF

        # libère le renommage seulement si c'est encore notre tag
        if self.table[reg] == rob_tag:
            self.table[reg] = None

    # ─── squash ───────────────────────────────────────────────────

    def squash(self, checkpoint=None):
        """
        Annule tous les renommages en cours.
        Après un squash (mauvaise prédiction), la RAT revient
        à l'état des registres commitées.

        Sans checkpoint : remet tous les tags à None
        (les valeurs dans arch_regs sont toujours correctes
        car seules les instructions commitées y écrivent).
        """
        self.table = [None] * self.num_arch_regs

    # ─── valeur depuis le ROB ─────────────────────────────────────

    def resolve_from_rob(self, tag, rob):
        """
        Essaie de résoudre un tag ROB immédiatement
        si le résultat est déjà disponible dans le ROB.

        Utilisé à l'issue pour éviter d'attendre le CDB
        si le résultat est déjà là.
        """
        value, ready = rob.get_value(tag)
        if ready:
            return value, None  # résultat disponible → pas de tag
        return 0, tag           # toujours en attente

    # ─── affichage ────────────────────────────────────────────────

    # noms ABI RISC-V
    ABI_NAMES = [
        'zero','ra','sp','gp','tp',
        't0','t1','t2',
        's0','s1',
        'a0','a1','a2','a3','a4','a5','a6','a7',
        's2','s3','s4','s5','s6','s7','s8','s9','s10','s11',
        't3','t4','t5','t6',
    ]

    def dump(self):
        print(f"─── RAT ──────────────────────────────────────────────")
        for i in range(self.num_arch_regs):
            val  = self.arch_regs[i]
            tag  = self.table[i]
            name = self.ABI_NAMES[i] if i < len(self.ABI_NAMES) else f'x{i}'
            if tag is not None or val != 0:
                tag_str = f"→ROB{tag}" if tag is not None else "committed"
                print(f"  x{i:<2} ({name:<4}) = {val:#010x}  {tag_str}")
        print(f"─────────────────────────────────────────────────────")

    def dump_full(self):
        """Affiche tous les registres même à 0."""
        print(f"─── RAT (complet) ────────────────────────────────────")
        for i in range(0, self.num_arch_regs, 2):
            for j in range(2):
                idx  = i + j
                val  = self.arch_regs[idx]
                tag  = self.table[idx]
                name = self.ABI_NAMES[idx] \
                       if idx < len(self.ABI_NAMES) else f'x{idx}'
                tag_str = f"→ROB{tag}" if tag is not None else "ok"
                print(f"  x{idx:<2} ({name:<4}) = {val:#010x} {tag_str:<8}",
                      end='  ')
            print()
        print(f"─────────────────────────────────────────────────────")

    def stats(self):
        print(f"  renames    : {self.total_renames}")
        print(f"  reads      : {self.total_reads}")
        print(f"  RAW stalls : {self.raw_stalls}")