import PsiMod
import input
from proc import *
from text import *

#Procedure lookup tables
procedures = {
        'energy' : {
            'scf'           : run_scf,
            'mcscf'         : run_mcscf,
            'dcft'          : run_dcft,
            'dfmp2'         : run_dfmp2,
            'dfcc'          : run_dfcc,
            'mp2'           : run_mp2,
            'mp2-drpa'      : run_mp2drpa,
            'sapt0'         : run_sapt,
            'sapt2'         : run_sapt,
            'sapt2+'        : run_sapt,
            'sapt2+3'       : run_sapt,
            'sapt0-ct'      : run_sapt_ct,
            'sapt2-ct'      : run_sapt_ct,
            'sapt2+-ct'     : run_sapt_ct,
            'sapt2+3-ct'    : run_sapt_ct,
            'mp2c'          : run_mp2c,
            'ccsd'          : run_ccsd,
            'ccsd(t)'       : run_ccsd_t,
            'eom-ccsd'      : run_eom_ccsd,
            'detci'         : run_detci,
            'mp'            : run_detci,  # arbitrary order mp(n)
            'zapt'          : run_detci,  # arbitrary order zapt(n)
            'cisd'          : run_detci,
            'cisdt'         : run_detci,
            'cisdtq'        : run_detci,
            'ci'            : run_detci,  # arbitrary order ci(n)
            'fci'           : run_detci
        },
        'gradient' : {
            'scf'           : run_scf_gradient,
            'ccsd'          : run_ccsd_gradient,
            'mp2'           : run_mp2_gradient
        },
        'hessian' : {
        },
        'response' : {
            'ccsd' : run_ccsd_response
        }}

def energy(name, **kwargs):
    lowername = name.lower()

    # Make sure the molecule the user provided is the active one
    if (kwargs.has_key('molecule')):
        activate(kwargs['molecule'])
        del kwargs['molecule']
    molecule = PsiMod.get_active_molecule()
    molecule.update_geometry()
    # Line below needed when passing in molecule as a keyword argument
    #    but causes mints2 test case to fail
    PsiMod.set_global_option("BASIS", PsiMod.get_global_option("BASIS"))

    # Allow specification of methods to arbitrary order
    lowername, level = parse_arbitrary_order(lowername)
    if level:
        kwargs['level'] = level

    try:
        return procedures['energy'][lowername](lowername,**kwargs)
    except KeyError:
        raise ValidationError('Energy method %s not available.' % (lowername))

def gradient(name, **kwargs):
    lowername = name.lower()
    dertype = 1

    # Order of precedence:
    #    1. Default for wavefunction
    #    2. Value obtained from kwargs, if user changed it
    #    3. If user provides a custom 'func' use that

    # Allow specification of methods to arbitrary order
    lowername, level = parse_arbitrary_order(lowername)
    if level:
        kwargs['level'] = level

    # 1. set the default to that of the provided name
    if (procedures['gradient'].has_key(lowername)):
        dertype = 1
    elif (procedures['energy'].has_key(lowername)):
        dertype = 0
        func = energy

    # 2. Check if the user passes dertype into this function
    if (kwargs.has_key('dertype')):
        opt_dertype = kwargs['dertype']

        if input.der0th.match(str(opt_dertype)):
            dertype = 0
            func = energy
        elif input.der1st.match(str(opt_dertype)):
            dertype = 1
        else:
            raise ValidationError('Requested derivative level \'dertype\' %s not valid for helper function optimize.' % (opt_dertype))

    # 3. if the user provides a custom function THAT takes precendence
    if (kwargs.has_key('opt_func')) or (kwargs.has_key('func')):
        if (kwargs.has_key('func')):
            kwargs['opt_func'] = kwargs['func']
            del kwargs['func']
        dertype = 0
        func = kwargs['opt_func']

    # Summary validation
    if (dertype == 1) and (procedures['gradient'].has_key(lowername)):
        pass
    elif (dertype == 0) and (func is energy) and (procedures['energy'].has_key(lowername)):
        pass
    elif (dertype == 0) and not(func is energy):
        pass
    else:
        raise ValidationError('Requested method \'name\' %s and derivative level \'dertype\' %s are not available.' 
            % (lowername, dertype))

    # Make sure the molecule the user provided is the active one
    if (kwargs.has_key('molecule')):
        activate(kwargs['molecule'])
        del kwargs['molecule']
    molecule = PsiMod.get_active_molecule()
    molecule.update_geometry()
    PsiMod.set_global_option("BASIS", PsiMod.get_global_option("BASIS"))

    # Does dertype indicate an analytic procedure both exists and is wanted?
    if (dertype == 1):
        # Nothing to it but to do it. Gradient information is saved
        # into the current reference wavefunction
        procedures['gradient'][lowername](lowername, **kwargs)

        return PsiMod.reference_wavefunction().energy()
    else:
        # If not, perform finite difference of energies
        info = "Performing finite difference calculations"
        print info

        # Obtain list of displacements
        displacements = PsiMod.fd_geoms_1_0()

        ndisp = len(displacements)

        # This version is pretty dependent on the reference geometry being last (as it is now)
        print " %d displacements needed." % ndisp
        energies = []
        for n, displacement in enumerate(displacements):
            # Print information to output.dat
            PsiMod.print_out("\n")
            banner("Loading displacement %d of %d" % (n+1, ndisp))

            # Print information to the screen
            print "    displacement %d" % (n+1)

            # Load in displacement into the active molecule
            PsiMod.get_active_molecule().set_geometry(displacement)

            # Wrap any positional arguments into kwargs (for intercalls among wrappers)
            if not('name' in kwargs) and name:
                kwargs['name'] = lowername

            # Perform the energy calculation
            #E = func(lowername, **kwargs)
            E = func(**kwargs)

            # Save the energy
            energies.append(E)

        # Obtain the gradient. This function stores the gradient into the reference wavefunction.
        PsiMod.fd_1_0(energies)

        # The last item in the list is the reference energy, return it
        return energies[-1]

def response(name, **kwargs):
    lowername = name.lower()

    # Make sure the molecule the user provided is the active one
    if (kwargs.has_key('molecule')):
        activate(kwargs['molecule'])
        del kwargs['molecule']
    molecule = PsiMod.get_active_molecule()
    molecule.update_geometry()
    PsiMod.set_global_option("BASIS", PsiMod.get_global_option("BASIS"))

    try:
        return procedures['response'][lowername](lowername, **kwargs)
    except KeyError:
        raise ValidationError('Response method %s not available.' %(lowername))

def optimize(name, **kwargs):
    for n in range(PsiMod.get_option("GEOM_MAXITER")):
        # Compute the gradient
        thisenergy = gradient(name, **kwargs)

        # Take step
        if PsiMod.optking() == PsiMod.PsiReturnType.EndLoop:
            print "Optimizer: Optimization complete!"
            PsiMod.opt_clean()
            PsiMod.clean()
            return thisenergy

    PsiMod.print_out("\tOptimizer: Did not converge!")
    return 0.0

def parse_arbitrary_order(name):
    namelower = name.lower()

    if re.match(r'^[a-z]+\d+$', namelower):       
        decompose = re.compile(r'^([a-z]+)(\d+)$').match(namelower)
        namestump = decompose.group(1)
        namelevel = int(decompose.group(2))

        if (namestump == 'mp') or (namestump == 'zapt') or (namestump == 'ci'):
            # Let 'mp2' pass through as itself
            if (namestump == 'mp') and (namelevel == 2):
                return namelower, None
            # Otherwise return method and order
            else:
                return namestump, namelevel
        else:
            return namelower, None
    else:
        return namelower, None

def frequencies(name, **kwargs):
    lowername = name.lower()

    # Make sure the molecule the user provided is the active one
    if (kwargs.has_key('molecule')):
        activate(kwargs['molecule'])
        del kwargs['molecule']
    molecule = PsiMod.get_active_molecule()
    molecule.update_geometry()
    PsiMod.set_global_option("BASIS", PsiMod.get_global_option("BASIS"))

    dertype = 2
    if (kwargs.has_key('dertype')):
        dertype = kwargs['dertype']

    if (kwargs.has_key('irrep')):
        irrep = kwargs['irrep'] - 1 # externally, A1 irrep is 1; internally 0
    else:
      irrep = -1; # -1 implies do all irreps 

    # By default, set func to the energy function
    func = energy
    func_existed = False
    if (kwargs.has_key('func')):
        func = kwargs['func']
        func_existed = True

    # Does an analytic procedure exist for the requested method?
    if (procedures['hessian'].has_key(lowername) and dertype == 2 and func_existed == False):
        # We have the desired method. Do it.
        procedures['hessian'][lowername](lowername, **kwargs)
        return PsiMod.reference_wavefunction().energy()
    elif (procedures['gradient'].has_key(lowername) and dertype == 1 and func_existed == False):
        # Ok, we're doing frequencies by gradients
        info = "Performing finite difference by gradient calculations"
        print info

        func = procedures['gradient'][lowername]

        # Obtain list of displacements
        displacements = PsiMod.fd_geoms_freq_1()
        ndisp = len(displacements)

        print " %d displacements needed." % ndisp
        gradients = []
        for n, displacement in enumerate(displacements):
            # Print information to output.dat
            PsiMod.print_out("\n")
            banner("Loading displacement %d of %d" % (n+1, ndisp))

            # Print information to the screen
            print "    displacement %d" % (n+1)

            # Load in displacement into the active molecule
            PsiMod.get_active_molecule().set_geometry(displacement)

            # Perform the gradient calculation
            G = func(lowername, **kwargs)

            # Save the gradient
            gradients.append(G)

        PsiMod.fd_freq_1(gradients)

        print " Computation complete."

    else: # Assume energy points
        # If not, perform finite difference of energies
        info = "Performing finite difference calculations"
        print info

        # Obtain list of displacements
        displacements = PsiMod.fd_geoms_freq_0(irrep)

        ndisp = len(displacements)

        # This version is pretty dependent on the reference geometry being last (as it is now)
        print " %d displacements needed." % ndisp
        energies = []
        for n, displacement in enumerate(displacements):
            # Print information to output.dat
            PsiMod.print_out("\n")
            banner("Loading displacement %d of %d" % (n+1, ndisp))

            # Print information to the screen
            print "    displacement %d" % (n+1)

            # Load in displacement into the active molecule
            PsiMod.get_active_molecule().set_geometry(displacement)

            # Perform the energy calculation
            E = func(lowername, **kwargs)

            # Save the energy
            energies.append(E)

            # clean may be necessary when changing irreps of displacements
            PsiMod.clean()

        # Obtain the gradient. This function stores the gradient into the reference wavefunction.
        PsiMod.fd_freq_0(energies, irrep)

        print " Computation complete."

        # The last item in the list is the reference energy, return it
        return energies[-1]


# to be changed to that it's behavior is different from frequencies()
# this one will get force constants
def hessian(name, **kwargs):
    lowername = name.lower()

    # Make sure the molecule the user provided is the active one
    if (kwargs.has_key('molecule')):
        activate(kwargs['molecule'])
        del kwargs['molecule']
    molecule = PsiMod.get_active_molecule()
    molecule.update_geometry()
    PsiMod.set_global_option("BASIS", PsiMod.get_global_option("BASIS"))

    dertype = 2
    if (kwargs.has_key('dertype')):
        dertype = kwargs['dertype']

    # By default, set func to the energy function
    func = energy
    func_existed = False
    if (kwargs.has_key('func')):
        func = kwargs['func']
        func_existed = True

    # Do we have analytic 2nd derivatives?
    if (procedures['hessian'].has_key(lowername) and dertype == 2 and func_existed == False):
        procedures['hessian'][lowername](lowername, **kwargs)
        return PsiMod.reference_wavefunction().energy()
    else: # Do finite differences of energies.
        info = "Performing finite difference calculations"
        print info

        displacements = PsiMod.fd_geoms_2_0()

        ndisp = len(displacements)

        print " %d displacements needed." % ndisp
        energies = []

        # Reference geometry and energy are last in list.
        for n, displacement in enumerate(displacements):
            PsiMod.print_out("\n")
            banner("Loading displacement %d of %d" % (n+1, ndisp))

            print "    displacement %d" % (n+1)

            PsiMod.get_active_molecule().set_geometry(displacement)

            E = func(lowername, **kwargs)
            energies.append(E)

        # Compute the hessian
        PsiMod.fd_2_0(energies)

        print " Computation complete."

        # The last item in the list is the reference energy, return it
        return energies[-1]

