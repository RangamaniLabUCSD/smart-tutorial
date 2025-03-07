import gmsh
import pathlib
import smart
gmsh.initialize()
gmsh.open("spot.msh")
surf = gmsh.model.get_entities(2)
loop = gmsh.model.geo.add_surface_loop([surf[0][1]])
vol = gmsh.model.geo.add_volume([loop])
gmsh.model.geo.synchronize()
gmsh.model.add_physical_group(3, [vol], tag=1)
gmsh.model.add_physical_group(2, [loop], tag=10)
gmsh.model.mesh.generate(3)
tmp_folder = pathlib.Path(f"tmpmesh")
tmp_folder.mkdir(exist_ok=True)
gmsh_file = tmp_folder / "tmpspot.msh"
gmsh.write(str(gmsh_file))
gmsh.finalize()
# return dolfin mesh of max dimension (parent mesh) and marker functions mf2 and mf3
dmesh, mf2, mf3 = smart.mesh_tools.gmsh_to_dolfin(str(gmsh_file), tmp_folder, 3)
smart.mesh_tools.write_mesh(dmesh, mf2, mf3, "spot_mesh.h5")