# Copyright (C) 2013 - Zhongnan Xu
"""This module contains specifically the functions needed running linear response calculations
"""

from espresso import *

#################################
## Linear response U functions ##
#################################
        
def initialize_lrU(self, patoms):
    '''The purpose of this initialize function is to re-order the atoms
    object so that it can be run in a linear response calculation'''

    # We first want to re-sort the atoms so that unique atoms are grouped together
    # and the non-unique atoms are at the back
    atoms = self.get_atoms()
    indexes = range(len(atoms))
    keys = sorted(patoms.keys())

    sort = []
    for key in keys:
        sort += list(patoms[key])
    for i in indexes:
        if i not in sort:
            sort.append(i)

    atoms = atoms[sort]
    self.atoms = atoms

    # Also re-sort the Hubbard_alpha, Hubbard_U and tags parameters
    Hubbard_alpha = self.list_params['Hubbard_alpha']
    Hubbard_U = self.list_params['Hubbard_U']
    self.list_params['Hubbard_alpha'] = [Hubbard_alpha[i] for i in sort]
    self.list_params['Hubbard_U'] = [Hubbard_U[i] for i in sort]

    return sort

Espresso.initialize_lrU = initialize_lrU
    
def run_scf(self, patoms, center=True):
    '''The purpose of this function is to create separate folders for each
    atom that one needs to perturb and then run the self-consistent calculations.
    A couple of things this function needs to do...
    1. Read in a dictionary file that tells us which atoms need to be perturbed
       and which other atoms are equivalent to this perturbed atom.
    2. Re-organize the atoms so that the different 'types' are grouped together
       with the perturbed atom at the first
    3. Create different folders for each scf calculation and future perturbation
       calculations.'''

    atoms = self.get_atoms()
    indexes = range(len(atoms))
    keys = sorted(patoms.keys())

    sort = self.initialize_lrU(patoms)

    # Now create folders for each perturbation and run the scf calculations
    cwd = os.getcwd()
    original_filename = self.filename
    for i, key in enumerate(keys):
        i += 1
        tags = []
        for k in indexes:
            if k == sort.index(key):
                tags.append(i)
            else:
                tags.append(0)
        self.initialize_atoms(tags=tags)
        self.int_params['ntyp'] = len(self.unique_set)
        if center == True:
            pos = self.atoms.get_positions()
            trans = pos[sort.index(key)]
            self.atoms.translate(-trans)
        self.filename = original_filename + '-{0:d}-pert'.format(i)
        if not os.path.isdir(self.filename):
            os.makedirs(self.filename)
        os.chdir(self.filename)
        if self.check_calc_complete() == False:
            self.write_input()
            self.run_params['jobname'] = self.espressodir + '-{0:d}-scf'.format(i)
            self.run(series=True)
        os.chdir(cwd)

    return

Espresso.run_scf = run_scf
    
def run_perts(self, indexes, alphas=(-0.15, -0.07, 0, 0.07, 0.15),
              test=False, walltime='50:00:00', mem='2GB'):
    '''The purpose of this to to run perturbations following the scf
    calculations that were run with the self.run_scf command.'''

    original_filename = self.filename
    cwd = os.getcwd()
    for i, ind in enumerate(indexes):
        i += 1 
        self.filename = original_filename + '-{0:d}-pert'.format(i)
        os.chdir(self.filename)
        # First check if the self-consistent calculation is complete
        if self.check_calc_complete() == False:
            pass
        self.run_params['jobname']  = self.espressodir + '-{0:d}'.format(i)
        self.run_pert(alphas=alphas, index=ind, test=test, walltime=walltime,
                      mem=mem)
        os.chdir(cwd)
    return

Espresso.run_perts = run_perts
    
def calc_Us(self, patoms, alphas=(-0.15, -0.07, 0, 0.07, 0.15), test=False, sc=1):
    '''The purpose of this program is to take the data out of the
    already run calculations and feed it to the r.x program, which
    calculates the linear response U. This function can calculate Us
    in systems with multiple atoms perturbed'''

    sort = self.initialize_lrU(patoms)

    if not isdir ('Ucalc'):
        os.mkdir('Ucalc')

    keys = sorted(patoms.keys())
    allatoms = []
    for key in keys:
        for index in patoms[key]:
            allatoms.append(index)

    cwd = os.getcwd()
    for i, key in enumerate(keys):
        os.chdir(self.filename + '-{0:d}-pert'.format(i + 1))
        # First assert that the calculations are done            
        for alpha in alphas:
            assert isfile('results/alpha_{0}.out'.format(alpha))
            assert self.check_calc_complete(filename='results/alpha_{0}.out'.format(alpha))
                # Create the arrays for storing the atom and their occupancies
        alpha_0s, alpha_fs = [], []

        # Store the initial and final occupations in arrays
        for alpha in alphas:
            occ_0s, occ_fs = [], []
            outfile = open('results/alpha_{0}.out'.format(alpha))
            lines = outfile.readlines()
            calc_started = False
            calc_finished = False
            for line in lines:
                # We first want to read the initial occupancies. This happens after
                # the calculation starts.
                if line.startswith('     Self'):
                    calc_started = True
                if line.startswith('     End'):
                    calc_finished = True
                # We will first 
                if not line.startswith('atom '):
                    continue
                occ = float(line.split()[-1])
                if calc_started == True and calc_finished == False:
                    occ_0s.append(occ)
                elif calc_finished == True:
                    occ_fs.append(occ)
                else:
                    continue
            alpha_0s.append(occ_0s)
            alpha_fs.append(occ_fs)

        # Write out the dn files
        os.chdir(cwd)
        dnda = open('Ucalc/dnda', 'a')
        for atom in range(len(allatoms)):
            list_0, list_f = [], []
            for i, alpha in enumerate(alphas):
                list_0.append(alpha_0s[i][atom])
                list_f.append(alpha_fs[i][atom])
            dn0_file = open('Ucalc/dn0.{0}.da.{1}.dat'.format(atom + 1,
                                                              sort.index(key) + 1), 'w')
            for alpha, occ in zip(alphas, list_0):
                dn0_file.write(' {alpha}  {occ}\n'.format(**locals()))
            dn0_file.close()
            dn_file = open('Ucalc/dn.{0}.da.{1}.dat'.format(atom + 1,
                                                            sort.index(key) + 1), 'w')
            for alpha, occ in zip(alphas, list_f):
                dn_file.write(' {alpha}  {occ}\n'.format(**locals()))
            dn_file.close()
            dnda_filename = 'dn.{0}.da.{1}.dat dn0.{0}.da.{1}.dat\n'
            dnda.write(dnda_filename.format(atom + 1, sort.index(key) + 1))
        dnda.close()

    # Write out the pos files
    pos_file = open('Ucalc/pos', 'w')
    for vec in self.atoms.cell:
        pos_file.write('{0} {1} {2}\n'.format(vec[0], vec[1], vec[2]))
    positions = self.atoms.get_scaled_positions()
    magmoms = self.atoms.get_initial_magnetic_moments()
    indexes = np.arange(len(positions))
    for ind, pos, mag in zip(indexes, positions, magmoms):
        if ind not in allatoms:
            continue
        if mag > 0:
            m = 1
        elif mag < 0:
            m = -1
        elif mag == 0:
            m = 0  
        pos_file.write('{0:1.5f} {1:1.5f} {2:1.5f} {3}\n'.format(pos[0], pos[1], pos[2], m))
    pos_file.close()

    # Finally, write out the input file for the r.x calculations
    rxinput = open('Ucalc/rx.in', 'w')
    rxinput.write('&input_mat\n')
    rxinput.write('  ntyp = {0}\n'.format(len(keys)))
    for i, key in enumerate(keys):
        rxinput.write('  na({0}) = {1}\n'.format(i + 1, len(patoms[key])))
    rxinput.write('  nalfa = {0:d}\n'.format(len(alphas)))
    rxinput.write('  magn = .True.\n')
    rxinput.write("  filepos = 'pos'\n")
    rxinput.write("  back = 'no'\n")
    rxinput.write("  filednda = 'dnda'\n")
    rxinput.write('  n1 = {0}\n'.format(sc))
    rxinput.write('  n2 = {0}\n'.format(sc))
    rxinput.write('  n3 = {0}\n'.format(sc))
    rxinput.write('&end')

    return

Espresso.calc_Us = calc_Us
    
def write_pert(self, alphas=(-0.15, -0.07, 0.0, 0.07, 0.15,), index=1, parallel=False):
    '''The purpose of this function is to calculate the linear response U
    after a self-consistent calculation has already been done. Some notes:

    The self-consistent calculation should have a unique atom that is
    perturbed. All atoms should also have non-zero but very low Hubbard
    U values applied. The unique atom, however, should have a different
    Hubbard U applied than its equivalent atoms.'''

    import shutil
    import fnmatch

    # First, read the diago_thr_init, which is needed for the perturbation
    scf_out = open(self.filename + '.out', 'r')
    for line in scf_out.readlines():
        if line.lower().startswith('     ethr'):
            ethr = float(line.split()[2].translate(None, ','))

    # First make the perturbations results folder
    if not os.path.isdir('results'):
        os.makedirs('results')

    # Now check to see which perturbations need to be done
    run_alphas = []    
    for alpha in alphas:
        fname = 'results/alpha_{alpha}.out'.format(**locals())
        if not self.check_calc_complete(filename=fname):
            run_alphas.append(alpha)


    # If all of them are complete just return
    if len(run_alphas) == 0:
        return None

    # Now create the input files that need to be run. These need to each
    # be in their own directory
    for alpha in run_alphas:
        orig_file = open(self.filename + '.in', 'r')
        lines = orig_file.readlines()
        # Also delete old files that were left from previous calculations
        try:
            for ef in os.listdir('alpha_{alpha}'.format(**locals())):
                if (fnmatch.fnmatch(ef, 'pwscf.*')
                    and os.path.isfile('alpha_{alpha}/{ef}'.format(**locals()))):
                    os.remove('alpha_{alpha}/{ef}'.format(**locals()))
                elif (fnmatch.fnmatch(ef, 'pwscf.*')
                      and os.path.isdir('alpha_{alpha}/{ef}'.format(**locals()))):
                    shutil.rmtree('alpha_{alpha}/{ef}'.format(**locals()))
        except:
            pass
        if parallel == False:
            if not os.path.isdir('alpha_' + str(alpha)):
                os.mkdir('alpha_' + str(alpha))
            new_file = open('alpha_{alpha}/alpha_{alpha}.in'.format(**locals()), 'w')
        else:
            new_file = open('alpha_{alpha}.in'.format(**locals()), 'w')
        for line in lines:
            if line.split()[0].lower() == '&control':
                new_file.write(line)
                new_file.write(" outdir = 'alpha_{alpha}/'\n".format(**locals()))
            elif line.split()[0].lower() == '&electrons':
                new_file.write(line)
                new_file.write(" startingwfc = 'file'\n")
                new_file.write(" startingpot = 'file'\n")
                new_file.write(" diago_thr_init = {ethr:.8g}\n".format(**locals()))
            elif line.split()[0].lower() == "hubbard_alpha({0})".format(int(index)):
                new_file.write(" Hubbard_alpha({0}) = {1}\n".format(int(index),
                                                                   alpha))
            else:
                new_file.write(line)

    return run_alphas

Espresso.write_pert = write_pert
    
def run_pert(self, alphas=(-0.15, -0.07, 0, 0.07, 0.15), index=1, test=False,
             walltime='50:00:00', mem='2GB'):
    '''Now we create the runscript that performs the calculations. This will
    be tricky because we need to write a script that copies the saved files
    from the previous calculation to be used in these perturbation calculations.
    Also note that index in this case is the index, starting at 1, of the unique
    atom that is to be perturbed.
    '''

    run_alphas = self.write_pert(alphas=alphas, index=index, parallel=False)
    if run_alphas == None:
        return

    if self.run_params['jobname'] == None:
        self.run_params['jobname'] = self.espressodir + '-pert'
    else:
        self.run_params['jobname'] += '-pert'

    run_file_name = self.filename + '.run'

    np = self.run_params['nodes'] * self.run_params['ppn']
    
    script = '''#!/bin/bash
#PBS -l walltime={0}
#PBS -l nodes={1:d}:ppn={2:d}
#PBS -l mem={4}
#PBS -j oe
#PBS -N {3}
cd $PBS_O_WORKDIR
'''.format(walltime, self.run_params['nodes'], self.run_params['ppn'],
           self.run_params['jobname'], self.run_params['mem'])

    run_cmd = self.run_params['executable']

    if self.run_params['ppn'] == 1:
        for alpha in run_alphas:
            run_script = '''cp -r pwscf.* alpha_{0}/
{1} < alpha_{0}/alpha_{0}.in > results/alpha_{0}.out
rm -fr alpha_{0}/pwscf.*
'''.format(alpha, run_cmd)
            script += run_script
    else:
        for alpha in run_alphas:
            run_script = '''cp -r pwscf.* alpha_{0}/
mpirun -np {1:d} {2} -inp alpha_{0}/alpha_{0}.in -npool {3} > results/alpha_{0}.out
rm -fr alpha_{0}/pwscf.*
'''.format(alpha, np, run_cmd, self.run_params['pools'])

            script += run_script

    script += '# end\n'
    if test == True:
        print script
        return
    run_file = open(run_file_name, 'w')
    run_file.write(script)
    run_file.close()

    # Now just submit the calculations
    p = Popen(['qsub', run_file_name], stdout=PIPE, stderr=PIPE)

    out, err = p.communicate(script)
    f = open('jobid', 'w')
    f.write(out)
    f.close()

    return

Espresso.run_pert = run_pert
    
def calc_U(self, dict_index, alphas=(-0.15, -0.07, 0, 0.07, 0.15), test=False, sc=1):
    '''The purpose of this program is to take the data out of the
    already run calculations and feed it to the r.x program, which
    calculates the linear response U.

    The dict_index contains all the information about the perturbed and the
    equivalent mirror images of this atom. The index of the dict is the
    perturbed atom, and the object of the.'''

    if not isdir('Ucalc'):
        os.mkdir('Ucalc')

    # First assert that the perturbation calculations are done
    for alpha in alphas:
        assert isfile('results/alpha_{0}.out'.format(alpha))
        assert self.check_calc_complete(filename='results/alpha_{0}.out'.format(alpha))

    # Create the arrays for storing the atom and their occupancies
    alpha_0s, alpha_fs = [], []

    # Store the initial and final occupations in arrays
    for alpha in alphas:
        occ_0s, occ_fs = [], []
        outfile = open('results/alpha_{0}.out'.format(alpha))
        lines = outfile.readlines()
        calc_started = False
        calc_finished = False
        for line in lines:
            # We first want to read the initial occupancies. This happens after
            # the calculation starts.
            if line.startswith('     Self'):
                calc_started = True
            if line.startswith('     End'):
                calc_finished = True
            # We will first 
            if not line.startswith('atom '):
                continue
            occ = float(line.split()[-1])
            if calc_started == True and calc_finished == False:
                occ_0s.append(occ)
            elif calc_finished == True:
                occ_fs.append(occ)
            else:
                continue
        alpha_0s.append(occ_0s)
        alpha_fs.append(occ_fs)

    # Write out the dn files
    dnda = open('Ucalc/dnda', 'w')
    key = dict_index.keys()[0]
    pindex = dict_index[key].index(key)
    for j, atom in enumerate(dict_index[key]):
        list_0, list_f = [], []
        for i, alpha in enumerate(alphas):
            list_0.append(alpha_0s[i][atom])
            list_f.append(alpha_fs[i][atom])
        dn0_file = open('Ucalc/dn0.{0}.da.{1}.dat'.format(int(j) + 1,
                                                          pindex + 1), 'w')
        for alpha, occ in zip(alphas, list_0):
            dn0_file.write(' {alpha}  {occ}\n'.format(**locals()))
        dn0_file.close()
        dn_file = open('Ucalc/dn.{0}.da.{1}.dat'.format(int(j) + 1,
                                                        pindex + 1), 'w')
        for alpha, occ in zip(alphas, list_f):
            dn_file.write(' {alpha}  {occ}\n'.format(**locals()))
        dn_file.close()
        dnda_filename = 'dn.{0}.da.{1}.dat dn0.{0}.da.{1}.dat\n'
        dnda.write(dnda_filename.format(int(j) + 1, pindex + 1))
    dnda.close()

    # Write out the pos files
    pos_file = open('Ucalc/pos', 'w')
    for vec in self.atoms.cell:
        pos_file.write('{0} {1} {2}\n'.format(vec[0], vec[1], vec[2]))
    positions = self.atoms.get_scaled_positions()
    magmoms = self.atoms.get_initial_magnetic_moments()
    indexes = np.arange(len(positions))
    for ind, pos, mag in zip(indexes, positions, magmoms):
        if ind not in dict_index[key]:
            continue
        if mag > 0:
            m = 1
        elif mag < 0:
            m = -1
        elif mag == 0:
            m = 1                
        pos_file.write('{0:1.5f} {1:1.5f} {2:1.5f} {3}\n'.format(pos[0], pos[1], pos[2], m))
    pos_file.close()

    # Finally, write out the input file for the r.x calculations
    rxinput = open('Ucalc/rx.in', 'w')
    rxinput.write('&input_mat\n')
    rxinput.write('  ntyp = 1\n')
    rxinput.write('  na(1) = {0}\n'.format(len(dict_index[key])))
    rxinput.write('  nalfa = {0:d}\n'.format(len(alphas)))
    rxinput.write('  magn = .True.\n')
    rxinput.write("  filepos = 'pos'\n")
    rxinput.write("  back = 'no'\n")
    rxinput.write("  filednda = 'dnda'\n")
    rxinput.write('  n1 = {0}\n'.format(sc))
    rxinput.write('  n2 = {0}\n'.format(sc))
    rxinput.write('  n3 = {0}\n'.format(sc))
    rxinput.write('&end')

    # Now perform the calculation
    os.chdir('Ucalc')
    Popen('r.x < rx.in', shell=True)
    sleep(3)
    Umat = open('Umat.out', 'r')
    for line in Umat.readlines():
        if not line.startswith('  type:'):
            continue
        U = float(line.split()[-1])
    os.chdir(self.cwd)

    return U 

Espresso.calc_U = calc_U
    
def read_Umat(self, f='Umat.out'):

    return

Espresso.read_Umat = read_Umat
    
def run_pert_parallel(self, alphas=(-0.15, -0.07, 0, 0.07, 0.15), index=1, test=False):
    '''This is a trial script to see if calculations can be done in parallel.
    '''
    run_alphas = self.write_pert(alphas=alphas, index=index, parallel=True)
    run_cmd = self.run_params['executable']
    for alpha in run_alphas:
        script = '''#!/bin/bash
cd $PBS_O_WORKDIR
{0} < alpha_{1}.in > results/alpha_{1}.out
# end
'''.format(run_cmd, alpha)
        if self.run_params['jobname'] == None:
            self.run_params['jobname'] = self.espressodir + '-pert'
        else:
            self.run_params['jobname'] += '-pert'

        resources = '-l walltime={0},nodes={1:d}:ppn={2:d}'
        if test == True:
            print script
            continue
        p = Popen(['qsub',
                   self.run_params['options'],
                   '-N', self.run_params['jobname'] + '_{0}'.format(alpha),
                   resources.format(self.run_params['walltime'],
                                    self.run_params['nodes'],
                                    self.run_params['ppn'])],
                  stdin=PIPE, stdout=PIPE, stderr=PIPE)
        out, err = p.communicate(script)
        f = open('jobid', 'w')
        f.write(out)
        f.close()

    return

Espresso.run_pert_parallel = run_pert_parallel
