"""Synthetic model-local meshes for support plane extraction."""
import numpy as np
import unittest


def board(z, x=0.0, size=1.0, downward=False):
    vertices = [(x, 0, z), (x + size, 0, z), (x + size, size, z), (x, size, z)]
    faces = [(0, 1, 2), (0, 2, 3)]
    return vertices, [tuple(reversed(f)) for f in faces] if downward else faces


def mesh(*boards):
    vertices, faces = [(0, 0, 0)], []
    for points, triangles in boards:
        offset = len(vertices)
        vertices.extend(points)
        faces.extend(tuple(i + offset for i in face) for face in triangles)
    return np.array(vertices), np.array(faces)


class SupportSurfacesTests(unittest.TestCase):
    def test_height_area_and_clearance_filters(self):
        from ffxiv_furniture.design.surfaces import measure_support_surfaces
        vertices, faces = mesh(board(0.1), board(0.3), board(0.4, downward=True),
                               board(0.8, size=0.1), board(1.2))
        surfaces = measure_support_surfaces(vertices, faces)
        np.testing.assert_allclose([s['z_local'] for s in surfaces], [1.2])

    def test_nearby_heights_merge_but_not_transitively(self):
        from ffxiv_furniture.design.surfaces import measure_support_surfaces
        vertices, faces = mesh(board(0.3), board(0.32, x=2), board(0.35, x=4), board(1.0, x=6))
        surfaces = measure_support_surfaces(vertices, faces)
        np.testing.assert_allclose([s['z_local'] for s in surfaces], [0.31, 0.35, 1.0])
        self.assertAlmostEqual(surfaces[0]['area_m2'], 2.0)

    def test_xy_disjoint_geometry_does_not_reduce_clearance(self):
        from ffxiv_furniture.design.surfaces import measure_support_surfaces
        vertices, faces = mesh(board(0.3), board(0.35, x=2, downward=True), board(1.0, x=2))
        surfaces = measure_support_surfaces(vertices, faces)
        self.assertAlmostEqual(surfaces[0]['clearance_above_m'], 0.7)

    def test_vertical_edge_contacts_do_not_block_boards(self):
        from ffxiv_furniture.design.surfaces import measure_support_surfaces
        vertices, faces = mesh(board(0.3), board(1.0))
        offset = len(vertices)
        vertices = np.vstack([vertices, [(0, 0, 0.3), (1, 0, 0.3), (1, 0, 1.0)]])
        faces = np.vstack([faces, [(offset, offset + 1, offset + 2)]])
        self.assertEqual(len(measure_support_surfaces(vertices, faces)), 2)

    def test_duplicate_triangles_do_not_inflate_area(self):
        from ffxiv_furniture.design.surfaces import measure_support_surfaces
        vertices, faces = mesh(board(0.3, size=0.1), board(0.3, size=0.1))
        self.assertEqual(measure_support_surfaces(vertices, faces), [])

    def test_side_panel_rising_from_board_is_not_an_overhead_plane(self):
        from ffxiv_furniture.design.surfaces import measure_support_surfaces
        vertices, faces = mesh(board(0.3), board(1.0))
        offset = len(vertices)
        vertices = np.vstack([vertices, [(0, 0, 0.3), (1, 0, 0.3), (1, 0.01, 1.0)]])
        faces = np.vstack([faces, [(offset, offset + 1, offset + 2)]])
        surfaces = measure_support_surfaces(vertices, faces)
        self.assertEqual(len(surfaces), 2)
        self.assertAlmostEqual(surfaces[0]['clearance_above_m'], 0.7)

    def test_inward_wound_extracted_box_has_upward_outward_top(self):
        from ffxiv_furniture.design.surfaces import measure_support_surfaces
        vertices = np.array([(0,0,0), (1,0,0), (1,1,0), (0,1,0),
                             (0,0,0.3), (1,0,0.3), (1,1,0.3), (0,1,0.3)])
        outward = np.array([(0,2,1),(0,3,2),(4,5,6),(4,6,7),
                            (0,1,5),(0,5,4),(1,2,6),(1,6,5),
                            (2,3,7),(2,7,6),(3,0,4),(3,4,7)])
        surfaces = measure_support_surfaces(vertices, outward[:, ::-1])
        self.assertEqual(len(surfaces), 1)
        self.assertAlmostEqual(surfaces[0]['z_local'], 0.3)
        self.assertEqual(surfaces[0]['is_top'], 1)

    def test_stacked_boards_cluster_and_clearance(self):
        from ffxiv_furniture.design.surfaces import measure_support_surfaces
        vertices, faces = mesh(board(0.3), board(0.8, downward=True), board(0.85), board(1.4))
        surfaces = measure_support_surfaces(vertices, faces)
        np.testing.assert_allclose([s['z_local'] for s in surfaces], [0.3, 0.85, 1.4])
        np.testing.assert_allclose([s['clearance_above_m'] for s in surfaces], [0.5, 0.55, 9.9])
        self.assertEqual([s['is_top'] for s in surfaces], [0, 0, 1])
        self.assertAlmostEqual(surfaces[0]['area_m2'], 1.0)
        self.assertEqual([surfaces[0][k] for k in ('min_x', 'min_y', 'max_x', 'max_y')], [0, 0, 1, 1])
