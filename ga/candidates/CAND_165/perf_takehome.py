"""
# Anthropic's Original Performance Engineering Take-home (Release version)

Copyright Anthropic PBC 2026. Permission is granted to modify and use, but not
to publish or redistribute your solutions so it's hard to find spoilers.

# Task

- Optimize the kernel (in KernelBuilder.build_kernel) as much as possible in the
  available time, as measured by test_kernel_cycles on a frozen separate copy
  of the simulator.

Validate your results using `python tests/submission_tests.py` without modifying
anything in the tests/ folder.

We recommend you look through problem.py next.
"""

from collections import defaultdict
import random
import unittest

from problem import (
    Engine,
    DebugInfo,
    SLOT_LIMITS,
    VLEN,
    N_CORES,
    SCRATCH_SIZE,
    Machine,
    Tree,
    Input,
    HASH_STAGES,
    reference_kernel,
    build_mem_image,
    reference_kernel2,
)


class KernelBuilder:
    def __init__(self):
        self.instrs = []
        self.scratch = {}
        self.scratch_debug = {}
        self.scratch_ptr = 0
        self.const_map = {}
        self.pending = {}

    def debug_info(self):
        return DebugInfo(scratch_map=self.scratch_debug)

    def build(self, slots: list[tuple[Engine, tuple]], vliw: bool = False):
        instrs = []
        for engine, slot in slots:
            instrs.append({engine: [slot]})
        return instrs

    def add(self, engine, slot):
        self.instrs.append({engine: [slot]})

    def flush_pending(self):
        if self.pending:
            self.instrs.append(self.pending)
            self.pending = {}

    def add_packed(self, engine, slot):
        limit = SLOT_LIMITS.get(engine, 1)
        if engine in self.pending and len(self.pending[engine]) >= limit:
            self.flush_pending()
        if engine not in self.pending:
            self.pending[engine] = []
        self.pending[engine].append(slot)

    def alloc_scratch(self, name=None, length=1):
        addr = self.scratch_ptr
        if name is not None:
            self.scratch[name] = addr
            self.scratch_debug[addr] = (name, length)
        self.scratch_ptr += length
        assert self.scratch_ptr <= SCRATCH_SIZE, "Out of scratch space"
        return addr

    def scratch_const(self, val, name=None):
        if val not in self.const_map:
            addr = self.alloc_scratch(name)
            self.add("load", ("const", addr, val))
            self.const_map[val] = addr
        return self.const_map[val]

    def build_hash(self, val_hash_addr, tmp1, tmp2, round, i):
        slots = []

        for hi, (op1, val1, op2, op3, val3) in enumerate(HASH_STAGES):
            slots.append(("alu", (op1, tmp1, val_hash_addr, self.scratch_const(val1))))
            slots.append(("alu", (op3, tmp2, val_hash_addr, self.scratch_const(val3))))
            slots.append(("alu", (op2, val_hash_addr, tmp1, tmp2)))
            slots.append(("debug", ("compare", val_hash_addr, (round, i, "hash_stage", hi))))

        return slots

    def build_kernel(
        self, forest_height: int, n_nodes: int, batch_size: int, rounds: int
    ):
        """
        SIMD vectorized implementation using valu, vload, vstore.
        Processes VLEN elements per iteration.
        """
        tmp1 = self.alloc_scratch("tmp1", VLEN)
        tmp2 = self.alloc_scratch("tmp2", VLEN)
        tmp3 = self.alloc_scratch("tmp3", VLEN)
        init_vars = [
            "rounds",
            "n_nodes",
            "batch_size",
            "forest_height",
            "forest_values_p",
            "inp_indices_p",
            "inp_values_p",
        ]
        scalar_tmp = self.alloc_scratch("scalar_tmp")
        for v in init_vars:
            self.alloc_scratch(v, 1)
        for i, v in enumerate(init_vars):
            self.add("load", ("const", scalar_tmp, i))
            self.add("load", ("load", self.scratch[v], scalar_tmp))

        zero_const = self.scratch_const(0)
        one_const = self.scratch_const(1)
        two_const = self.scratch_const(2)

        zero_vec = self.alloc_scratch("zero_vec", VLEN)
        one_vec = self.alloc_scratch("one_vec", VLEN)
        two_vec = self.alloc_scratch("two_vec", VLEN)
        self.add("valu", ("vbroadcast", zero_vec, zero_const))
        self.add("valu", ("vbroadcast", one_vec, one_const))
        self.add("valu", ("vbroadcast", two_vec, two_const))

        n_nodes_vec = self.alloc_scratch("n_nodes_vec", VLEN)
        self.add("valu", ("vbroadcast", n_nodes_vec, self.scratch["n_nodes"]))

        forest_p_vec = self.alloc_scratch("forest_p_vec", VLEN)
        hash_const_vecs = []
        for hi, (op1, val1, op2, op3, val3) in enumerate(HASH_STAGES):
            const1 = self.scratch_const(val1)
            const3 = self.scratch_const(val3)
            const1_vec = self.alloc_scratch(f"const1_vec_{hi}", VLEN)
            const3_vec = self.alloc_scratch(f"const3_vec_{hi}", VLEN)
            self.add("valu", ("vbroadcast", const1_vec, const1))
            self.add("valu", ("vbroadcast", const3_vec, const3))
            hash_const_vecs.append((const1_vec, const3_vec))

        self.add("flow", ("pause",))
        self.add("debug", ("comment", "Starting SIMD loop"))

        vec_idx = self.alloc_scratch("vec_idx", VLEN)
        vec_val = self.alloc_scratch("vec_val", VLEN)
        vec_node_val = self.alloc_scratch("vec_node_val", VLEN)
        vec_addr = self.alloc_scratch("vec_addr", VLEN)

        num_vec_iters = batch_size // VLEN

        scalar_tmp2 = self.alloc_scratch("scalar_tmp2")
        scalar_tmp3 = self.alloc_scratch("scalar_tmp3")
        scalar_tmp4 = self.alloc_scratch("scalar_tmp4")

        vec_idx_b = self.alloc_scratch("vec_idx_b", VLEN)
        vec_val_b = self.alloc_scratch("vec_val_b", VLEN)
        vec_node_val_b = self.alloc_scratch("vec_node_val_b", VLEN)
        vec_addr_b = self.alloc_scratch("vec_addr_b", VLEN)
        tmp1_b = self.alloc_scratch("tmp1_b", VLEN)
        tmp2_b = self.alloc_scratch("tmp2_b", VLEN)
        tmp3_b = self.alloc_scratch("tmp3_b", VLEN)

        vec_idx_c = self.alloc_scratch("vec_idx_c", VLEN)
        vec_val_c = self.alloc_scratch("vec_val_c", VLEN)
        vec_node_val_c = self.alloc_scratch("vec_node_val_c", VLEN)
        vec_addr_c = self.alloc_scratch("vec_addr_c", VLEN)
        tmp1_c = self.alloc_scratch("tmp1_c", VLEN)
        tmp2_c = self.alloc_scratch("tmp2_c", VLEN)
        tmp3_c = self.alloc_scratch("tmp3_c", VLEN)

        vec_idx_d = self.alloc_scratch("vec_idx_d", VLEN)
        vec_val_d = self.alloc_scratch("vec_val_d", VLEN)
        vec_node_val_d = self.alloc_scratch("vec_node_val_d", VLEN)
        vec_addr_d = self.alloc_scratch("vec_addr_d", VLEN)
        tmp1_d = self.alloc_scratch("tmp1_d", VLEN)
        tmp2_d = self.alloc_scratch("tmp2_d", VLEN)
        tmp3_d = self.alloc_scratch("tmp3_d", VLEN)

        scalar_tmp5 = self.alloc_scratch("scalar_tmp5")
        scalar_tmp6 = self.alloc_scratch("scalar_tmp6")
        scalar_tmp7 = self.alloc_scratch("scalar_tmp7")
        scalar_tmp8 = self.alloc_scratch("scalar_tmp8")

        vec_idx_e = self.alloc_scratch("vec_idx_e", VLEN)
        vec_val_e = self.alloc_scratch("vec_val_e", VLEN)
        vec_node_val_e = self.alloc_scratch("vec_node_val_e", VLEN)
        vec_addr_e = self.alloc_scratch("vec_addr_e", VLEN)
        tmp1_e = self.alloc_scratch("tmp1_e", VLEN)
        tmp2_e = self.alloc_scratch("tmp2_e", VLEN)
        tmp3_e = self.alloc_scratch("tmp3_e", VLEN)

        vec_idx_f = self.alloc_scratch("vec_idx_f", VLEN)
        vec_val_f = self.alloc_scratch("vec_val_f", VLEN)
        vec_node_val_f = self.alloc_scratch("vec_node_val_f", VLEN)
        vec_addr_f = self.alloc_scratch("vec_addr_f", VLEN)
        tmp1_f = self.alloc_scratch("tmp1_f", VLEN)
        tmp2_f = self.alloc_scratch("tmp2_f", VLEN)
        tmp3_f = self.alloc_scratch("tmp3_f", VLEN)

        vec_idx_g = self.alloc_scratch("vec_idx_g", VLEN)
        vec_val_g = self.alloc_scratch("vec_val_g", VLEN)
        vec_node_val_g = self.alloc_scratch("vec_node_val_g", VLEN)
        vec_addr_g = self.alloc_scratch("vec_addr_g", VLEN)
        tmp1_g = self.alloc_scratch("tmp1_g", VLEN)
        tmp2_g = self.alloc_scratch("tmp2_g", VLEN)
        tmp3_g = self.alloc_scratch("tmp3_g", VLEN)

        vec_idx_h = self.alloc_scratch("vec_idx_h", VLEN)
        vec_val_h = self.alloc_scratch("vec_val_h", VLEN)
        vec_node_val_h = self.alloc_scratch("vec_node_val_h", VLEN)
        vec_addr_h = self.alloc_scratch("vec_addr_h", VLEN)
        tmp1_h = self.alloc_scratch("tmp1_h", VLEN)
        tmp2_h = self.alloc_scratch("tmp2_h", VLEN)
        tmp3_h = self.alloc_scratch("tmp3_h", VLEN)

        scalar_tmp9 = self.alloc_scratch("scalar_tmp9")
        scalar_tmp10 = self.alloc_scratch("scalar_tmp10")
        scalar_tmp11 = self.alloc_scratch("scalar_tmp11")
        scalar_tmp12 = self.alloc_scratch("scalar_tmp12")
        scalar_tmp13 = self.alloc_scratch("scalar_tmp13")
        scalar_tmp14 = self.alloc_scratch("scalar_tmp14")
        scalar_tmp15 = self.alloc_scratch("scalar_tmp15")
        scalar_tmp16 = self.alloc_scratch("scalar_tmp16")

        self.instrs.append({
            "valu": [
                ("vbroadcast", forest_p_vec, self.scratch["forest_values_p"]),
            ]
        })

        for round in range(rounds):
            vi = 0
            while vi < num_vec_iters:
                if vi + 7 < num_vec_iters:
                    base_i_a = vi * VLEN
                    base_i_b = (vi + 1) * VLEN
                    base_i_c = (vi + 2) * VLEN
                    base_i_d = (vi + 3) * VLEN
                    base_i_e = (vi + 4) * VLEN
                    base_i_f = (vi + 5) * VLEN
                    base_i_g = (vi + 6) * VLEN
                    base_i_h = (vi + 7) * VLEN
                    base_const_a = self.scratch_const(base_i_a)
                    base_const_b = self.scratch_const(base_i_b)
                    base_const_c = self.scratch_const(base_i_c)
                    base_const_d = self.scratch_const(base_i_d)
                    base_const_e = self.scratch_const(base_i_e)
                    base_const_f = self.scratch_const(base_i_f)
                    base_const_g = self.scratch_const(base_i_g)
                    base_const_h = self.scratch_const(base_i_h)

                    self.instrs.append({
                        "alu": [
                            ("+", scalar_tmp, self.scratch["inp_indices_p"], base_const_a),
                            ("+", scalar_tmp2, self.scratch["inp_values_p"], base_const_a),
                            ("+", scalar_tmp3, self.scratch["inp_indices_p"], base_const_b),
                            ("+", scalar_tmp4, self.scratch["inp_values_p"], base_const_b),
                            ("+", scalar_tmp5, self.scratch["inp_indices_p"], base_const_c),
                            ("+", scalar_tmp6, self.scratch["inp_values_p"], base_const_c),
                            ("+", scalar_tmp7, self.scratch["inp_indices_p"], base_const_d),
                            ("+", scalar_tmp8, self.scratch["inp_values_p"], base_const_d),
                            ("+", scalar_tmp9, self.scratch["inp_indices_p"], base_const_e),
                            ("+", scalar_tmp10, self.scratch["inp_values_p"], base_const_e),
                            ("+", scalar_tmp11, self.scratch["inp_indices_p"], base_const_f),
                            ("+", scalar_tmp12, self.scratch["inp_values_p"], base_const_f),
                        ]
                    })
                    self.instrs.append({
                        "alu": [
                            ("+", scalar_tmp13, self.scratch["inp_indices_p"], base_const_g),
                            ("+", scalar_tmp14, self.scratch["inp_values_p"], base_const_g),
                            ("+", scalar_tmp15, self.scratch["inp_indices_p"], base_const_h),
                            ("+", scalar_tmp16, self.scratch["inp_values_p"], base_const_h),
                        ],
                        "load": [
                            ("vload", vec_idx, scalar_tmp),
                            ("vload", vec_val, scalar_tmp2),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("vload", vec_idx_b, scalar_tmp3),
                            ("vload", vec_val_b, scalar_tmp4),
                        ],
                        "valu": [
                            ("+", vec_addr, forest_p_vec, vec_idx),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("vload", vec_idx_c, scalar_tmp5),
                            ("vload", vec_val_c, scalar_tmp6),
                        ],
                        "valu": [
                            ("+", vec_addr_b, forest_p_vec, vec_idx_b),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("vload", vec_idx_d, scalar_tmp7),
                            ("vload", vec_val_d, scalar_tmp8),
                        ],
                        "valu": [
                            ("+", vec_addr_c, forest_p_vec, vec_idx_c),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("vload", vec_idx_e, scalar_tmp9),
                            ("vload", vec_val_e, scalar_tmp10),
                        ],
                        "valu": [
                            ("+", vec_addr_d, forest_p_vec, vec_idx_d),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("vload", vec_idx_f, scalar_tmp11),
                            ("vload", vec_val_f, scalar_tmp12),
                        ],
                        "valu": [
                            ("+", vec_addr_e, forest_p_vec, vec_idx_e),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("vload", vec_idx_g, scalar_tmp13),
                            ("vload", vec_val_g, scalar_tmp14),
                        ],
                        "valu": [
                            ("+", vec_addr_f, forest_p_vec, vec_idx_f),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("vload", vec_idx_h, scalar_tmp15),
                            ("vload", vec_val_h, scalar_tmp16),
                        ],
                        "valu": [
                            ("+", vec_addr_g, forest_p_vec, vec_idx_g),
                        ]
                    })

                    self.instrs.append({
                        "valu": [
                            ("+", vec_addr_h, forest_p_vec, vec_idx_h),
                        ],
                        "load": [
                            ("load_offset", vec_node_val, vec_addr, 0),
                            ("load_offset", vec_node_val, vec_addr, 1),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val, vec_addr, 2),
                            ("load_offset", vec_node_val, vec_addr, 3),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val, vec_addr, 4),
                            ("load_offset", vec_node_val, vec_addr, 5),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val, vec_addr, 6),
                            ("load_offset", vec_node_val, vec_addr, 7),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_b, vec_addr_b, 0),
                            ("load_offset", vec_node_val_b, vec_addr_b, 1),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_b, vec_addr_b, 2),
                            ("load_offset", vec_node_val_b, vec_addr_b, 3),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_b, vec_addr_b, 4),
                            ("load_offset", vec_node_val_b, vec_addr_b, 5),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_b, vec_addr_b, 6),
                            ("load_offset", vec_node_val_b, vec_addr_b, 7),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_c, vec_addr_c, 0),
                            ("load_offset", vec_node_val_c, vec_addr_c, 1),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_c, vec_addr_c, 2),
                            ("load_offset", vec_node_val_c, vec_addr_c, 3),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_c, vec_addr_c, 4),
                            ("load_offset", vec_node_val_c, vec_addr_c, 5),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_c, vec_addr_c, 6),
                            ("load_offset", vec_node_val_c, vec_addr_c, 7),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_d, vec_addr_d, 0),
                            ("load_offset", vec_node_val_d, vec_addr_d, 1),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_d, vec_addr_d, 2),
                            ("load_offset", vec_node_val_d, vec_addr_d, 3),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_d, vec_addr_d, 4),
                            ("load_offset", vec_node_val_d, vec_addr_d, 5),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_d, vec_addr_d, 6),
                            ("load_offset", vec_node_val_d, vec_addr_d, 7),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_e, vec_addr_e, 0),
                            ("load_offset", vec_node_val_e, vec_addr_e, 1),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_e, vec_addr_e, 2),
                            ("load_offset", vec_node_val_e, vec_addr_e, 3),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_e, vec_addr_e, 4),
                            ("load_offset", vec_node_val_e, vec_addr_e, 5),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_e, vec_addr_e, 6),
                            ("load_offset", vec_node_val_e, vec_addr_e, 7),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_f, vec_addr_f, 0),
                            ("load_offset", vec_node_val_f, vec_addr_f, 1),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_f, vec_addr_f, 2),
                            ("load_offset", vec_node_val_f, vec_addr_f, 3),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_f, vec_addr_f, 4),
                            ("load_offset", vec_node_val_f, vec_addr_f, 5),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_f, vec_addr_f, 6),
                            ("load_offset", vec_node_val_f, vec_addr_f, 7),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_g, vec_addr_g, 0),
                            ("load_offset", vec_node_val_g, vec_addr_g, 1),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_g, vec_addr_g, 2),
                            ("load_offset", vec_node_val_g, vec_addr_g, 3),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_g, vec_addr_g, 4),
                            ("load_offset", vec_node_val_g, vec_addr_g, 5),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_g, vec_addr_g, 6),
                            ("load_offset", vec_node_val_g, vec_addr_g, 7),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_h, vec_addr_h, 0),
                            ("load_offset", vec_node_val_h, vec_addr_h, 1),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_h, vec_addr_h, 2),
                            ("load_offset", vec_node_val_h, vec_addr_h, 3),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_h, vec_addr_h, 4),
                            ("load_offset", vec_node_val_h, vec_addr_h, 5),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("load_offset", vec_node_val_h, vec_addr_h, 6),
                            ("load_offset", vec_node_val_h, vec_addr_h, 7),
                        ]
                    })
                    self.instrs.append({
                        "valu": [
                            ("^", vec_val, vec_val, vec_node_val),
                            ("^", vec_val_b, vec_val_b, vec_node_val_b),
                            ("^", vec_val_c, vec_val_c, vec_node_val_c),
                            ("^", vec_val_d, vec_val_d, vec_node_val_d),
                            ("^", vec_val_e, vec_val_e, vec_node_val_e),
                            ("^", vec_val_f, vec_val_f, vec_node_val_f),
                        ]
                    })
                    self.instrs.append({
                        "valu": [
                            ("^", vec_val_g, vec_val_g, vec_node_val_g),
                            ("^", vec_val_h, vec_val_h, vec_node_val_h),
                        ]
                    })

                    for hi, (op1, val1, op2, op3, val3) in enumerate(HASH_STAGES):
                        const1_vec, const3_vec = hash_const_vecs[hi]
                        self.instrs.append({
                            "valu": [
                                (op1, tmp1, vec_val, const1_vec),
                                (op3, tmp2, vec_val, const3_vec),
                                (op1, tmp1_b, vec_val_b, const1_vec),
                                (op3, tmp2_b, vec_val_b, const3_vec),
                                (op1, tmp1_c, vec_val_c, const1_vec),
                                (op3, tmp2_c, vec_val_c, const3_vec),
                            ]
                        })
                        self.instrs.append({
                            "valu": [
                                (op1, tmp1_d, vec_val_d, const1_vec),
                                (op3, tmp2_d, vec_val_d, const3_vec),
                                (op1, tmp1_e, vec_val_e, const1_vec),
                                (op3, tmp2_e, vec_val_e, const3_vec),
                                (op1, tmp1_f, vec_val_f, const1_vec),
                                (op3, tmp2_f, vec_val_f, const3_vec),
                            ]
                        })
                        self.instrs.append({
                            "valu": [
                                (op1, tmp1_g, vec_val_g, const1_vec),
                                (op3, tmp2_g, vec_val_g, const3_vec),
                                (op1, tmp1_h, vec_val_h, const1_vec),
                                (op3, tmp2_h, vec_val_h, const3_vec),
                                (op2, vec_val, tmp1, tmp2),
                                (op2, vec_val_b, tmp1_b, tmp2_b),
                            ]
                        })
                        self.instrs.append({
                            "valu": [
                                (op2, vec_val_c, tmp1_c, tmp2_c),
                                (op2, vec_val_d, tmp1_d, tmp2_d),
                                (op2, vec_val_e, tmp1_e, tmp2_e),
                                (op2, vec_val_f, tmp1_f, tmp2_f),
                                (op2, vec_val_g, tmp1_g, tmp2_g),
                                (op2, vec_val_h, tmp1_h, tmp2_h),
                            ]
                        })

                    self.instrs.append({
                        "valu": [
                            ("&", tmp1, vec_val, one_vec),
                            ("*", vec_idx, vec_idx, two_vec),
                            ("&", tmp1_b, vec_val_b, one_vec),
                            ("*", vec_idx_b, vec_idx_b, two_vec),
                            ("&", tmp1_c, vec_val_c, one_vec),
                            ("*", vec_idx_c, vec_idx_c, two_vec),
                        ],
                        "store": [
                            ("vstore", scalar_tmp2, vec_val),
                            ("vstore", scalar_tmp4, vec_val_b),
                        ]
                    })
                    self.instrs.append({
                        "valu": [
                            ("&", tmp1_d, vec_val_d, one_vec),
                            ("*", vec_idx_d, vec_idx_d, two_vec),
                            ("&", tmp1_e, vec_val_e, one_vec),
                            ("*", vec_idx_e, vec_idx_e, two_vec),
                            ("&", tmp1_f, vec_val_f, one_vec),
                            ("*", vec_idx_f, vec_idx_f, two_vec),
                        ],
                        "store": [
                            ("vstore", scalar_tmp6, vec_val_c),
                            ("vstore", scalar_tmp8, vec_val_d),
                        ]
                    })
                    self.instrs.append({
                        "valu": [
                            ("&", tmp1_g, vec_val_g, one_vec),
                            ("*", vec_idx_g, vec_idx_g, two_vec),
                            ("&", tmp1_h, vec_val_h, one_vec),
                            ("*", vec_idx_h, vec_idx_h, two_vec),
                            ("+", tmp3, one_vec, tmp1),
                            ("+", tmp3_b, one_vec, tmp1_b),
                        ],
                        "store": [
                            ("vstore", scalar_tmp10, vec_val_e),
                            ("vstore", scalar_tmp12, vec_val_f),
                        ]
                    })
                    self.instrs.append({
                        "valu": [
                            ("+", tmp3_c, one_vec, tmp1_c),
                            ("+", tmp3_d, one_vec, tmp1_d),
                            ("+", tmp3_e, one_vec, tmp1_e),
                            ("+", tmp3_f, one_vec, tmp1_f),
                            ("+", tmp3_g, one_vec, tmp1_g),
                            ("+", tmp3_h, one_vec, tmp1_h),
                        ],
                        "store": [
                            ("vstore", scalar_tmp14, vec_val_g),
                            ("vstore", scalar_tmp16, vec_val_h),
                        ]
                    })
                    self.instrs.append({
                        "valu": [
                            ("+", vec_idx, vec_idx, tmp3),
                            ("+", vec_idx_b, vec_idx_b, tmp3_b),
                            ("+", vec_idx_c, vec_idx_c, tmp3_c),
                            ("+", vec_idx_d, vec_idx_d, tmp3_d),
                            ("+", vec_idx_e, vec_idx_e, tmp3_e),
                            ("+", vec_idx_f, vec_idx_f, tmp3_f),
                        ]
                    })
                    self.instrs.append({
                        "valu": [
                            ("+", vec_idx_g, vec_idx_g, tmp3_g),
                            ("+", vec_idx_h, vec_idx_h, tmp3_h),
                            ("<", tmp1, vec_idx, n_nodes_vec),
                            ("<", tmp1_b, vec_idx_b, n_nodes_vec),
                            ("<", tmp1_c, vec_idx_c, n_nodes_vec),
                            ("<", tmp1_d, vec_idx_d, n_nodes_vec),
                        ]
                    })
                    self.instrs.append({
                        "valu": [
                            ("<", tmp1_e, vec_idx_e, n_nodes_vec),
                            ("<", tmp1_f, vec_idx_f, n_nodes_vec),
                            ("<", tmp1_g, vec_idx_g, n_nodes_vec),
                            ("<", tmp1_h, vec_idx_h, n_nodes_vec),
                            ("*", vec_idx, vec_idx, tmp1),
                            ("*", vec_idx_b, vec_idx_b, tmp1_b),
                        ]
                    })
                    self.instrs.append({
                        "valu": [
                            ("*", vec_idx_c, vec_idx_c, tmp1_c),
                            ("*", vec_idx_d, vec_idx_d, tmp1_d),
                            ("*", vec_idx_e, vec_idx_e, tmp1_e),
                            ("*", vec_idx_f, vec_idx_f, tmp1_f),
                            ("*", vec_idx_g, vec_idx_g, tmp1_g),
                            ("*", vec_idx_h, vec_idx_h, tmp1_h),
                        ],
                        "store": [
                            ("vstore", scalar_tmp, vec_idx),
                            ("vstore", scalar_tmp3, vec_idx_b),
                        ]
                    })
                    self.instrs.append({
                        "store": [
                            ("vstore", scalar_tmp5, vec_idx_c),
                            ("vstore", scalar_tmp7, vec_idx_d),
                        ]
                    })
                    self.instrs.append({
                        "store": [
                            ("vstore", scalar_tmp9, vec_idx_e),
                            ("vstore", scalar_tmp11, vec_idx_f),
                        ]
                    })
                    self.instrs.append({
                        "store": [
                            ("vstore", scalar_tmp13, vec_idx_g),
                            ("vstore", scalar_tmp15, vec_idx_h),
                        ]
                    })
                    vi += 8
                elif vi + 3 < num_vec_iters:
                    base_i_a = vi * VLEN
                    base_i_b = (vi + 1) * VLEN
                    base_i_c = (vi + 2) * VLEN
                    base_i_d = (vi + 3) * VLEN
                    base_const_a = self.scratch_const(base_i_a)
                    base_const_b = self.scratch_const(base_i_b)
                    base_const_c = self.scratch_const(base_i_c)
                    base_const_d = self.scratch_const(base_i_d)

                    self.instrs.append({
                        "alu": [
                            ("+", scalar_tmp, self.scratch["inp_indices_p"], base_const_a),
                            ("+", scalar_tmp2, self.scratch["inp_values_p"], base_const_a),
                            ("+", scalar_tmp3, self.scratch["inp_indices_p"], base_const_b),
                            ("+", scalar_tmp4, self.scratch["inp_values_p"], base_const_b),
                            ("+", scalar_tmp5, self.scratch["inp_indices_p"], base_const_c),
                            ("+", scalar_tmp6, self.scratch["inp_values_p"], base_const_c),
                            ("+", scalar_tmp7, self.scratch["inp_indices_p"], base_const_d),
                            ("+", scalar_tmp8, self.scratch["inp_values_p"], base_const_d),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("vload", vec_idx, scalar_tmp),
                            ("vload", vec_val, scalar_tmp2),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("vload", vec_idx_b, scalar_tmp3),
                            ("vload", vec_val_b, scalar_tmp4),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("vload", vec_idx_c, scalar_tmp5),
                            ("vload", vec_val_c, scalar_tmp6),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("vload", vec_idx_d, scalar_tmp7),
                            ("vload", vec_val_d, scalar_tmp8),
                        ]
                    })

                    self.instrs.append({
                        "valu": [
                            ("+", vec_addr, forest_p_vec, vec_idx),
                            ("+", vec_addr_b, forest_p_vec, vec_idx_b),
                            ("+", vec_addr_c, forest_p_vec, vec_idx_c),
                            ("+", vec_addr_d, forest_p_vec, vec_idx_d),
                        ]
                    })

                    for lane in range(0, VLEN, 2):
                        self.instrs.append({
                            "load": [
                                ("load_offset", vec_node_val, vec_addr, lane),
                                ("load_offset", vec_node_val, vec_addr, lane + 1),
                            ]
                        })
                    for lane in range(0, VLEN, 2):
                        self.instrs.append({
                            "load": [
                                ("load_offset", vec_node_val_b, vec_addr_b, lane),
                                ("load_offset", vec_node_val_b, vec_addr_b, lane + 1),
                            ]
                        })
                    for lane in range(0, VLEN, 2):
                        self.instrs.append({
                            "load": [
                                ("load_offset", vec_node_val_c, vec_addr_c, lane),
                                ("load_offset", vec_node_val_c, vec_addr_c, lane + 1),
                            ]
                        })
                    for lane in range(0, VLEN, 2):
                        self.instrs.append({
                            "load": [
                                ("load_offset", vec_node_val_d, vec_addr_d, lane),
                                ("load_offset", vec_node_val_d, vec_addr_d, lane + 1),
                            ]
                        })

                    self.instrs.append({
                        "valu": [
                            ("^", vec_val, vec_val, vec_node_val),
                            ("^", vec_val_b, vec_val_b, vec_node_val_b),
                            ("^", vec_val_c, vec_val_c, vec_node_val_c),
                            ("^", vec_val_d, vec_val_d, vec_node_val_d),
                        ]
                    })

                    for hi, (op1, val1, op2, op3, val3) in enumerate(HASH_STAGES):
                        const1_vec, const3_vec = hash_const_vecs[hi]
                        self.instrs.append({
                            "valu": [
                                (op1, tmp1, vec_val, const1_vec),
                                (op3, tmp2, vec_val, const3_vec),
                                (op1, tmp1_b, vec_val_b, const1_vec),
                                (op3, tmp2_b, vec_val_b, const3_vec),
                                (op1, tmp1_c, vec_val_c, const1_vec),
                                (op3, tmp2_c, vec_val_c, const3_vec),
                            ]
                        })
                        self.instrs.append({
                            "valu": [
                                (op1, tmp1_d, vec_val_d, const1_vec),
                                (op3, tmp2_d, vec_val_d, const3_vec),
                                (op2, vec_val, tmp1, tmp2),
                                (op2, vec_val_b, tmp1_b, tmp2_b),
                            ]
                        })
                        self.instrs.append({
                            "valu": [
                                (op2, vec_val_c, tmp1_c, tmp2_c),
                                (op2, vec_val_d, tmp1_d, tmp2_d),
                            ]
                        })

                    self.instrs.append({
                        "valu": [
                            ("&", tmp1, vec_val, one_vec),
                            ("*", vec_idx, vec_idx, two_vec),
                            ("&", tmp1_b, vec_val_b, one_vec),
                            ("*", vec_idx_b, vec_idx_b, two_vec),
                            ("&", tmp1_c, vec_val_c, one_vec),
                            ("*", vec_idx_c, vec_idx_c, two_vec),
                        ]
                    })
                    self.instrs.append({
                        "valu": [
                            ("&", tmp1_d, vec_val_d, one_vec),
                            ("*", vec_idx_d, vec_idx_d, two_vec),
                            ("+", tmp3, one_vec, tmp1),
                            ("+", tmp3_b, one_vec, tmp1_b),
                        ]
                    })
                    self.instrs.append({
                        "valu": [
                            ("+", tmp3_c, one_vec, tmp1_c),
                            ("+", tmp3_d, one_vec, tmp1_d),
                            ("+", vec_idx, vec_idx, tmp3),
                            ("+", vec_idx_b, vec_idx_b, tmp3_b),
                        ]
                    })
                    self.instrs.append({
                        "valu": [
                            ("+", vec_idx_c, vec_idx_c, tmp3_c),
                            ("+", vec_idx_d, vec_idx_d, tmp3_d),
                        ]
                    })

                    self.instrs.append({
                        "valu": [
                            ("<", tmp1, vec_idx, n_nodes_vec),
                            ("<", tmp1_b, vec_idx_b, n_nodes_vec),
                            ("<", tmp1_c, vec_idx_c, n_nodes_vec),
                            ("<", tmp1_d, vec_idx_d, n_nodes_vec),
                            ("*", vec_idx, vec_idx, tmp1),
                            ("*", vec_idx_b, vec_idx_b, tmp1_b),
                        ]
                    })
                    self.instrs.append({
                        "valu": [
                            ("*", vec_idx_c, vec_idx_c, tmp1_c),
                            ("*", vec_idx_d, vec_idx_d, tmp1_d),
                        ]
                    })

                    self.instrs.append({
                        "store": [
                            ("vstore", scalar_tmp, vec_idx),
                            ("vstore", scalar_tmp2, vec_val),
                        ]
                    })
                    self.instrs.append({
                        "store": [
                            ("vstore", scalar_tmp3, vec_idx_b),
                            ("vstore", scalar_tmp4, vec_val_b),
                        ]
                    })
                    self.instrs.append({
                        "store": [
                            ("vstore", scalar_tmp5, vec_idx_c),
                            ("vstore", scalar_tmp6, vec_val_c),
                        ]
                    })
                    self.instrs.append({
                        "store": [
                            ("vstore", scalar_tmp7, vec_idx_d),
                            ("vstore", scalar_tmp8, vec_val_d),
                        ]
                    })
                    vi += 4
                elif vi + 1 < num_vec_iters:
                    base_i_a = vi * VLEN
                    base_i_b = (vi + 1) * VLEN
                    base_const_a = self.scratch_const(base_i_a)
                    base_const_b = self.scratch_const(base_i_b)

                    self.instrs.append({
                        "alu": [
                            ("+", scalar_tmp, self.scratch["inp_indices_p"], base_const_a),
                            ("+", scalar_tmp2, self.scratch["inp_values_p"], base_const_a),
                            ("+", scalar_tmp3, self.scratch["inp_indices_p"], base_const_b),
                            ("+", scalar_tmp4, self.scratch["inp_values_p"], base_const_b),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("vload", vec_idx, scalar_tmp),
                            ("vload", vec_val, scalar_tmp2),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("vload", vec_idx_b, scalar_tmp3),
                            ("vload", vec_val_b, scalar_tmp4),
                        ]
                    })

                    self.instrs.append({
                        "valu": [
                            ("+", vec_addr, forest_p_vec, vec_idx),
                            ("+", vec_addr_b, forest_p_vec, vec_idx_b),
                        ]
                    })

                    for lane in range(0, VLEN, 2):
                        self.instrs.append({
                            "load": [
                                ("load_offset", vec_node_val, vec_addr, lane),
                                ("load_offset", vec_node_val, vec_addr, lane + 1),
                            ]
                        })
                    for lane in range(0, VLEN, 2):
                        self.instrs.append({
                            "load": [
                                ("load_offset", vec_node_val_b, vec_addr_b, lane),
                                ("load_offset", vec_node_val_b, vec_addr_b, lane + 1),
                            ]
                        })

                    self.instrs.append({
                        "valu": [
                            ("^", vec_val, vec_val, vec_node_val),
                            ("^", vec_val_b, vec_val_b, vec_node_val_b),
                        ]
                    })

                    for hi, (op1, val1, op2, op3, val3) in enumerate(HASH_STAGES):
                        const1_vec, const3_vec = hash_const_vecs[hi]
                        self.instrs.append({
                            "valu": [
                                (op1, tmp1, vec_val, const1_vec),
                                (op3, tmp2, vec_val, const3_vec),
                                (op1, tmp1_b, vec_val_b, const1_vec),
                                (op3, tmp2_b, vec_val_b, const3_vec),
                            ]
                        })
                        self.instrs.append({
                            "valu": [
                                (op2, vec_val, tmp1, tmp2),
                                (op2, vec_val_b, tmp1_b, tmp2_b),
                            ]
                        })

                    self.instrs.append({
                        "valu": [
                            ("&", tmp1, vec_val, one_vec),
                            ("*", vec_idx, vec_idx, two_vec),
                            ("&", tmp1_b, vec_val_b, one_vec),
                            ("*", vec_idx_b, vec_idx_b, two_vec),
                        ]
                    })
                    self.instrs.append({
                        "valu": [
                            ("+", tmp3, one_vec, tmp1),
                            ("+", tmp3_b, one_vec, tmp1_b),
                        ]
                    })
                    self.instrs.append({
                        "valu": [
                            ("+", vec_idx, vec_idx, tmp3),
                            ("+", vec_idx_b, vec_idx_b, tmp3_b),
                        ]
                    })

                    self.instrs.append({
                        "valu": [
                            ("<", tmp1, vec_idx, n_nodes_vec),
                            ("<", tmp1_b, vec_idx_b, n_nodes_vec),
                            ("*", vec_idx, vec_idx, tmp1),
                            ("*", vec_idx_b, vec_idx_b, tmp1_b),
                        ]
                    })

                    self.instrs.append({
                        "store": [
                            ("vstore", scalar_tmp, vec_idx),
                            ("vstore", scalar_tmp2, vec_val),
                        ]
                    })
                    self.instrs.append({
                        "store": [
                            ("vstore", scalar_tmp3, vec_idx_b),
                            ("vstore", scalar_tmp4, vec_val_b),
                        ]
                    })
                    vi += 2
                else:
                    base_i = vi * VLEN
                    base_const = self.scratch_const(base_i)

                    self.instrs.append({
                        "alu": [
                            ("+", scalar_tmp, self.scratch["inp_indices_p"], base_const),
                            ("+", scalar_tmp2, self.scratch["inp_values_p"], base_const),
                        ]
                    })
                    self.instrs.append({
                        "load": [
                            ("vload", vec_idx, scalar_tmp),
                            ("vload", vec_val, scalar_tmp2),
                        ]
                    })

                    self.instrs.append({
                        "valu": [("+", vec_addr, forest_p_vec, vec_idx)]
                    })

                    for lane in range(0, VLEN, 2):
                        self.instrs.append({
                            "load": [
                                ("load_offset", vec_node_val, vec_addr, lane),
                                ("load_offset", vec_node_val, vec_addr, lane + 1),
                            ]
                        })

                    self.instrs.append({"valu": [("^", vec_val, vec_val, vec_node_val)]})

                    for hi, (op1, val1, op2, op3, val3) in enumerate(HASH_STAGES):
                        const1_vec, const3_vec = hash_const_vecs[hi]
                        self.instrs.append({
                            "valu": [
                                (op1, tmp1, vec_val, const1_vec),
                                (op3, tmp2, vec_val, const3_vec),
                            ]
                        })
                        self.instrs.append({
                            "valu": [(op2, vec_val, tmp1, tmp2)]
                        })

                    self.instrs.append({
                        "valu": [
                            ("&", tmp1, vec_val, one_vec),
                            ("*", vec_idx, vec_idx, two_vec),
                        ]
                    })
                    self.instrs.append({"valu": [("+", tmp3, one_vec, tmp1)]})
                    self.instrs.append({"valu": [("+", vec_idx, vec_idx, tmp3)]})

                    self.instrs.append({
                        "valu": [
                            ("<", tmp1, vec_idx, n_nodes_vec),
                            ("*", vec_idx, vec_idx, tmp1),
                        ]
                    })

                    self.instrs.append({"store": [("vstore", scalar_tmp, vec_idx)]})
                    self.instrs.append({"store": [("vstore", scalar_tmp2, vec_val)]})
                    vi += 1

        self.instrs.append({"flow": [("pause",)]})

BASELINE = 147734

def do_kernel_test(
    forest_height: int,
    rounds: int,
    batch_size: int,
    seed: int = 123,
    trace: bool = False,
    prints: bool = False,
):
    print(f"{forest_height=}, {rounds=}, {batch_size=}")
    random.seed(seed)
    forest = Tree.generate(forest_height)
    inp = Input.generate(forest, batch_size, rounds)
    mem = build_mem_image(forest, inp)

    kb = KernelBuilder()
    kb.build_kernel(forest.height, len(forest.values), len(inp.indices), rounds)
    # print(kb.instrs)

    value_trace = {}
    machine = Machine(
        mem,
        kb.instrs,
        kb.debug_info(),
        n_cores=N_CORES,
        value_trace=value_trace,
        trace=trace,
    )
    machine.prints = prints
    for i, ref_mem in enumerate(reference_kernel2(mem, value_trace)):
        machine.run()
        inp_values_p = ref_mem[6]
        if prints:
            print(machine.mem[inp_values_p : inp_values_p + len(inp.values)])
            print(ref_mem[inp_values_p : inp_values_p + len(inp.values)])
        assert (
            machine.mem[inp_values_p : inp_values_p + len(inp.values)]
            == ref_mem[inp_values_p : inp_values_p + len(inp.values)]
        ), f"Incorrect result on round {i}"
        inp_indices_p = ref_mem[5]
        if prints:
            print(machine.mem[inp_indices_p : inp_indices_p + len(inp.indices)])
            print(ref_mem[inp_indices_p : inp_indices_p + len(inp.indices)])
        # Updating these in memory isn't required, but you can enable this check for debugging
        # assert machine.mem[inp_indices_p:inp_indices_p+len(inp.indices)] == ref_mem[inp_indices_p:inp_indices_p+len(inp.indices)]

    print("CYCLES: ", machine.cycle)
    print("Speedup over baseline: ", BASELINE / machine.cycle)
    return machine.cycle


class Tests(unittest.TestCase):
    def test_ref_kernels(self):
        """
        Test the reference kernels against each other
        """
        random.seed(123)
        for i in range(10):
            f = Tree.generate(4)
            inp = Input.generate(f, 10, 6)
            mem = build_mem_image(f, inp)
            reference_kernel(f, inp)
            for _ in reference_kernel2(mem, {}):
                pass
            assert inp.indices == mem[mem[5] : mem[5] + len(inp.indices)]
            assert inp.values == mem[mem[6] : mem[6] + len(inp.values)]

    def test_kernel_trace(self):
        # Full-scale example for performance testing
        do_kernel_test(10, 16, 256, trace=True, prints=False)

    # Passing this test is not required for submission, see submission_tests.py for the actual correctness test
    # You can uncomment this if you think it might help you debug
    # def test_kernel_correctness(self):
    #     for batch in range(1, 3):
    #         for forest_height in range(3):
    #             do_kernel_test(
    #                 forest_height + 2, forest_height + 4, batch * 16 * VLEN * N_CORES
    #             )

    def test_kernel_cycles(self):
        do_kernel_test(10, 16, 256)


# To run all the tests:
#    python perf_takehome.py
# To run a specific test:
#    python perf_takehome.py Tests.test_kernel_cycles
# To view a hot-reloading trace of all the instructions:  **Recommended debug loop**
# NOTE: The trace hot-reloading only works in Chrome. In the worst case if things aren't working, drag trace.json onto https://ui.perfetto.dev/
#    python perf_takehome.py Tests.test_kernel_trace
# Then run `python watch_trace.py` in another tab, it'll open a browser tab, then click "Open Perfetto"
# You can then keep that open and re-run the test to see a new trace.

# To run the proper checks to see which thresholds you pass:
#    python tests/submission_tests.py

if __name__ == "__main__":
    unittest.main()
