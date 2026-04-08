import open3d as o3d
import numpy as np

# Charger votre PCD
pcd = o3d.io.read_point_cloud("pointcloud_map.pcd")
points = np.asarray(pcd.points)

# SOLUTION 1 : Supprimer les points exactement à l'origine (les rayons ratés de CARLA)
distances = np.linalg.norm(points, axis=1)
valid_points = points[distances > 1.0] # Garde les points à plus de 1 mètre de l'origine (0,0,0)

# Mettre à jour et sauvegarder
pcd.points = o3d.utility.Vector3dVector(valid_points)
o3d.io.write_point_cloud("carte_corrigee.pcd", pcd)