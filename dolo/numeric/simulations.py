from dolo.numeric.global_solution import step_residual

import numpy

def simulate(model, dr, s0=None, sigma=None, n_exp=0, horizon=40, parms=None, seed=1, discard=False, stack_series=True, solve_expectations=False, nodes=None, weights=None, use_pandas=True, forcing_shocks=None):
    '''
    :param model: compiled model
    :param dr: decision rule
    :param s0: initial state where all simulations start
    :param sigma: covariance matrix of the normal multivariate distribution describing the random shocks
    :param n_exp: number of draws to simulate. Use 0 for impulse-response functions
    :param horizon: horizon for the simulation
    :param parms: (vector) value for the parameters of the model
    :param seed: used to initialize the random number generator. Use it to replicate exact same results among simulations
    :param discard: (default: False) if True, then all simulations containing at least one non finite value are discarded
    :param stack_series: return simulated series for different types of variables separately (in a list)
    :return: a ``n_s x n_exp x horizon`` array where ``n_s`` is the number of states. The second dimension is omitted if
    n_exp = 0.
    '''


    if n_exp ==0:
        irf = True
        n_exp = 1
    else:
        irf = False



    calib = model.calibration

    if parms is None:
        parms = numpy.array( calib['parameters'] ) # TODO : remove reference to symbolic model

    if sigma is None:
        sigma = numpy.array( calib['covariances'] )

    if s0 is None:
        s0 = numpy.array( calib['states'] )

    # s0 = numpy.atleast_2d(s0.flatten()).T

    x0 = dr(s0)

    s_simul = numpy.zeros( (horizon, n_exp, s0.shape[0]) )
    x_simul = numpy.zeros( (horizon, n_exp, x0.shape[0]) )

    s_simul[0,:,:] = s0[None,:]
    x_simul[0,:,:] = x0[None,:]

    fun = model.functions

    if model.model_type == 'fga':
        ff = fun['arbitrage']
        gg = fun['transition']
        aa = fun['auxiliary']
        g = lambda s,x,e,p : gg(s,x,aa(s,x,p),e,p)
        f = lambda s,x,e,S,X,p : ff(s,x,aa(s,x,p),S,X,aa(S,X,p),p)
    else:
        f = model.functions['arbitrage']
        g = model.functions['transition']


    numpy.random.seed(seed)

    for t in range(horizon):
        mean = numpy.zeros(sigma.shape[0])
        if irf:

            if forcing_shocks is not None and t<forcing_shocks.shape[1]:
                epsilons = forcing_shocks[:,t]
            else:
                epsilons = numpy.zeros( (1,sigma.shape[0]) )
        else:
            epsilons = numpy.random.multivariate_normal(mean, sigma, n_exp)
            print(epsilons)

        s = s_simul[t,:,:]

        x = dr(s)

        if solve_expectations:
            # TODO: add complementarities
            from dolo.numeric.optimize.newton import newton, SerialDifferentiableFunction

            fobj = lambda t: step_residual(s, t, dr, f, g, parms, nodes, weights, with_derivatives=False) #
            diff_F = SerialDifferentiableFunction(fobj)
#  x = solver(fobj, x,  serial_problem=True)
            [x,nit] = newton(diff_F, x) #, numdiff=True)

        x_simul[t,:,:] = x

        ss = g(s,x,epsilons,parms)

        if t<(horizon-1):
            s_simul[t+1,:,:] = ss

    from numpy import isnan,all

    if not 'auxiliary' in fun: # TODO: find a better test than this
        l = [s_simul, x_simul]
        varnames = model.symbols['states'] + model.symbols['controls']
    else:
        aux = fun['auxiliary']
        n_s = s_simul.shape[1]
        n_x = x_simul.shape[1]
        N = n_exp*horizon
        a_simul = aux( s_simul.reshape((N, -1)), x_simul.reshape((N,-1)), parms)
        n_a = a_simul.shape[1]
        a_simul = a_simul.reshape(horizon,n_exp,n_a)
        l = [s_simul, x_simul, a_simul]
        varnames = model.symbols['states'] + model.symbols['controls'] + model.symbols['auxiliaries']
    if not stack_series:
        return l

    else:
        simul = numpy.concatenate(l,axis=2)

    if discard:
        iA = -isnan(x_simul)
        valid = all( all( iA, axis=0 ), axis=1 )
        simul = simul[:,valid,:]
        n_kept = s_simul.shape[1]
        if n_exp > n_kept:
            print( 'Discarded {}/{}'.format(n_exp-n_kept,n_exp))

    if irf:
        simul = simul[:,0,:]

        if use_pandas:
            import pandas
            print(simul.shape)
            ts = pandas.DataFrame(simul, columns=varnames)
            return ts

    return simul


def plot_decision_rule(model, dr, state, plot_controls=None, bounds=None, n_steps=10, s0=None, **kwargs):

    import numpy

    states_names = model.symbols['states']
    controls_names = model.symbols['controls']
    index = states_names.index(str(state))
    if bounds is None:
        bounds = [dr.smin[index], dr.smax[index]]
    values = numpy.linspace(bounds[0], bounds[1], n_steps)
    if s0 is None:
        s0 = model.calibration['states']
    svec = numpy.row_stack([s0]*n_steps)
    svec[:,index] = values
    xvec = dr(svec)

    if plot_controls is None:
        return [svec, xvec]
    else:
        from matplotlib import pyplot
        if isinstance(plot_controls, str):
            i = controls_names.index(plot_controls)
            pyplot.plot(values, xvec[:,i], **kwargs)
        else:
            for cn in  plot_controls:
                i = controls_names.index(cn)
                pyplot.plot(values, xvec[:,i], label=cn)
            pyplot.legend()
        pyplot.xlabel(state)



if __name__ == '__main__':

    from dolo import yaml_import, approximate_controls
    model = yaml_import('../../examples/global_models/capital.yaml')

    dr = approximate_controls(model)

    sigma = model.covariances

    # from dolo.compiler.compiler_global import Cmodel

    import numpy
    from matplotlib.pyplot import hist, show, figure, plot


    s0 = model.calibration['states']
    parms = model.calibration['parameters']
    
    horizon = 50

    simul = simulate(model, dr, s0, sigma, n_exp=150, parms=parms, seed=1, horizon=horizon)



    from dolo.numeric.discretization import hermgauss
    N = 80
    [x,w] = hermgauss(N)*sigma
    simul_2 = simulate(model, dr, s0, sigma, n_exp=150, parms=parms, horizon=horizon, seed=1, solve_expectations=True, nodes=x, weights=w)



    timevec = numpy.array(range(simul.shape[2]))


    figure()
    plot(simul[:,0,0]) # - simul_2[0,0,:])
    show()

#
#    figure()
#    plot(simul[0,0,:])
#    plot(simul_2[0,0,:])
#    show()

    figure()
    for t in range( horizon ):
        hist( simul[t,:,0], bins=50 )

    show()
    #plot(timevec,s_simul[0,0,:])
