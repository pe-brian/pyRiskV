# pyRiskV

Simulateur pédagogique d'un processeur RISC-V 32 bits (RV32I),
construit depuis les portes logiques NAND jusqu'à l'exécution
out-of-order (algorithme de Tomasulo) avec hiérarchie mémoire complète.

## Architecture du projet

```
riscv-sim/
├── src/
│   ├── basics.py           # portes logiques depuis NAND
│   ├── foo.py              # binarray, decrepr, conversions
│   ├── memory.py           # RAM rapide fictive
│   ├── slow_memory.py      # RAM avec latence réaliste (miss=50cy, hit=4cy)
│   ├── cache_l1.py         # cache L1 direct-mapped 4Ko, write-back, prefetch
│   ├── cache_l2.py         # cache L2 4-way LRU 64Ko, write-back
│   ├── alu.py              # ALU 32 bits + extension M (MUL, DIV, REM)
│   ├── decoder.py          # décodeur RV32I (6 formats : R, I, S, B, U, J)
│   ├── registers.py        # banc de 32 registres, x0 hardwired à 0
│   ├── cpu.py              # CPU séquentiel fetch/decode/execute
│   ├── cpu_pipeline.py     # pipeline 5 étages + forwarding + branch prediction
│   ├── cpu_ooo.py          # CPU out-of-order (Tomasulo) superscalaire
│   ├── branch_predictor.py # static, bimodal, gshare, tournament, BTB
│   ├── sim_config.py       # configuration cohérente avec validation CLI
│   └── mem_init.py         # initialisation mémoire depuis fichier JSON
│   └── tomasulo/
│       ├── config.py       # TomasuloConfig (RS, ROB, latences, superscalarité)
│       ├── rob.py          # Reorder Buffer (file circulaire)
│       ├── rs.py           # Reservation Stations (ALU, MUL, MEM)
│       ├── rat.py          # Register Alias Table (register renaming)
│       ├── cdb.py          # Common Data Bus (broadcast résultats)
│       └── functional_unit.py  # unités fonctionnelles
├── programs/
│   └── rust/
│       ├── fibonacci.rs/.elf/.bin   # fib(n), lit n depuis JSON
│       ├── bubblesort.rs/.elf/.bin  # tri à bulles, tableau depuis JSON
│       ├── random_access.rs/.elf/.bin
│       ├── seqsum.rs/.elf/.bin      # somme séquentielle (benchmark cache)
│       ├── link.ld                  # linker script (.text=0x0, .data=0x400)
│       ├── fibonacci.json           # { "memory": [{"addr":"0x400","value":8}] }
│       ├── bubblesort.json
│       ├── random_access.json
│       └── seqsum.json
├── main.py                 # CLI avec toutes les options
└── benchmark.py            # benchmark synthétique multi-programmes
```

## Modes d'exécution

### CPU séquentiel (défaut)
Exécution instruction par instruction, 1 cycle par instruction.

### Pipeline 5 étages (`--pipeline`)
IF → ID → EX → MEM → WB avec :
- Data forwarding (EX→EX, MEM→EX)
- Load-use hazard detection
- Branch prediction + BTB spéculatif

### Out-of-Order / Tomasulo (`--pipeline --ooo`)
Algorithme de Tomasulo complet :
- Reservation Stations (ALU, MUL, MEM)
- Reorder Buffer (commit in-order)
- Register Alias Table (élimine WAR/WAW hazards)
- Common Data Bus (broadcast résultats)
- Superscalarité configurable (`issue_width`, `commit_width`)

## Hiérarchie mémoire

| option | description |
|--------|-------------|
| défaut | RAM rapide fictive (0 latence) |
| `--slow-mem` | RAM lente réaliste (miss=50cy, hit=4cy) |
| `--l2` | RAM lente + cache L2 (LRU 4-way, 64Ko, 10cy) |
| `--cache` | RAM lente + L1 (direct-mapped, 4Ko, 1cy) + L2 |

Caches avec write-back et prefetching next-line.

## Prédicteurs de branchement

| option | description |
|--------|-------------|
| défaut | static not-taken |
| `--taken` | static taken |
| `--bimodal` | bimodal 2 bits |
| `--gshare` | gshare 4 bits d'historique |
| `--tournament` | tournament (bimodal + gshare) |
| `--no-btb` | désactive le BTB spéculatif |

## Installation

### Toolchain RISC-V (WSL Alpine)
```bash
apk add python3 gcc-riscv-none-elf binutils-riscv-none-elf make
```

### Rust pour RISC-V (PowerShell Windows)
```powershell
rustup target add riscv32i-unknown-none-elf
```

## Compilation d'un programme Rust

```powershell
# dans programs/rust/ — PowerShell Windows
rustc --target riscv32i-unknown-none-elf --edition 2021 `
      -C opt-level=1 -C panic=abort -C overflow-checks=no `
      -C link-arg=-Tlink.ld mon_programme.rs -o mon_programme.elf
```

```bash
# WSL — extraire le binaire
riscv-none-elf-objcopy -O binary \
    --only-section=.text \
    --only-section=.data \
    programs/rust/mon_programme.elf \
    programs/rust/mon_programme.bin
```

## Initialisation mémoire (JSON)

Chaque programme peut avoir un fichier `.json` du même nom pour initialiser
la mémoire avant l'exécution. Il est chargé automatiquement.

```json
{
    "description": "BubbleSort — 8 éléments",
    "entry": 0,
    "memory": [
        { "addr": "0x500", "value": 8 },
        { "addr": "0x400", "values": [64, 25, 12, 22, 11, 90, 3, 47] }
    ]
}
```

Types supportés : `value`, `values`, `bytes`, `string`, `file`.

## Exécution

```bash
# séquentiel
python3 main.py programs/rust/fibonacci.bin --no-regs

# pipeline avec cache L1+L2 et gshare
python3 main.py programs/rust/bubblesort.bin --pipeline --cache --gshare --no-regs

# out-of-order
python3 main.py programs/rust/bubblesort.bin --pipeline --ooo --no-regs

# JSON explicite
python3 main.py mon_prog.bin --mem-init mon_prog.json --no-regs

# debug cycle par cycle
python3 main.py programs/rust/fibonacci.bin --pipeline --ooo --debug --no-regs
```

## Benchmark

```bash
# tous les programmes
python3 benchmark.py

# programme spécifique
python3 benchmark.py BubbleSort
python3 benchmark.py Fibonacci SeqSum
```

Affiche un tableau synthétique avec cycles, IPC, précision du prédicteur
et gains par config mémoire, plus un graphe ASCII.

## Instructions supportées

| Type | Instructions |
|------|-------------|
| R    | ADD, SUB, AND, OR, XOR, SLL, SRL, SRA, SLT, SLTU |
| I    | ADDI, ANDI, ORI, XORI, SLTI, SLTIU, SLLI, SRLI, SRAI |
| I    | LW, LH, LB, LHU, LBU |
| S    | SW, SH, SB |
| B    | BEQ, BNE, BLT, BGE, BLTU, BGEU |
| U    | LUI, AUIPC |
| J    | JAL, JALR |
| M    | MUL, MULH, MULHU, MULHSU, DIV, DIVU, REM, REMU |
| Sys  | ECALL (exit, write), EBREAK |

## Résultats de référence (benchmark complet)

```
Fibonacci   — pipeline/rapide : 57 cy, IPC 0.86  | ooo : 64 cy, IPC 0.75
BubbleSort  — pipeline/rapide : 307 cy, IPC 0.85 | ooo : 530 cy, IPC 0.49
RandomAccess— pipeline/rapide : 465 cy, IPC 0.98 | ooo : 725 cy, IPC 0.63
SeqSum      — pipeline/rapide : 10257 cy, IPC 1.00| ooo : 16407 cy, IPC 0.62
```

## Superscalarité (OoO)

Configurable dans `src/tomasulo/config.py` :

```python
cfg = TomasuloConfig()
cfg.issue_width  = 2  # instructions émises par cycle
cfg.commit_width = 2  # instructions commitées par cycle
cfg.cdb_width    = 2  # broadcasts CDB par cycle
```
