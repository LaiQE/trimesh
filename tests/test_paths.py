try:
    from . import generic as g
except BaseException:
    import generic as g


class VectorTests(g.unittest.TestCase):

    def test_discrete(self):

        for d in g.get_2D():
            # store md5 before requesting passive functions
            md5 = d.md5()

            # make sure various methods return
            # basically the same bounds
            atol = d.scale / 1000
            for dis, pa, pl in zip(d.discrete,
                                   d.paths,
                                   d.polygons_closed):
                # bounds of discrete version of path
                bd = g.np.array([g.np.min(dis, axis=0),
                                 g.np.max(dis, axis=0)])
                # bounds of polygon version of path
                bl = g.np.reshape(pl.bounds, (2, 2))
                # try bounds of included entities from path
                pad = g.np.vstack([d.entities[i].discrete(d.vertices)
                                   for i in pa])
                bp = g.np.array([g.np.min(pad, axis=0),
                                 g.np.max(pad, axis=0)])

                assert g.np.allclose(bd, bl, atol=atol)
                assert g.np.allclose(bl, bp, atol=atol)

            # run some checks
            check_Path2D(d)

            # copying shouldn't touch original file
            copied = d.copy()

            # these operations shouldn't have mutated anything!
            assert d.md5() == md5

            # copy should have saved the metadata
            assert set(copied.metadata.keys()) == set(d.metadata.keys())

            # file_name should be populated, and if we have a DXF file
            # the layer field should be populated with layer names
            if d.metadata['file_name'][-3:] == 'dxf':
                assert len(d.layers) == len(d.entities)

            for path in d.paths:
                verts = d.discretize_path(path)
                dists = g.np.sum((g.np.diff(verts, axis=0))**2, axis=1)**.5

                if not g.np.all(dists > g.tol_path.zero):
                    raise ValueError('{} had zero distance in discrete!',
                                     d.metadata['file_name'])

                circuit_dist = g.trimesh.util.euclidean(verts[0], verts[-1])
                circuit_test = circuit_dist < g.tol_path.merge
                if not circuit_test:
                    g.log.error('On file %s First and last vertex distance %f',
                                d.metadata['file_name'],
                                circuit_dist)
                assert circuit_test

                is_ccw = g.trimesh.path.util.is_ccw(verts)
                if not is_ccw:
                    g.log.error('discrete %s not ccw!',
                                d.metadata['file_name'])

            for i in range(len(d.paths)):
                assert d.polygons_closed[i].is_valid
                assert d.polygons_closed[i].area > g.tol_path.zero
            export_dict = d.export(file_type='dict')
            to_dict = d.to_dict()
            assert isinstance(to_dict, dict)
            assert isinstance(export_dict, dict)
            assert len(to_dict) == len(export_dict)

            export_svg = d.export(file_type='svg')
            simple = d.simplify()
            split = d.split()
            g.log.info('Split %s into %d bodies, checking identifiers',
                       d.metadata['file_name'],
                       len(split))
            for body in split:
                body.identifier

            if len(d.root) == 1:
                d.apply_obb()

            # store the X values of bounds
            ori = d.bounds.copy()
            # apply a translation
            d.apply_translation([10, 0])
            # X should have translated by 10.0
            assert g.np.allclose(d.bounds[:, 0] - 10, ori[:, 0])
            # Y should not have moved
            assert g.np.allclose(d.bounds[:, 1], ori[:, 1])

            if len(d.polygons_full) > 0 and len(d.vertices) < 150:
                g.log.info('Checking medial axis on %s',
                           d.metadata['file_name'])
                m = d.medial_axis()
                assert len(m.entities) > 0

            # shouldn't crash
            d.fill_gaps()

            # transform to first quadrant
            d.rezero()
            # run process manually
            d.process()

    def test_poly(self):
        p = g.get_mesh('2D/LM2.dxf')
        assert p.is_closed
        assert any(len(i.points) > 2 for i in p.entities if
                   g.trimesh.util.is_instance_named(i, 'Line'))

        assert len(p.layers) == len(p.entities)
        assert len(g.np.unique(p.layers)) > 1

        p.explode()
        assert all(len(i.points) == 2 for i in p.entities if
                   g.trimesh.util.is_instance_named(i, 'Line'))
        assert p.is_closed
        p.entities = p.entities[:-1]
        assert not p.is_closed

        # fill gaps of any distance
        p.fill_gaps(g.np.inf)
        assert p.is_closed

    def test_edges(self):
        """
        Test edges_to_polygon
        """
        m = g.get_mesh('featuretype.STL')

        # get a polygon for the second largest facet
        index = m.facets_area.argsort()[-2]
        normal = m.facets_normal[index]
        origin = m._cache['facets_origin'][index]
        T = g.trimesh.geometry.plane_transform(origin, normal)
        vertices = g.trimesh.transform_points(m.vertices, T)[:, :2]

        # find boundary edges for the facet
        edges = m.edges_sorted.reshape(
            (-1, 6))[m.facets[index]].reshape((-1, 2))
        group = g.trimesh.grouping.group_rows(edges, require_count=1)

        # run the polygon conversion
        polygon = g.trimesh.path.polygons.edges_to_polygons(
            edges=edges[group],
            vertices=vertices)

        assert len(polygon) == 1
        assert g.np.isclose(polygon[0].area,
                            m.facets_area[index])

        # try transforming the polygon around
        M = g.np.eye(3)
        M[0][2] = 10.0
        P2 = g.trimesh.path.polygons.transform_polygon(polygon[0], M)
        distance = g.np.array(P2.centroid) - g.np.array(polygon[0].centroid)
        assert g.np.allclose(distance, [10.0, 0])

    def test_random_polygon(self):
        """
        Test creation of random polygons
        """
        p = g.trimesh.path.polygons.random_polygon()
        assert p.area > 0.0
        assert p.is_valid

    def test_sample(self):
        """
        Test random sampling of polygons
        """
        p = g.Point([0, 0]).buffer(1.0)
        count = 100

        s = g.trimesh.path.polygons.sample(p, count=count)
        assert len(s) <= count
        assert s.shape[1] == 2

        radius = (s ** 2).sum(axis=1).max()
        assert radius < (1.0 + 1e-8)

        # test Path2D sample wiring
        path = g.trimesh.load_path(p)
        s = path.sample(count=count)
        assert len(s) <= count
        assert s.shape[1] == 2
        radius = (s ** 2).sum(axis=1).max()
        assert radius < (1.0 + 1e-8)

        # try getting OBB of samples
        T, extents = g.trimesh.path.polygons.polygon_obb(s)
        # OBB of samples should be less than diameter of circle
        diameter = g.np.reshape(p.bounds, (2, 2)).ptp(axis=0).max()
        assert (extents <= diameter).all()

        # test sampling with multiple bodies
        for i in range(3):
            assert g.np.isclose(path.area, p.area * (i + 1))
            path = path + g.trimesh.load_path(
                g.Point([(i + 2) * 2, 0]).buffer(1.0))
            s = path.sample(count=count)
            assert s.shape[1] == 2


class UpstreamTests(g.unittest.TestCase):
    def test_shapely(self):
        """
        conda installs of shapely started returning NaN on
        valid input so make sure our builds fail in that case
        """
        l = g.LineString([[0, 0], [1, 0]])
        assert g.np.isclose(l.length, 1.0)


class ArcTests(g.unittest.TestCase):

    def test_center(self):

        test_points = [[[0, 0], [1.0, 1], [2, 0]]]
        test_results = [[[1, 0], 1.0]]
        points = test_points[0]
        res_center, res_radius = test_results[0]
        center_info = g.trimesh.path.arc.arc_center(points)
        C, R, N, angle = (center_info['center'],
                          center_info['radius'],
                          center_info['normal'],
                          center_info['span'])

        assert abs(R - res_radius) < g.tol_path.zero
        assert g.trimesh.util.euclidean(C, res_center) < g.tol_path.zero

    def test_center_random(self):

        # Test that arc centers work on well formed random points in 2D and 3D
        min_angle = g.np.radians(2)
        min_radius = .0001
        count = 1000

        center_3D = (g.np.random.random((count, 3)) - .5) * 50
        center_2D = center_3D[:, 0:2]
        radii = g.np.clip(g.np.random.random(count) * 100, min_angle, g.np.inf)

        angles = g.np.random.random((count, 2)) * \
            (g.np.pi - min_angle) + min_angle
        angles = g.np.column_stack((g.np.zeros(count),
                                    g.np.cumsum(angles, axis=1)))

        points_2D = g.np.column_stack((g.np.cos(angles[:, 0]),
                                       g.np.sin(angles[:, 0]),
                                       g.np.cos(angles[:, 1]),
                                       g.np.sin(angles[:, 1]),
                                       g.np.cos(angles[:, 2]),
                                       g.np.sin(angles[:, 2]))).reshape((-1, 6))
        points_2D *= radii.reshape((-1, 1))
        points_2D += g.np.tile(center_2D, (1, 3))
        points_2D = points_2D.reshape((-1, 3, 2))
        points_3D = g.np.column_stack((points_2D.reshape((-1, 2)),
                                       g.np.tile(center_3D[:, 2].reshape((-1, 1)),
                                                 (1, 3)).reshape(-1))).reshape((-1, 3, 3))

        for center, radius, three in zip(center_2D,
                                         radii,
                                         points_2D):
            info = g.trimesh.path.arc.arc_center(three)

            assert g.np.allclose(center, info['center'])
            assert g.np.allclose(radius, info['radius'])

        for center, radius, three in zip(center_3D,
                                         radii,
                                         points_3D):
            transform = g.trimesh.transformations.random_rotation_matrix()
            center = g.trimesh.transformations.transform_points([center], transform)[
                0]
            three = g.trimesh.transformations.transform_points(
                three, transform)

            info = g.trimesh.path.arc.arc_center(three)

            assert g.np.allclose(center, info['center'])
            assert g.np.allclose(radius, info['radius'])

    def test_multiroot(self):
        """
        Test a Path2D object containing polygons nested in
        the interiors of other polygons.
        """
        inner = g.trimesh.creation.annulus(r_min=.5, r_max=.6)
        outer = g.trimesh.creation.annulus(r_min=.9, r_max=1.0)
        m = inner + outer

        s = m.section(plane_normal=[0, 0, 1],
                      plane_origin=[0, 0, 0])
        p = s.to_planar()[0]

        assert len(p.polygons_closed) == 4
        assert len(p.polygons_full) == 2
        assert len(p.root) == 2
        check_Path2D(p)


class SplitTest(g.unittest.TestCase):

    def test_split(self):

        for fn in ['2D/ChuteHolderPrint.DXF',
                   '2D/tray-easy1.dxf',
                   '2D/sliding-base.dxf',
                   '2D/wrench.dxf',
                   '2D/spline_1.dxf']:
            p = g.get_mesh(fn)

            # make sure something was loaded
            assert len(p.root) > 0

            # split by connected
            split = p.split()

            # make sure split parts have same area as source
            assert g.np.isclose(p.area, sum(i.area for i in split))
            # make sure concatenation doesn't break that
            assert g.np.isclose(p.area, g.np.sum(split).area)

            # check that cache didn't screw things up
            for s in split:
                assert len(s.root) == 1
                assert len(s.path_valid) == len(s.paths)
                assert len(s.paths) == len(s.discrete)
                assert s.path_valid.sum() == len(s.polygons_closed)
                check_Path2D(s)


class SectionTest(g.unittest.TestCase):

    def test_section(self):
        mesh = g.get_mesh('tube.obj')

        # check the CCW correctness with a normal in both directions
        for sign in [1.0, -1.0]:
            # get a cross section of the tube
            section = mesh.section(plane_origin=mesh.center_mass,
                                   plane_normal=[0.0, sign, 0.0])

            # Path3D -> Path2D
            planar, T = section.to_planar()

            # tube should have one closed polygon
            assert len(planar.polygons_full) == 1
            polygon = planar.polygons_full[0]
            # closed polygon should have one interior
            assert len(polygon.interiors) == 1

            # the exterior SHOULD be counterclockwise
            assert g.trimesh.path.util.is_ccw(
                polygon.exterior.coords)
            # the interior should NOT be counterclockwise
            assert not g.trimesh.path.util.is_ccw(
                polygon.interiors[0].coords)

            # should be a valid Path2D
            check_Path2D(planar)


class CreationTests(g.unittest.TestCase):

    def test_circle(self):
        from trimesh.path import creation
        pattern = creation.circle_pattern(pattern_radius=1.0,
                                          circle_radius=0.1,
                                          count=4)
        assert len(pattern.entities) == 4
        assert len(pattern.polygons_closed) == 4
        assert len(pattern.polygons_full) == 4

        # should be a valid Path2D
        check_Path2D(pattern)

    def test_rect(self):
        from trimesh.path import creation

        # create a single rectangle
        pattern = creation.rectangle([[0, 0], [2, 3]])
        assert len(pattern.entities) == 1
        assert len(pattern.polygons_closed) == 1
        assert len(pattern.polygons_full) == 1
        assert g.np.isclose(pattern.area, 6.0)
        # should be a valid Path2D
        check_Path2D(pattern)

        # make 10 untouching rectangles
        pattern = creation.rectangle(
            g.np.arange(40).reshape((-1, 2, 2)))
        assert len(pattern.entities) == 10
        assert len(pattern.polygons_closed) == 10
        assert len(pattern.polygons_full) == 10
        # should be a valid Path2D
        check_Path2D(pattern)


def check_Path2D(path):
    """
    Make basic assertions on Path2D objects
    """
    # root count should be the same as the closed polygons
    assert len(path.root) == len(path.polygons_full)

    # make sure polygons are really polygons
    assert all(type(i).__name__ == 'Polygon'
               for i in path.polygons_full)
    assert all(type(i).__name__ == 'Polygon'
               for i in path.polygons_closed)

    # these should all correspond to each other
    assert len(path.discrete) == len(path.polygons_closed)
    assert len(path.discrete) == len(path.paths)

    # make sure None polygons are not referenced in graph
    assert all(path.polygons_closed[i] is not None
               for i in path.enclosure_directed.nodes())


if __name__ == '__main__':
    g.trimesh.util.attach_to_log()
    g.unittest.main()
