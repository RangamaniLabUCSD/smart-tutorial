from smart import config, mesh, model, mesh_tools, visualization
from smart.units import unit
from smart.model_assembly import (
    Compartment,
    Parameter,
    Reaction,
    Species,
    SpeciesContainer,
    ParameterContainer,
    CompartmentContainer,
    ReactionContainer,
)
import logging
logger = logging.getLogger("smart")
import dolfin as d
from matplotlib import pyplot as plt
import pathlib
import numpy as np

folder5 = pathlib.Path("part5")
folder5.mkdir(exist_ok=True)

AR1 = 1.0
sourceRad = [5.0*AR1**(1/3),5.0*AR1**(1/3),5.0*AR1**(-2/3)]
sourceLoc = [[0,0,0]]

AR2 = 1.0
otherCellRad = [5.0*AR2**(1/3),5.0*AR2**(1/3),5.0*AR2**(-2/3)]
otherCellLoc = [[DEFINE ADDITIONAL LOCATIONS HERE]] 
otherCellRad = len(otherCellLoc)*[otherCellRad]

dmesh, facet_markers, cell_markers = mesh_tools.create_multicell(
                                                  cubeSize=50, 
                                                  locVec1=sourceLoc, cellRad1=sourceRad,
                                                  locVec2=otherCellLoc, cellRad2=otherCellRad,
                                                  hCube=5.0, hCell=0.5, 
                                                  interface_marker1=11, interface_marker2=12, outer_marker=10,
                                                  extracell_tag=1)

mesh_tools.write_mesh(dmesh, facet_markers, cell_markers, str(folder5 / "extracell.h5"))
D_unit = unit.um**2 / unit.s
conc_unit = unit.molecule / unit.um**3
surf_unit = unit.molecule / unit.um**2

EC_var = Compartment("EC", 3, unit.um, 1)#, vel=[0.0,0.0,0.0])
source_var = Compartment("source", 2, unit.um, 11)
outer_var = Compartment("outer", 2, unit.um, 10)
cellmem_var = Compartment("cellmem", 2, unit.um, 12)
c_var = Species("c", 0, conc_unit, 130.0, D_unit, "EC")
R_var = Species("R", 10.0, surf_unit, 0.0, D_unit, "cellmem")
kdecay_var = Parameter("kdecay", 0.011, 1/unit.s)
r_decay = Reaction("r_decay", ["c"], [], param_map={"k":"kdecay"},
                    species_map={"c":"c"}, eqn_f_str="k*c")
j0_var = Parameter("j0", 100.0, surf_unit/unit.s)
r_release = Reaction("r_release", [], ["c"],
                     param_map={"j0":"j0"}, eqn_f_str="j0",
                     explicit_restriction_to_domain="source")

Rtot = Parameter("Rtot", 10.0, surf_unit)
kon_var = Parameter("kon", 100.0, 1/(conc_unit*unit.s))
koff_var = Parameter("koff", 1.0, 1/unit.s)
r_bind = Reaction("r_bind", ["c","R"], [],
                     param_map={"kon":"kon", "koff":"koff", "Rtot":"Rtot"}, 
                     eqn_f_str="kon*c*R - koff*(Rtot-R)",
                     explicit_restriction_to_domain="cellmem")
# create containers
cc = CompartmentContainer()
cc.add([EC_var, source_var, cellmem_var])
sc = SpeciesContainer()
sc.add([c_var, R_var])
pc = ParameterContainer()
pc.add([kdecay_var, j0_var, Rtot, kon_var, koff_var])
rc = ReactionContainer()
rc.add([r_decay, r_release, r_bind])
parent_mesh = mesh.ParentMesh(mesh_filename=str(folder5 / "extracell.h5"), 
                              mesh_filetype="hdf5", name="parent_mesh")
config_cur = config.Config()
model_cur = model.Model(pc, sc, cc, rc, config_cur, parent_mesh)
config_cur.solver.update({"final_t": 1.0, "initial_dt": 0.05})
model_cur.initialize()
results = dict()
for species_name, species in model_cur.sc.items:
    results[species_name] = d.XDMFFile(model_cur.mpi_comm_world, 
                                       str(folder5 / f"{species_name}.xdmf"))
    results[species_name].parameters["flush_output"] = True
    results[species_name].write(model_cur.sc[species_name].sol, model_cur.t)

# An ROI can be defined to integrate over a specific subvolume.
# If use_roi is false, then the integral for c_roi is conducted over the source surface
use_roi = False
if use_roi:
    class ROI(d.SubDomain):
        def inside(self, x, on_boundary):
            rcur = np.sqrt(x[0]**2 + x[1]**2 + x[2]**2)
            return (rcur > 5.5) and (rcur < 6.5)
    mf_int = d.MeshFunction("size_t", model_cur.cc["EC"].dolfin_mesh, 3, 0)
    roiDef = ROI()
    roiDef.mark(mf_int, 1) # mark roi with 1
    dx = d.Measure("dx", domain=model_cur.cc["EC"].dolfin_mesh, subdomain_data=mf_int)
else:
    dx = d.Measure("dx", domain=model_cur.cc["EC"].dolfin_mesh)
    dx_source = d.Measure("dx", domain=model_cur.cc["source"].dolfin_mesh)

volume = d.assemble_mixed(1.0*dx)
avg_c = [d.assemble_mixed(model_cur.sc["c"].sol*dx)/volume]
if use_roi:
    roi_vol = d.assemble_mixed(1.0*dx(1))
    c_roi = [d.assemble_mixed(model_cur.sc["c"].sol*dx(1))/roi_vol]
else:
    roi_vol = d.assemble_mixed(1.0*dx_source)
    c_roi = [d.assemble_mixed(model_cur.sc["c"].sol*dx_source)/roi_vol]
logger.setLevel(logging.WARNING) # suppress excessive output
while True:
    model_cur.monolithic_solve()
    print(f"Done with t = {model_cur.t}")
    for species_name, species in model_cur.sc.items:
        results[species_name].write(model_cur.sc[species_name].sol, model_cur.t)
    avg_c.append(d.assemble_mixed(model_cur.sc["c"].sol*dx) / volume)
    if use_roi:
        c_roi.append(d.assemble_mixed(model_cur.sc["c"].sol*dx(1))/roi_vol)
    else:
        c_roi.append(d.assemble_mixed(model_cur.sc["c"].sol*dx_source)/roi_vol)
    if model_cur.t >= model_cur.final_t:
        break

import numpy as np
from scipy.special import erfc
# now plot and compare to analytical solution
plt.plot(model_cur.tvec, c_roi, label="SMART")
# analytical solution at source membrane
t = np.array([float(val) for val in model_cur.tvec])
t[0] = 1e-6
j0 = j0_var.value
R = 5.0
dr = 0.0
D = c_var.D
k = kdecay_var.value
multFactor = j0*R**2/(dr + R)
term1 = (1/(2*(D+R*np.sqrt(D*k))))*np.exp(-dr/np.sqrt(D/k))*erfc(dr/(2*np.sqrt(D*t)) - np.sqrt(k*t))
term2 = (1/(2*(D-R*np.sqrt(D*k))))*np.exp(dr/np.sqrt(D/k))*erfc(dr/(2*np.sqrt(D*t)) + np.sqrt(k*t))
term3 = (-1/(D-k*R**2))*np.exp(dr/R + (D/R**2 - k)*t)*erfc(dr/(2*np.sqrt(D*t)) + np.sqrt(D*t)/R)
cAnalytical = multFactor*(term1 + term2 + term3)
plt.plot(t, cAnalytical, label="Analytical")

plt.xlabel('Time (s)')
plt.ylabel('c concentration $\mathrm{(molecules/μm^3)}$')
plt.legend()
plt.savefig(str(folder5 / "part5plot.png"))
plt.show()

visualization.plot(model_cur.sc["c"].sol)