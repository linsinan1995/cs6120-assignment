"""
a program that performs local value numbering algorithm

bril2json < ~/bril/examples/test/tdce/simple.bril | python3 lvn.py

value table:
1. give index to a variable when its value is changed
2. 
"""

import sys
sys.path.append('../l2-cfg')
import cfg
from dataclasses import dataclass
from collections import OrderedDict, namedtuple
from typing import Any

@dataclass(unsafe_hash=True)
class ValueTableIndex:
    arglen:int
    op:str
    rhs1:Any
    rhs2:Any
    def __init__(self, op, rhs:list):
        self.arglen = len(rhs)
        if len(rhs) == 0:
            self.op = op
            self.rhs1 = None
            self.rhs2 = None
        elif len(rhs) == 1:
            self.op = op
            self.rhs1 = rhs[0]
            self.rhs2 = None
        elif len(rhs) == 2:
            self.op = op
            self.rhs1 = rhs[0]
            self.rhs2 = rhs[1]
        else:
            raise ValueError(f"invalid argument nunmber: {inst}!")

    def __repr__(self):
        return f"op: {self.op}, args: [{self.rhs1}, {self.rhs1}]"

class ValueIdxMap:
    """manage mapping between variable and its index and also index assignment"""
    def __init__(self):
        self.var_to_index = dict()
        self.index_to_var = dict()
        self.cur_idx = 0

    def add(self, var, idx):
        """add a variable into variable hashmap"""
        self.var_to_index[var] = idx
        self.index_to_var[idx] = var
        # self.cur_idx += 1

    def get_index(self, var):
        return self.var_to_index.get(var, None)

    def set_index(self, var, idx):
        self.var_to_index[var] = idx

    def get_var(self, idx):
        return self.index_to_var.get(idx, None)

    def assign_idx(self):
        self.cur_idx += 1
        return self.cur_idx - 1

class Argument:
    """argument class for distinguishing variable and constant"""
    def __init__(self, content):
        self.content = content
        self.is_const = not isinstance(content, str)

    def update(self, new_content):
        """update argument content(from text form variable to its idx in variable hashmap"""
        assert not self.is_const
        self.content = new_content
        return self

    def __repr__(self):
        if self.is_const  :
            _type = "constant"
        else:
            _type = "variable" if isinstance(self.content, str) else "ref"
        return f"(arg: {self.content}, type: {_type})"

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.content == other.content and \
            self.is_const == other.is_const

    def __lt__(self, other):
        if self.is_const == other.is_const:
            return self.content.__lt__(other.content)

        return self.is_const

    def __hash__(self):
        return hash(self.content) ^ hash(self.is_const)

    @staticmethod
    def build(inst, variable_map):
        if inst['op'] == 'const':
            # variable_map.add(inst['dest'])
            return [Argument(inst['value'])]
        return [Argument(arg) for arg in inst['args']]

def opt_bb_lvn(cfg, canonicalize=lambda x:x):
    """perform basic block level DCE in CFG"""
    table = OrderedDict()
    hashmap = ValueIdxMap()

    def perform(block):
        for inst in block:
            # call -> intraprocedual
            if 'dest' in inst and ('args' in inst or inst['op'] == 'const') and inst['op'] != 'call':
                op = inst.get('op')
                dest = inst.get('dest')
                args = Argument.build(inst, hashmap)
                args = [var if var.is_const else var.update(hashmap.get_index(var.content)) for var in args]
                hash_val = ValueTableIndex(inst['op'], args)
                hash_val = canonicalize(hash_val)

                # dce

                if hash_val in table:
                    idx, hashed_dest = table[hash_val]
                    # cse: skip constant assignment
                    hashmap.set_index(dest, idx)
                    if inst['op'] != 'const':
                        inst.update({
                            'op': 'id',
                            'args': [hashed_dest],
                        })
                else:
                    # add into value table
                    table[hash_val] = hashmap.assign_idx(), dest

                # update variable dict
                if not hashmap.get_index(dest):
                    idx, _ = table[hash_val]
                    hashmap.add(dest, idx)

            # print(table)
        return block

    for k, v in cfg.items():
        cfg[k].block = perform(v.block)

    return cfg

def add_mul_canonicalize(val):
    if val.op in ('add', 'mul'):
        if val.arglen == 2 and val.rhs1 < val.rhs2:
            tmp = val.rhs1
            val.rhs1 = val.rhs2
            val.rhs2 = tmp
    return val

if __name__ == "__main__":
    functs = cfg.load()
    parsed_cfg = cfg.build_cfg(functs)
    n_inst, n_arg = cfg.get_stat(parsed_cfg)
    print(f"In original CFG, there are # inst = {n_inst}, # variable used = {n_arg}")
    opt_cfg = opt_bb_lvn(parsed_cfg, canonicalize=add_mul_canonicalize)
    n_inst, n_arg = cfg.get_stat(opt_cfg)
    print(f"In optimized CFG, there are # inst = {n_inst}, # variable used = {n_arg}")
