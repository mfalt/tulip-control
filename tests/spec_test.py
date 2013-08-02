#!/usr/bin/env python
"""
SCL; 2 August 2013.
"""

import copy
import numpy as np
from tulip.spec import GRSpec
import tulip.gridworld as gw


def specs_equal(s1, s2):
    """Return True if s1 and s2 are *roughly* syntactically equal.

    This function seems to be of little or no use outside this test
    module because of its fragility.
    """
    if s1 is None or s2 is None:
        raise TypeError
    for s in [s1, s2]:
        s.env_vars.sort()
        s.sys_vars.sort()
        if hasattr(s.env_init, "sort"):
            s.env_init.sort()
        if hasattr(s.env_safety, "sort"):
            s.env_safety.sort()
        if hasattr(s.env_prog, "sort"):
            s.env_prog.sort()
        if hasattr(s.sys_init, "sort"):
            s.sys_init.sort()
        if hasattr(s.sys_safety, "sort"):
            s.sys_safety.sort()
        if hasattr(s.sys_prog, "sort"):
            s.sys_prog.sort()
    if s1.env_vars != s2.env_vars or s1.sys_vars != s2.sys_vars:
        return False
    if s1.env_init != s2.env_init or s1.env_safety != s2.env_safety or s1.env_prog != s2.env_prog:
        return False
    if s1.sys_init != s2.sys_init or s1.sys_safety != s2.sys_safety or s1.sys_prog != s2.sys_prog:
        return False
    return True


def import_GridWorld_test():
    # Sanity-check
    X = gw.random_world((5, 10), prefix="sys")
    s = GRSpec()
    s.import_GridWorld(X)
    assert specs_equal(X.spec(), s)


class GRSpec_test:
    def setUp(self):
        self.f = GRSpec(env_vars=["x"], sys_vars=["y"],
                        env_prog=["!x", "x"], sys_prog=["y&!x"])

    def tearDown(self):
        self.f = None

    def test_sym_to_prop(self):
        original_env_vars = copy.copy(self.f.env_vars)
        original_sys_vars = copy.copy(self.f.sys_vars)
        self.f.sym_to_prop({"x":"bar", "y":"uber|cat"})
        assert self.f.env_vars == original_env_vars and self.f.sys_vars == original_sys_vars
        assert self.f.env_prog == ["!(bar)", "(bar)"] and self.f.sys_prog == ["(uber|cat)&!(bar)"]
