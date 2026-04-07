import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from sim_config import SimConfig


def main():
    MEMORY_SIZE = 16384
    ENTRY_POINT = 0
    MAX_STEPS   = 500000
    CLOCK_HZ    = 100_000_000

    # aide
    if '--help' in sys.argv or len(sys.argv) < 2:
        print("usage: python main.py <programme.bin> [options]")
        SimConfig.help()
        sys.exit(0 if '--help' in sys.argv else 1)

    bin_path = sys.argv[1]
    debug    = '--debug'    in sys.argv
    no_regs  = '--no-regs'  in sys.argv
    pipeline = '--pipeline' in sys.argv

    if not os.path.exists(bin_path):
        print(f"fichier introuvable : {bin_path}")
        sys.exit(1)

    # ─── configuration ────────────────────────────────────────────
    cfg = SimConfig.from_args(sys.argv)
    cfg.dump()

    # ─── mémoire ──────────────────────────────────────────────────
    mem = cfg.build_memory(MEMORY_SIZE)
    nb  = mem.load_binary(bin_path, start=ENTRY_POINT)

    # initialisation des données
    nb = mem.load_binary(bin_path, start=ENTRY_POINT)

    from mem_init import MemoryInitializer

    # cherche un fichier .json associé au .bin
    init = MemoryInitializer.resolve(bin_path, sys.argv)
    if init:
        init.apply(mem)
        init.dump()

    print(f"chargement : {bin_path}")
    print(f"taille     : {nb} octets ({nb // 4} instructions)")
    print(f"mode       : {'pipeline' if pipeline else 'séquentiel'}")
    print("─" * 56)

    # ─── exécution ────────────────────────────────────────────────
    if pipeline:
        cpu    = cfg.build_pipeline(mem)
        cpu.pc = ENTRY_POINT
        steps  = cpu.run(max_cycles=MAX_STEPS, debug=debug)
        print("─" * 56)
        print(f"cycles       : {cpu.cycles}")
        print(f"instructions : {cpu.instructions}")
        print(f"IPC          : {cpu.instructions/cpu.cycles:.2f}")
        print(f"temps simulé : {cpu.elapsed_us():.3f} µs @ {CLOCK_HZ//1_000_000} MHz")
        print(f"résultat     : a0 = {cpu.regs.read(10)} "
              f"({cpu.regs.read(10):#010x})")
    else:
        from cpu import CPU
        cpu    = CPU(mem, clock_hz=CLOCK_HZ)
        cpu.pc = ENTRY_POINT
        steps  = cpu.run(max_steps=MAX_STEPS, debug=debug)
        print("─" * 56)
        print(f"arrêt après  : {steps} instructions | {cpu.cycles} cycles")
        print(f"temps simulé : {cpu.elapsed_us():.3f} µs @ {CLOCK_HZ//1_000_000} MHz")
        print(f"résultat     : a0 = {cpu.regs.read(10)} "
              f"({cpu.regs.read(10):#010x})")

    if not no_regs:
        print()
        cpu.regs.dump()

    # ─── stats mémoire ────────────────────────────────────────────
    from cache_l1 import CacheL1
    from cache_l2 import CacheL2
    from slow_memory import SlowMemory

    if isinstance(mem, CacheL1):
        print()
        mem.dump()
        if isinstance(mem.mem, CacheL2):
            mem.mem.dump()
            mem.mem.mem.dump()
        else:
            mem.mem.dump()
    elif isinstance(mem, CacheL2):
        print()
        mem.dump()
        mem.mem.dump()
    elif isinstance(mem, SlowMemory):
        print()
        mem.dump()


if __name__ == '__main__':
    main()