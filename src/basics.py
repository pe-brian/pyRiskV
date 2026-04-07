def NAND(a, b): return not (a and b)

def NOT(a):     return NAND(a, a)
def AND(a, b):  return NOT(NAND(a, b))
def OR(a, b):   return NAND(NOT(a), NOT(b))

def ADD(a, b, c=False):
    if c:
        if   NOT(a): a, c = True, False
        elif NOT(b): b, c = True, False
    return ((AND(b, c), True) if AND(a, b) else (True, False)) if OR(a, b) else (False, False)
