import json
import os


class MemoryInitializer():
    """
    Charge un fichier JSON de configuration mémoire.

    Formats supportés :
    - value   : un entier 32 bits
    - values  : liste d'entiers 32 bits
    - bytes   : liste d'octets
    - string  : chaîne ASCII (octets)
    - file    : charge un fichier binaire à cette adresse

    Exemple :
    {
        "entry": 0,
        "description": "BubbleSort n=8",
        "memory": [
            { "addr": "0x500", "value": 8 },
            { "addr": "0x400", "values": [64, 25, 12, 22, 11, 90, 3, 47] },
            { "addr": "0x600", "string": "Hello world" },
            { "addr": "0x700", "bytes": [0x01, 0x02, 0x03] }
        ]
    }
    """

    def __init__(self, json_path):
        with open(json_path, 'r') as f:
            self.config = json.load(f)
        self.path = json_path

    @property
    def entry_point(self):
        return self.config.get('entry', 0)

    @property
    def description(self):
        return self.config.get('description', '')

    def _parse_addr(self, addr):
        """Accepte '0x200' ou 512."""
        if isinstance(addr, str):
            return int(addr, 16) if addr.startswith('0x') else int(addr)
        return addr

    def apply(self, mem):
        """Applique la configuration à la mémoire."""
        base_dir = os.path.dirname(self.path)

        for entry in self.config.get('memory', []):
            addr = self._parse_addr(entry['addr'])

            if 'value' in entry:
                # un entier 32 bits
                val = entry['value']
                if hasattr(mem, '_access_latency'):
                    mem.write_word(addr, val, track=False)
                else:
                    mem.write_word(addr, val)

            elif 'values' in entry:
                # liste d'entiers 32 bits
                for i, val in enumerate(entry['values']):
                    a = addr + i * 4
                    if hasattr(mem, '_access_latency'):
                        mem.write_word(a, val, track=False)
                    else:
                        mem.write_word(a, val)

            elif 'bytes' in entry:
                # liste d'octets
                for i, byte in enumerate(entry['bytes']):
                    mem.write_byte(addr + i, byte & 0xFF)

            elif 'string' in entry:
                # chaîne ASCII null-terminée
                s = entry['string']
                for i, c in enumerate(s):
                    mem.write_byte(addr + i, ord(c))
                mem.write_byte(addr + len(s), 0)  # null terminator

            elif 'file' in entry:
                # charge un fichier binaire
                file_path = os.path.join(base_dir, entry['file'])
                with open(file_path, 'rb') as f:
                    data = f.read()
                for i, byte in enumerate(data):
                    mem.write_byte(addr + i, byte)

    @classmethod
    def from_args(cls, args):
        """Cherche --mem-init <fichier.json> dans les arguments."""
        for i, arg in enumerate(args):
            if arg == '--mem-init' and i + 1 < len(args):
                return cls(args[i + 1])
        return None

    def dump(self):
        print(f"─── mémoire init ────────────────────────────────────")
        if self.description:
            print(f"  description  : {self.description}")
        print(f"  entry point  : {self.entry_point:#010x}")
        for entry in self.config.get('memory', []):
            addr = self._parse_addr(entry['addr'])
            if 'value' in entry:
                print(f"  {addr:#010x} ← {entry['value']}")
            elif 'values' in entry:
                print(f"  {addr:#010x} ← {len(entry['values'])} mots")
            elif 'bytes' in entry:
                print(f"  {addr:#010x} ← {len(entry['bytes'])} octets")
            elif 'string' in entry:
                print(f"  {addr:#010x} ← \"{entry['string'][:20]}\"")
            elif 'file' in entry:
                print(f"  {addr:#010x} ← file:{entry['file']}")
        print(f"─────────────────────────────────────────────────────")

    @classmethod
    def resolve(cls, bin_path, args):
        """
        Résout le meilleur initialiseur disponible :
        1. --mem-init explicite dans les args
        2. fichier .json du même nom que le .bin
        3. None
        """
        init = cls.from_args(args)
        if init is None:
            init = cls.from_bin(bin_path)
        return init
    
    @classmethod
    def from_bin(cls, bin_path):
        """Cherche automatiquement un .json du même nom."""
        json_path = os.path.splitext(bin_path)[0] + '.json'
        if os.path.exists(json_path):
            return cls(json_path)
        return None