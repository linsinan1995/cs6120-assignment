"""
a program that performs local value numbering algorithm

bril2json < ~/bril/examples/test/tdce/simple.bril | python3 lvn.py

"""

import sys
sys.path.append('../l2-cfg')
import cfg as _cfg
from dataclasses import dataclass
from collections import OrderedDict, namedtuple
from typing import Any
import itertools
from copy import deepcopy

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
        return f"op: {self.op}, args: [{self.rhs1}" + (", {self.rhs2}]" if self.rhs2 else "]")

    def get_args(self) -> set:
        if self.arglen == 2:
            return [self.rhs1, self.rhs2]
        elif self.arglen == 1:
            return [self.rhs1]
        return []

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
        return f"value: {self.content}, type: {_type}"

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
            # if isinstance(inst['value'], bool):
            #     inst['value'] = 1 if inst['value'] else 0
            return [Argument(inst['value'])]
        return [Argument(arg) for arg in inst['args']]

def opt_bb_lvn(cfg, canonicalize=lambda x:x, verbose=False):
    """perform basic block level DCE in CFG"""
    table = OrderedDict()
    hashmap = ValueIdxMap()
    # global target_label
    # target_label = None
    # branching_backet = dict()

    def get_entry_from_table(idx):
        # get table enty at index arg.content
        return next(itertools.islice(table.items(), idx, idx+1))

    def arithmetic_cf(inst):
        all_const = True
        if inst['op'] == 'add' and \
              not isinstance(inst['args'][0], str) and \
              not isinstance(inst['args'][1], str):
            inst = {
                'op': 'const',
                'value': inst['args'][0] + inst['args'][1]
            }
        elif inst['op'] == 'mul' and \
              not isinstance(inst['args'][0], str) and \
              not isinstance(inst['args'][1], str):
            inst = {
                'op': 'const',
                'value': inst['args'][0] * inst['args'][1]
            }

        return inst

    def perform(block, label_name):
        global target_label
        last_def =  dict() # (var, idx)->index of inst
        will_delete = []  # [idx of inst]

        for i, inst in enumerate(block):
            # todo: only dump branching info
            # if inst['op'] in _cfg._jmp:
            #     if inst['op'] == 'br':
            #         cond = inst['args'][0]
            #         var, _ = get_entry_from_table(hashmap.get_index(cond))
            #         # assume middle end will convert biop into a temp variable
            #         if var.arglen == 1 and var.rhs1.is_const:
            #             target_label = inst['labels'][0] if var.rhs1.content else inst['labels'][1]
            #             branching_backet[target_label] = (label_name, i)
            #             if verbose:
            #                 print(f"detect constant branching to '{target_label}', original instruction: {inst}, cond = {var}")
            #         else:
            #             target_label = inst['labels']
            #             branching_backet[target_label[0]] = (label_name, i)
            #             branching_backet[target_label[1]] = (label_name, i)

            #     elif inst['op'] == 'jmp':
            #         if verbose:
            #             print(f"detect jmp to '{inst['labels'][0]}'")
            #         target_label = inst['labels'][0]
            #         branching_backet[target_label] = (label_name, i)

            # call -> intraprocedual
            if 'dest' in inst and ('args' in inst or inst['op'] == 'const') and inst['op'] != 'call':
                op = inst.get('op')
                dest = inst.get('dest')
                args = Argument.build(inst, hashmap)
                args = [var if var.is_const else var.update(hashmap.get_index(var.content)) for var in args]

                # dce
                for arg in inst.get('args', []):
                    last_def.pop(arg, None)
                if dest in last_def:
                    will_delete.append(last_def[dest])

                last_def[dest] = i

                if verbose:
                    inst_prev = deepcopy(inst)
                    cf_flag = False

                # constant folding
                for j, arg in enumerate(args):
                    if not arg.is_const and len(table) > arg.content:
                        # get table enty at index arg.content
                        var, _ = get_entry_from_table(arg.content)
                        # var = table.items()[arg.content]
                        if var.op == 'const':
                            args[j] = Argument(var.rhs1.content)
                            # update on original block
                            inst["args"][j] = var.rhs1.content
                        cf_flag = True
                inst = arithmetic_cf(inst)
                if verbose and cf_flag:
                    print(f"constant folding! the instruction is converted from {inst_prev} to {inst}")

                hash_val = ValueTableIndex(inst['op'], args)
                hash_val = canonicalize(hash_val)

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

        # dce delete instructions
        for  idx in reversed(will_delete):
            if verbose:
                print("delete instruction: ", block.pop(idx))
            else:
                block.pop(idx)

        return block

    for i, (k, v) in enumerate(cfg.items()):
        # todo: overlapping backward branching & impact on farward branching

        # constant backward branching & there is no unknown branching before
        # if k in branching_backet and len(branching_backet) == 1:
        #     if verbose:
        #         print(f"detected removable backward branching to '{k}'")
        #     # delete block between branching_backet[k].i to current block
        #     label, insn_idx = branching_backet.pop(k)
        #     # delete insn
        #     cfg[label].block = cfg[label].block[(insn_idx-1):]
        #     start_delete = False
        #     for _k, _v in enumerate(cfg.items()):
        #         if _k == label:
        #             start_delete = True
        #         elif _k == k:
        #             break
        #         elif start_delete:
        #             cfg.pop(_k)

        cfg[k].block = perform(v.block, k)

    return cfg

def add_mul_canonicalize(val):
    if val.op in ('add', 'mul'):
        if val.arglen == 2 and val.rhs1 < val.rhs2:
            tmp = val.rhs1
            val.rhs1 = val.rhs2
            val.rhs2 = tmp
    return val

if __name__ == "__main__":
    functs = _cfg.load()
    parsed_cfg = _cfg.build_cfg(functs)
    n_inst, n_arg = _cfg.get_stat(parsed_cfg)
    print(f"In original CFG, there are # inst = {n_inst}, # variable used = {n_arg}")
    opt_cfg = opt_bb_lvn(parsed_cfg, canonicalize=add_mul_canonicalize, verbose=True)
    n_inst, n_arg = _cfg.get_stat(opt_cfg)
    print(f"In optimized CFG, there are # inst = {n_inst}, # variable used = {n_arg}")
