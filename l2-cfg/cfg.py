"""
a program that parses instructions stream to cfg

bril2json < ~/bril/test/interp/jmp.bril | python3 cfg.py
"""

import json
import sys
from dataclasses import dataclass
from collections import OrderedDict

# call is not a terminator
_term    = set(['jmp', 'br', 'ret'])
_jmp     = set(['jmp', 'br'])
_no_succ = set(['ret'])

@dataclass(init=False)
class CfgItem:
    name:  str
    block: list
    succ:  list # successor
    def __init__ (self, name, block):
        self.name = name
        self.block = block
        self.succ = []

def load():
    """read json-formatted standard input"""
    prog = json.load(sys.stdin)
    return prog

def build_block(insts):
    """parse Inst to Basic Block"""
    bblock = []
    for inst in insts:
        if 'label' in inst:
            yield bblock
            bblock = [inst]
        elif 'op' not in inst:
            continue
        elif inst['op'] in _term:
            bblock.append(inst)
            yield bblock
            bblock = []
        else:
            # normal instruction
            bblock.append(inst)

    yield bblock

def build_cfg(functs):
    """parse IR to CFG"""
    name_template = "bb_"
    cnt = 0
    cfg = OrderedDict()
    for inst_list in functs['functions']:
        for block in build_block(inst_list['instrs']):
            # skip empty block
            if len(block) == 0:
                continue
            # get name
            if 'label' in block[0]:
                cfg[block[0]['label']] = CfgItem(name=block[0]['label'], block=block[1:])
            else:
                cfg[f"{name_template}{cnt}"] = CfgItem(name=f"{name_template}{cnt}", block=block)
                cnt += 1

    cur_succ = []
    for k, v in reversed(cfg.items()):
        if len(v.block) == 0:
            continue
        # label only bb does not exist
        if v.block[-1]['op'] in _jmp:
            for succ_label in v.block[-1]['labels']:
                v.succ.append(succ_label)
        elif v.block[-1]['op'] in _no_succ:
            continue
        else:
            v.succ = cur_succ
            cur_succ = [v.name]
    return cfg

def visualize_cfg(cfg):
    """input a CFG, and output a dot script for the CFG structure"""
    from graphviz import Digraph
    length = len(cfg)
    if length == 0:
        print("Empty cfg.")
        return

    g = Digraph('G', filename='cfg.gv')
    g.node('start', shape='Mdiamond')
    g.node('end', shape='Msquare')

    for idx, (k, v) in enumerate(cfg.items()):
        if idx == 0:
            g.edge('start', k)
        if idx == length-1:
            g.edge(k, 'end')

        if v.succ:
            for one_succ in v.succ:
                g.edge(k, one_succ)
    g.save()

def get_stat(cfg):
    """get the number of instruction in a CFG"""
    n_inst = 0
    n_arg = 0
    for k, v in cfg.items():
        for inst in v.block:
            n_inst += 1
            n_arg += len([arg for arg in inst.get('args', []) if isinstance(arg, str)] and arg not in ('True', 'False')) +\
                    1 if inst.get('dest', False) else 0
    return n_inst, n_arg

if __name__ == "__main__":
    functs = load()
    cfg = build_cfg(functs)
    for k, v in cfg.items():
        print(f"name:{k}")
        print(f"succ:{'None' if len(v.succ) == 0 else ''}")
        for s in v.succ:
            print("  ", s)
        print("inst:")
        for inst in v.block:
            print("  ", inst)
        print("=============================")
    visualize_cfg(cfg)
