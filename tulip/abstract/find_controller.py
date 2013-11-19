# Copyright (c) 2011, 2012, 2013 by California Institute of Technology
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 
# 3. Neither the name of the California Institute of Technology nor
#    the names of its contributors may be used to endorse or promote
#    products derived from this software without specific prior
#    written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL CALTECH
# OR THE CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF
# USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
# OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.
#
""" 
Algorithms related to controller synthesis for discretized dynamics.
    
Primary functions:
    - get_input
    
Helper functions:
    - get_input_helper
    - is_seq_inside
    - get_cell_id

see also
--------
discretize
"""
import numpy as np
from cvxopt import matrix,solvers

from tulip import polytope as pc
from discretize import solve_feasible, createLM, _block_diag2

def get_input(
    x0, ssys, part, start, end, N, R=[], r=[], Q=[],
    mid_weight=0., conservative=True,
    closed_loop=True, test_result=False
):
    """Calculate an input signal sequence taking the plant from state `start` 
    to state `end` in the partition part, such that 
    f(x,u) = x'Rx + r'x + u'Qu + mid_weight*|xc-x(0)|_2 is minimal. xc is
    the chebyshev center of the final cell.
    If no cost parameters are given, Q = I and mid_weight=3 are used. 
        
    Input:

    - `x0`: initial continuous state
    - `ssys`: LtiSysDyn object specifying system dynamics
    - `part`: PropPreservingPartition object specifying the state
              space partition.
    - `start`: int specifying the number of the initial state in `part`
    - `end`: int specifying the number of the end state in `part`
    - `N`: the horizon length
    - `R`: state cost matrix for x = [x(1)' x(2)' .. x(N)']', 
           size (N*xdim x N*xdim). If empty, zero matrix is used.
    - `r`: cost vector for x = [x(1)' x(2)' .. x(N)']', size (N*xdim x 1)
    - `Q`: input cost matrix for u = [u(0)' u(1)' .. u(N-1)']', 
           size (N*udim x N*udim). If empty, identity matrix is used.
    - `mid_weight`: cost weight for |x(N)-xc|_2
    - `conservative`: if True, force plant to stay inside initial
                      state during execution. if False, plant is
                      forced to stay inside the original proposition
                      preserving cell.
    - `closed_loop`: should be True if closed loop discretization has
                     been used.
    - `test_result`: performs a simulation (without disturbance) to
                     make sure that the calculated input sequence is
                     safe.
    
    Output:
    - A (N x m) numpy array where row k contains u(k) for k = 0,1 ... N-1.
    
    Note1: The same horizon length as in reachability analysis should
    be used in order to guarantee feasibility.
    
    Note2: If the closed loop algorithm has been used to compute
    reachability the input needs to be recalculated for each time step
    (with decreasing horizon length). In this case only u(0) should be
    used as a control signal and u(1) ... u(N-1) thrown away.
    
    Note3: The "conservative" calculation makes sure that the plants
    remains inside the convex hull of the starting region during
    execution, i.e.  x(1), x(2) ...  x(N-1) are in conv_hull(starting
    region).  If the original proposition preserving partition is not
    convex, safety can not be guaranteed.
    """
    if (len(R) == 0) and (len(Q) == 0) and \
    (len(r) == 0) and (mid_weight == 0):
        # Default behavior
        Q = np.eye(N*ssys.B.shape[1])
        R = np.zeros([N*x0.size, N*x0.size])
        r = np.zeros([N*x0.size,1])
        mid_weight = 3
    if len(R) == 0:
        R = np.zeros([N*x0.size, N*x0.size])
    if len(Q) == 0:
        Q = np.zeros([N*ssys.B.shape[1], N*ssys.B.shape[1]])    
    if len(r) == 0:
        r = np.zeros([N*x0.size,1])
    
    if (R.shape[0] != R.shape[1]) or (R.shape[0] != N*x0.size):
        raise Exception("get_input: "
            "R must be square and have side N * dim(state space)")
    
    if (Q.shape[0] != Q.shape[1]) or (Q.shape[0] != N*ssys.B.shape[1]):
        raise Exception("get_input: "
            "Q must be square and have side N * dim(input space)")
    if part.trans != None:
        if part.trans[end,start] != 1:
            raise Exception("get_input: "
                "no transition from state " + str(start) +
                " to state " + str(end)
            )
    else:
        print("get_input: "
            "Warning, no transition matrix found, assuming feasible")
    
    if (not conservative) & (part.orig == None):
        print("List of original proposition preserving "
            "partitions not given, reverting to conservative mode")
        conservative = True
       
    P_start = part.list_region[start]
    P_end = part.list_region[end]
    
    n = ssys.A.shape[1]
    m = ssys.B.shape[1]
    
    if conservative:
        # Take convex hull or P_start as constraint
        if len(P_start) > 0:
            if len(P_start.list_poly) > 1:
                # Take convex hull
                vert = pc.extreme(P_start.list_poly[0])
                for i in range(1, len(P_start.list_poly)):
                    vert = np.hstack([
                        vert,
                        pc.extreme(P_start.list_poly[i])
                    ])
                P1 = pc.qhull(vert)
            else:
                P1 = P_start.list_poly[0]
        else:
            P1 = P_start
    else:
        # Take original proposition preserving cell as constraint
        P1 = part.orig_list_region[part.orig[start]]
    
    if len(P_end) > 0:
        low_cost = np.inf
        low_u = np.zeros([N,m])
        for i in range(len(P_end.list_poly)):
            P3 = P_end.list_poly[i]
            if mid_weight > 0:
                rc, xc = pc.cheby_ball(P3)
                R[
                    np.ix_(
                        range(n*(N-1), n*N),
                        range(n*(N-1), n*N)
                    )
                ] += mid_weight*np.eye(n)
                
                r[range((N-1)*n, N*n), :] += -mid_weight*xc
            try:
                u, cost = get_input_helper(
                    x0, ssys, P1, P3, N, R, r, Q,
                    closed_loop=closed_loop
                )
                r[range((N-1)*n, N*n), :] += mid_weight*xc
            except:
                r[range((N-1)*n, N*n), :] += mid_weight*xc
                continue
            if cost < low_cost:
                low_u = u
                low_cost = cost
        if low_cost == np.inf:
            raise Exception("get_input: Did not find any trajectory")
    else:
        P3 = P_end
        if mid_weight > 0:
            rc, xc = pc.cheby_ball(P3)
            R[
                np.ix_(
                    range(n*(N-1), n*N),
                    range(n*(N-1), n*N)
                )
            ] += mid_weight*np.eye(n)
            r[range((N-1)*n, N*n), :] += -mid_weight*xc
        low_u, cost = get_input_helper(
            x0, ssys, P1, P3, N, R, r, Q,
            closed_loop=closed_loop
        )
        
    if test_result:
        good = is_seq_inside(x0, low_u, ssys, P1, P3)
        if not good:
            print("Calculated sequence not good")
    return low_u

def get_input_helper(
    x0, ssys, P1, P3, N, R, r, Q,
    closed_loop=True
):
    """Calculates the sequence u_seq such that
    - x(t+1) = A x(t) + B u(t) + K
    - x(k) \in P1 for k = 0,...N
    - x(N) \in P3
    - [u(k); x(k)] \in PU
    
    and minimizes x'Rx + 2*r'x + u'Qu
    """
    n = ssys.A.shape[1]
    m = ssys.B.shape[1]
    
    list_P = []
    if closed_loop:
        temp_part = P3
        list_P.append(P3)
        for i in xrange(N-1,0,-1): 
            temp_part = solve_feasible(
                P1, temp_part, ssys, N=1,
                closed_loop=False, trans_set=P1
            )
            list_P.insert(0, temp_part)
        list_P.insert(0,P1)
        L,M = createLM(ssys, N, list_P, disturbance_ind=[1])
    else:
        list_P.append(P1)
        for i in xrange(N-1,0,-1):
            list_P.append(P1)
        list_P.append(P3)
        L,M = createLM(ssys, N, list_P)
    
    # Remove first constraint on x(0)
    L = L[range(list_P[0].A.shape[0], L.shape[0]),:]
    M = M[range(list_P[0].A.shape[0], M.shape[0]),:]
    
    # Separate L matrix
    Lx = L[:,range(n)]
    Lu = L[:,range(n,L.shape[1])] 
    
    M = M - np.dot(Lx, x0).reshape(Lx.shape[0],1)
        
    # Constraints
    G = matrix(Lu)
    h = matrix(M)

    B_diag = ssys.B
    for i in xrange(N-1):
        B_diag = _block_diag2(B_diag,ssys.B)
    K_hat = np.tile(ssys.K, (N,1))

    A_it = ssys.A.copy()
    A_row = np.zeros([n, n*N])
    A_K = np.zeros([n*N, n*N])
    A_N = np.zeros([n*N, n])

    for i in xrange(N):
        A_row = np.dot(ssys.A, A_row)
        A_row[np.ix_(
            range(n),
            range(i*n, (i+1)*n)
        )] = np.eye(n)

        A_N[np.ix_(
            range(i*n, (i+1)*n),
            range(n)
        )] = A_it
        
        A_K[np.ix_(
            range(i*n,(i+1)*n),
            range(A_K.shape[1])
        )] = A_row
        
        A_it = np.dot(ssys.A, A_it)
        
    Ct = np.dot(A_K, B_diag)
    P = matrix(Q + np.dot(Ct.T, np.dot(R, Ct)))
    q = matrix(
        np.dot(
            np.dot(x0.reshape(1,x0.size), A_N.T) +
            np.dot(A_K, K_hat).T , np.dot(R, Ct)
        ) +
        np.dot(r.T, Ct )
    ).T 
    
    sol = solvers.qp(P,q,G,h)
    
    if sol['status'] != "optimal":
        raise Exception("getInputHelper: "
            "QP solver finished with status " +
            str(sol['status'])
        )
    u = np.array(sol['x']).flatten()
    cost = sol['primal objective']
    
    return u.reshape(N, m), cost

def is_seq_inside(x0, u_seq, ssys, P0, P1):
    """Checks if the plant remains inside P0 for time t = 1, ... N-1
    and  that the plant reaches P1 for time t = N.
    Used to test a computed input sequence.
    No disturbance is taken into account.
    
    @param x0: initial point for execution
    @param u_seq: (N x m) array where row k is input for t = k
    
    @param ssys: dynamics
    @type ssys: LtiSysDyn
    
    @param P0: Polytope where we want x(k) to remain for k = 1, ... N-1
    
    @return: C{True} if x(k) \in P0 for k = 1, .. N-1 and x(N) \in P1.
        C{False} otherwise  
    """
    N = u_seq.shape[0]
    x = x0.reshape(x0.size,1)
    
    A = ssys.A
    B = ssys.B
    if len(ssys.K) == 0:
        K = np.zeros(x.shape)
    else:
        K = ssys.K
    
    inside = True
    for i in xrange(N-1):
        u = u_seq[i,:].reshape(u_seq[i,:].size,1)
        x = np.dot(A,x) + np.dot(B,u) + K       
        if not pc.is_inside(P0, x):
            inside = False
    un_1 = u_seq[N-1,:].reshape(u_seq[N-1,:].size,1)
    xn = np.dot(A,x) + np.dot(B,un_1) + K
    if not pc.is_inside(P1, xn):
        inside = False
            
    return inside
    
def get_cell_id(x0, part):
    """Return an integer specifying in which discrete state
    the continuous state x0 belongs to.
        
    Input:
    - `x0`: initial continuous state
    - `part`: PropPreservingPartition object specifying
        the state space partition
    
    Output:
    - cellID: int specifying the discrete state in
        `part` x0 belongs to, -1 if x0 does 
        not belong to any discrete state.
    
    Note1: If there are overlapping partitions
    (i.e., x0 can belong to more than one discrete state),
    this just returns the first ID
    """
    cellID = -1
    for i in xrange(part.num_regions):
        if pc.is_inside(part.list_region[i], x0):
             cellID = i
             break
    return cellID