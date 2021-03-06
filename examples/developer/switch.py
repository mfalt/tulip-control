"""
Simple example with uncontrolled switching, for debugging

 6 cell robot example.
     +---+---+---+
     | 3 | 4 | 5 |
     +---+---+---+
     | 0 | 1 | 2 |
     +---+---+---+
"""
from tulip import spec, synth, transys
import numpy as np
from scipy import sparse as sp

sys_swe = transys.OpenFTS()
sys_swe.sys_actions.add('')
sys_swe.env_actions.add_from({'sun','rain'})

# Environment actions are mutually exclusive.
n = 2
states = ['s'+str(i) for i in xrange(n) ]
sys_swe.states.add_from(states)
sys_swe.states.initial |= ['s0']

# different transitions possible, depending on weather
transmat1 = sp.lil_matrix(np.array(
                [[0,1],
                 [1,0]]
            ))
sys_swe.transitions.add_labeled_adj(transmat1, states, ('','sun') )

# avoid being killed by environment
transmat2 = sp.lil_matrix(np.array(
                [[1,0],
                 [0,1]]
            ))
sys_swe.transitions.add_labeled_adj(transmat2, states, ('','rain') )

# atomic props
sys_swe.atomic_propositions.add_from(['home','lot'])
sys_swe.states.labels(states, [{'home'}, {'lot'}] )
print(sys_swe)

# (park & sun) & []<>!park && []<>sum
env_vars = {'park'}
env_init = {'park', 'sun'}
env_prog = {'!park','sun'}
env_safe = set()

# (s0 & X0reach) & []<> home & [](park -> <>lot)
sys_vars = {'X0reach'}
sys_init = {'X0reach', 's0'}          
sys_prog = {'home'}               # []<>home
sys_safe = {'next(X0reach) <-> lot || (X0reach && !park)'}
sys_prog |= {'X0reach'}

# Create the specification
specs = spec.GRSpec(env_vars, sys_vars, env_init, sys_init,
                    env_safe, sys_safe, env_prog, sys_prog)
                    
# Controller synthesis
ctrl = synth.synthesize('gr1c', specs, sys=sys_swe,
                        ignore_sys_init=True, bool_actions=True)

if not ctrl.save('switch.pdf'):
    print(ctrl)
