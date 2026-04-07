import sys
import os
import io
import contextlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from mem_init import MemoryInitializer
from memory import Memory
from slow_memory import SlowMemory
from cache_l1 import CacheL1
from cache_l2 import CacheL2
from cpu import CPU
from cpu_pipeline import Pipeline
from cpu_ooo import CPUOutOfOrder
from tomasulo.config import TomasuloConfig
from branch_predictor import StaticNotTaken, StaticTaken, Bimodal, GShare, Tournament

# ─── configuration ────────────────────────────────────────────────────

MEMORY_SIZE = 16384
CLOCK_HZ    = 100_000_000
MAX_CYCLES  = 500_000

# ─── programmes ───────────────────────────────────────────────────────

PROGRAMS = [
    {
        'name': 'Fibonacci',
        'path': 'programs/fibonacci/fibonacci.bin',
        'init': 'programs/fibonacci/fibonacci.json',
    },
    {
        'name': 'BubbleSort',
        'path': 'programs/bubblesort/bubblesort.bin',
        'init': 'programs/bubblesort/bubblesort.json',
    },
    {
        'name': 'RandomAccess',
        'path': 'programs/random_access/random_access.bin',
        'init': 'programs/random_access/random_access.json',
    },
    {
        'name': 'SeqSum',
        'path': 'programs/seqsum/seqsum.bin',
        'init': 'programs/seqsum/seqsum.json',
    },
]

PREDICTORS = [
    ('static-not-taken', lambda: StaticNotTaken()),
    ('static-taken',     lambda: StaticTaken()),
    ('bimodal-64',       lambda: Bimodal(size=64)),
    ('gshare-4bits',     lambda: GShare(history_bits=4, table_size=64)),
    ('tournament',       lambda: Tournament()),
]

# ─── utilitaires ──────────────────────────────────────────────────────

@contextlib.contextmanager
def silent():
    """Supprime stdout pendant l'exécution."""
    with contextlib.redirect_stdout(io.StringIO()):
        yield

def _init(mem, init_path):
    """Applique le fichier JSON d'initialisation si disponible."""
    if init_path and os.path.exists(init_path):
        MemoryInitializer(init_path).apply(mem)

def _best(results):
    """Retourne le meilleur résultat (moins de cycles)."""
    return min(results.items(), key=lambda x: x[1]['cycles'])

# ─── fonctions d'exécution ────────────────────────────────────────────

def run_sequential(path, init_path):
    mem = Memory(MEMORY_SIZE)
    mem.load_binary(path, start=0)
    _init(mem, init_path)
    cpu    = CPU(mem, clock_hz=CLOCK_HZ)
    cpu.pc = 0
    with silent():
        steps = cpu.run(max_steps=MAX_CYCLES * 10)
    return {
        'cycles':       cpu.cycles,
        'instructions': steps,
        'ipc':          steps / cpu.cycles if cpu.cycles else 0,
        'result':       cpu.regs.read(10),
        'time_us':      cpu.elapsed_us(),
        'precision':    None,
        'penalties':    None,
        'mem_hits':     None,
        'mem_misses':   None,
        'predictor':    '—',
    }

def run_pipeline(path, init_path, predictor_fn, pred_name):
    mem = Memory(MEMORY_SIZE)
    mem.load_binary(path, start=0)
    _init(mem, init_path)
    cpu    = Pipeline(mem, clock_hz=CLOCK_HZ, predictor=predictor_fn())
    cpu.pc = 0
    with silent():
        cpu.run(max_cycles=MAX_CYCLES * 10)
    return {
        'cycles':       cpu.cycles,
        'instructions': cpu.instructions,
        'ipc':          cpu.instructions / cpu.cycles if cpu.cycles else 0,
        'result':       cpu.regs.read(10),
        'time_us':      cpu.elapsed_us(),
        'precision':    cpu.predictor.accuracy(),
        'penalties':    cpu.branch_penalties,
        'mem_hits':     None,
        'mem_misses':   None,
        'predictor':    pred_name,
    }

def run_pipeline_slow(path, init_path, predictor_fn, pred_name):
    mem = SlowMemory(MEMORY_SIZE, latency_miss=50, latency_hit=4)
    mem.load_binary(path, start=0)
    _init(mem, init_path)
    cpu    = Pipeline(mem, clock_hz=CLOCK_HZ, predictor=predictor_fn())
    cpu.pc = 0
    with silent():
        cpu.run(max_cycles=MAX_CYCLES * 20)
    return {
        'cycles':       cpu.cycles,
        'instructions': cpu.instructions,
        'ipc':          cpu.instructions / cpu.cycles if cpu.cycles else 0,
        'result':       cpu.regs.read(10),
        'time_us':      cpu.elapsed_us(),
        'precision':    cpu.predictor.accuracy(),
        'penalties':    cpu.branch_penalties,
        'mem_hits':     mem.row_hits,
        'mem_misses':   mem.row_misses,
        'predictor':    pred_name,
    }

def run_pipeline_cached(path, init_path, predictor_fn, pred_name):
    ram   = SlowMemory(MEMORY_SIZE, latency_miss=50, latency_hit=4)
    cache = CacheL1(ram, hit_latency=1)
    cache.load_binary(path, start=0)
    _init(cache, init_path)
    cpu    = Pipeline(cache, clock_hz=CLOCK_HZ, predictor=predictor_fn())
    cpu.pc = 0
    with silent():
        cpu.run(max_cycles=MAX_CYCLES * 20)
    return {
        'cycles':       cpu.cycles,
        'instructions': cpu.instructions,
        'ipc':          cpu.instructions / cpu.cycles if cpu.cycles else 0,
        'result':       cpu.regs.read(10),
        'time_us':      cpu.elapsed_us(),
        'precision':    cpu.predictor.accuracy(),
        'penalties':    cpu.branch_penalties,
        'mem_hits':     cache.hits,
        'mem_misses':   cache.misses,
        'predictor':    pred_name,
    }

def run_pipeline_l1l2(path, init_path, predictor_fn, pred_name):
    ram = SlowMemory(MEMORY_SIZE, latency_miss=50, latency_hit=4)
    l2  = CacheL2(ram, hit_latency=10)
    l1  = CacheL1(l2, hit_latency=1)
    l1.load_binary(path, start=0)
    _init(l1, init_path)
    cpu    = Pipeline(l1, clock_hz=CLOCK_HZ, predictor=predictor_fn())
    cpu.pc = 0
    with silent():
        cpu.run(max_cycles=MAX_CYCLES * 20)
    return {
        'cycles':       cpu.cycles,
        'instructions': cpu.instructions,
        'ipc':          cpu.instructions / cpu.cycles if cpu.cycles else 0,
        'result':       cpu.regs.read(10),
        'time_us':      cpu.elapsed_us(),
        'precision':    cpu.predictor.accuracy(),
        'penalties':    cpu.branch_penalties,
        'mem_hits':     l1.hits,
        'mem_misses':   l1.misses,
        'predictor':    pred_name,
    }

def run_ooo(path, init_path):
    """Out-of-order Tomasulo sur RAM rapide."""
    mem = Memory(MEMORY_SIZE)
    mem.load_binary(path, start=0)
    _init(mem, init_path)
    cfg = TomasuloConfig()
    cfg.issue_width  = 2
    cfg.commit_width = 2
    cfg.cdb_width    = 2
    cpu = CPUOutOfOrder(mem, tomasulo_cfg=cfg, clock_hz=CLOCK_HZ)
    with silent():
        cpu.run(max_cycles=MAX_CYCLES * 10)
    return {
        'cycles':       cpu.cycles,
        'instructions': cpu.instructions,
        'ipc':          cpu.instructions / cpu.cycles if cpu.cycles else 0,
        'result':       cpu.regs.read(10),
        'time_us':      cpu.elapsed_us(),
        'precision':    None,
        'penalties':    cpu.branch_mispredictions,
        'mem_hits':     None,
        'mem_misses':   None,
        'predictor':    '—',
    }

# ─── affichage synthétique ────────────────────────────────────────────

def fmt_hit(r):
    hits  = r.get('mem_hits')
    miss  = r.get('mem_misses')
    if hits is None:
        return ''
    total = hits + (miss or 0)
    if total == 0:
        return ''
    return f" [{hits/total*100:.0f}%hit]"

def print_report(program_name, seq, best_fast, best_slow,
                 best_cached, best_l1l2, ooo):
    W = 72
    print(f"\n{'═' * W}")
    print(f"  {program_name}")
    print(f"{'═' * W}")
    print(f"  {'config':<22} {'cycles':>7} {'instrs':>7} "
          f"{'IPC':>5} {'temps':>9}  {'résultat':>8}  prédicteur")
    print(f"  {'-'*22} {'-'*7} {'-'*7} {'-'*5} {'-'*9}  {'-'*8}  {'-'*16}")

    def row(label, r):
        prec = f" {r['precision']:.0f}%" if r['precision'] is not None else ''
        hit  = fmt_hit(r)
        pred = r.get('predictor', '—')
        print(f"  {label:<22} {r['cycles']:>7} {r['instructions']:>7} "
              f"{r['ipc']:>5.2f} {r['time_us']:>8.3f}µs "
              f" {r['result']:>8}{hit}  {pred}{prec}")

    row('séquentiel/rapide', seq)
    row('pipeline/rapide',   best_fast)
    row('pipeline/lente',    best_slow)
    row('pipeline/l1',       best_cached)
    row('pipeline/l1+l2',    best_l1l2)
    row('ooo/rapide',        ooo)

    # gains vs RAM lente
    ref = best_slow['cycles']
    if ref > 0:
        print(f"\n  gains vs RAM lente :")
        for label, r in [('rapide', best_fast), ('l1', best_cached),
                         ('l1+l2', best_l1l2), ('ooo', ooo)]:
            gain = (ref - r['cycles']) / ref * 100
            print(f"    {label:<8} → {gain:+.0f}%  ({r['cycles']} cycles)")

    # graphe ASCII
    rows = [
        ('séquentiel', seq['cycles']),
        ('rapide',     best_fast['cycles']),
        ('lente',      best_slow['cycles']),
        ('l1',         best_cached['cycles']),
        ('l1+l2',      best_l1l2['cycles']),
        ('ooo',        ooo['cycles']),
    ]
    max_c     = max(c for _, c in rows)
    bar_width = 40
    print()
    print(f"  ── cycles ──")
    for label, cycles in rows:
        bar_len = int(cycles / max_c * bar_width) if max_c else 0
        bar     = '#' * bar_len
        pad     = ' ' * (bar_width - bar_len)
        print(f"  {label:<12} |{bar}{pad}| {cycles}")
    print(f"{'═' * W}\n")

# ─── main ─────────────────────────────────────────────────────────────

def main():
    programs = PROGRAMS
    if len(sys.argv) > 1:
        names    = [n.lower() for n in sys.argv[1:]]
        programs = [p for p in PROGRAMS if p['name'].lower() in names]
        if not programs:
            print(f"programmes disponibles : {[p['name'] for p in PROGRAMS]}")
            sys.exit(1)

    for prog in programs:
        if not os.path.exists(prog['path']):
            print(f"[!] fichier introuvable : {prog['path']} — ignoré")
            continue

        init_path      = prog.get('init')
        results_fast   = {}
        results_slow   = {}
        results_cached = {}
        results_l1l2   = {}

        print(f"  {prog['name']} — séquentiel...        ", end='\r')
        seq = run_sequential(prog['path'], init_path)

        for pred_name, pred_fn in PREDICTORS:
            print(f"  {prog['name']} — {pred_name}...        ", end='\r')
            results_fast[pred_name]   = run_pipeline(
                prog['path'], init_path, pred_fn, pred_name)
            results_slow[pred_name]   = run_pipeline_slow(
                prog['path'], init_path, pred_fn, pred_name)
            results_cached[pred_name] = run_pipeline_cached(
                prog['path'], init_path, pred_fn, pred_name)
            results_l1l2[pred_name]   = run_pipeline_l1l2(
                prog['path'], init_path, pred_fn, pred_name)

        print(f"  {prog['name']} — ooo...               ", end='\r')
        ooo = run_ooo(prog['path'], init_path)

        print(f"  {prog['name']} — terminé.              ")

        print_report(
            prog['name'], seq,
            _best(results_fast)[1],
            _best(results_slow)[1],
            _best(results_cached)[1],
            _best(results_l1l2)[1],
            ooo,
        )

if __name__ == '__main__':
    main()
