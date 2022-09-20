import logging
import os
from unittest import TestCase
from unittest.mock import ANY, MagicMock, Mock, call, patch

from osgeo import gdal, ogr

from gdal_utils import (
    convert,
    convert_raster,
    convert_vector,
    get_band_statistics,
    get_dimensions,
    get_distance,
    get_meta,
    is_envelope,
    merge_geotiffs,
    polygonize,
)

logger = logging.getLogger(__name__)


class TestGdalUtils(TestCase):
    def setUp(self):
        self.path = os.path.dirname(os.path.realpath(__file__))

    @patch("gdal_utils.os.path.isfile")
    @patch("gdal_utils.open_dataset")
    def test_get_meta(self, open_dataset_mock, isfile):
        dataset_path = "/path/to/dataset"
        isfile.return_value = True

        mock_open_dataset = Mock(spec=gdal.Dataset)
        mock_open_dataset.RasterCount = 0
        open_dataset_mock.return_value = mock_open_dataset
        mock_open_dataset.GetDriver.return_value.ShortName = "gtiff"
        expected_meta = {
            "driver": "gtiff",
            "is_raster": True,
            "nodata": None,
            "dim": [],
            "srs": None,
        }
        returned_meta = get_meta(dataset_path)
        self.assertEqual(expected_meta, returned_meta)

        mock_open_dataset.RasterCount = 2
        mock_open_dataset.GetRasterBand.return_value.GetNoDataValue.return_value = (
            -32768.0
        )
        expected_dimensions = [200, 300, 1]
        mock_open_dataset.RasterXSize = expected_dimensions[0]
        mock_open_dataset.RasterYSize = expected_dimensions[1]
        expected_meta = {
            "driver": "gtiff",
            "is_raster": True,
            "nodata": -32768.0,
            "dim": expected_dimensions,
            "srs": None,
        }
        returned_meta = get_meta(dataset_path)
        self.assertEqual(expected_meta, returned_meta)

        mock_open_dataset = Mock(spec=ogr.DataSource)
        open_dataset_mock.return_value = mock_open_dataset
        mock_open_dataset.GetDriver.return_value.GetName.return_value = "gpkg"
        expected_meta = {
            "driver": "gpkg",
            "is_raster": False,
            "nodata": None,
            "dim": [],
            "srs": None,
        }
        returned_meta = get_meta(dataset_path)
        self.assertEqual(expected_meta, returned_meta)

        open_dataset_mock.return_value = None
        expected_meta = {
            "driver": None,
            "is_raster": None,
            "nodata": None,
            "dim": [],
            "srs": None,
        }
        returned_meta = get_meta(dataset_path)
        self.assertEqual(expected_meta, returned_meta)

    def test_is_envelope(self):
        envelope_gj = """{"type": "MultiPolygon",
            "coordinates": [ [
                [   [0,0],
                    [1,0],
                    [1,1],
                    [0,1],
                    [0,0]
                ]
            ] ]
        }"""
        triangle_gj = """{"type": "MultiPolygon",
            "coordinates": [ [
                [   [0,0],
                    [1,0],
                    [0,1],
                    [0,0]
                ]
            ] ]
        }"""
        non_env_gj = """{"type": "MultiPolygon",
            "coordinates": [ [
                [   [0,0],
                    [1.5,0],
                    [1,1],
                    [0,1],
                    [0,0]
                ]
            ] ]
        }"""
        empty_gj = ""

        self.assertTrue(is_envelope(envelope_gj))
        self.assertFalse(is_envelope(triangle_gj))
        self.assertFalse(is_envelope(non_env_gj))
        self.assertFalse(is_envelope(empty_gj))

    @patch("gdal_utils.get_task_command")
    @patch("gdal_utils.is_envelope")
    @patch("gdal_utils.get_meta")
    @patch("gdal_utils.os.path.isfile")
    def test_convert(
        self, isfile, get_meta_mock, is_envelope_mock, get_task_command_mock
    ):
        isfile.return_value = True

        with self.assertRaises(Exception):
            convert(input_files=None)

        # Raster geopackage
        in_projection = "EPSG:4326"
        out_projection = "EPSG:3857"
        geojson_file = "/path/to/geojson"
        reproj_geojson_file = "/path/to/geojson-aoi.gpkg"
        out_dataset = "/path/to/dataset"
        in_dataset = "/path/to/old_dataset"
        driver = "gpkg"
        band_type = gdal.GDT_Byte
        dstalpha = True
        lambda_mock = MagicMock()
        get_task_command_mock.return_value = lambda_mock
        get_meta_mock.return_value = {
            "driver": "gpkg",
            "is_raster": True,
            "nodata": None,
            "srs": 4326,
        }
        is_envelope_mock.return_value = False
        convert(
            boundary=geojson_file,
            input_files=[in_dataset],
            output_file=out_dataset,
            driver=driver,
            projection=3857,
        )
        get_task_command_mock.assert_called_once_with(
            convert_raster,
            [in_dataset],
            out_dataset,
            driver=driver,
            config_options=None,
            creation_options=None,
            band_type=band_type,
            dst_alpha=dstalpha,
            boundary=geojson_file,
            src_srs=None,
            dst_srs=out_projection,
            translate_params=None,
            warp_params=None,
            use_translate=False,
        )
        get_task_command_mock.reset_mock()

        # Geotiff
        driver = "gtiff"
        band_type = None
        dstalpha = True
        get_meta_mock.return_value = {
            "driver": "gtiff",
            "is_raster": True,
            "nodata": None,
            "srs": 4326,
        }
        is_envelope_mock.return_value = True  # So, no need for -dstalpha
        convert(
            boundary=geojson_file,
            input_files=[in_dataset],
            output_file=out_dataset,
            driver=driver,
        )
        get_task_command_mock.assert_called_once_with(
            convert_raster,
            [in_dataset],
            out_dataset,
            driver=driver,
            config_options=None,
            creation_options=None,
            band_type=band_type,
            dst_alpha=dstalpha,
            boundary=geojson_file,
            src_srs=None,
            dst_srs=in_projection,
            translate_params=None,
            warp_params=None,
            use_translate=False,
        )
        get_task_command_mock.reset_mock()

        # Geotiff with non-envelope polygon cutline
        is_envelope_mock.return_value = False
        dstalpha = True
        convert(
            boundary=geojson_file,
            input_files=[in_dataset],
            output_file=out_dataset,
            driver=driver,
        )
        get_task_command_mock.assert_called_once_with(
            convert_raster,
            [in_dataset],
            out_dataset,
            driver=driver,
            config_options=None,
            creation_options=None,
            band_type=band_type,
            dst_alpha=dstalpha,
            boundary=geojson_file,
            src_srs=None,
            dst_srs=in_projection,
            translate_params=None,
            warp_params=None,
            use_translate=False,
        )
        get_task_command_mock.reset_mock()

        # Vector
        driver = "gpkg"
        get_meta_mock.return_value = {"driver": "gpkg", "is_raster": False}
        convert(
            boundary=geojson_file,
            input_files=[in_dataset],
            output_file=out_dataset,
            driver=driver,
        )
        get_task_command_mock.has_calls(
            [
                call(
                    convert_vector,
                    [in_dataset],
                    out_dataset,
                    driver=driver,
                    config_options=None,
                    dataset_creation_options=None,
                    layer_creation_options=None,
                    src_srs=None,
                    dst_srs=in_projection,
                    layers=None,
                    layer_name=None,
                    access_mode="overwrite",
                    boundary=geojson_file,
                    bbox=None,
                    distinct_field=None,
                ),
                call(
                    convert_vector,
                    [geojson_file],
                    reproj_geojson_file,
                    driver=driver,
                    config_options=None,
                    dataset_creation_options=None,
                    layer_creation_options=None,
                    src_srs=None,
                    dst_srs=in_projection,
                    layers=None,
                    layer_name=None,
                    access_mode="overwrite",
                    boundary=geojson_file,
                    bbox=None,
                    distinct_field=None,
                ),
            ]
        )
        get_task_command_mock.reset_mock()

        # Test that extra_parameters are added when converting to NITF.
        driver = "nitf"
        extra_parameters = ["-co ICORDS=G"]
        in_projection = "EPSG:4326"
        out_projection = "EPSG:3857"
        band_type = None
        dstalpha = True
        get_meta_mock.return_value = {"driver": "gpkg", "is_raster": True}
        convert(
            driver=driver,
            input_files=[in_dataset],
            creation_options=extra_parameters,
            output_file=out_dataset,
            src_srs=4326,
            projection=3857,
        )
        get_task_command_mock.assert_called_once_with(
            convert_raster,
            [in_dataset],
            out_dataset,
            driver=driver,
            config_options=None,
            creation_options=extra_parameters,
            band_type=band_type,
            dst_alpha=dstalpha,
            boundary=None,
            src_srs=in_projection,
            dst_srs=out_projection,
            translate_params=None,
            warp_params=None,
            use_translate=False,
        )
        get_task_command_mock.reset_mock()

        # Test converting to a new projection
        driver = "gpkg"
        out_projection = "EPSG:3857"
        band_type = gdal.GDT_Byte
        dstalpha = True
        get_meta_mock.return_value = {"driver": "gpkg", "is_raster": True}
        convert(
            driver=driver,
            input_files=[in_dataset],
            output_file=out_dataset,
            projection=3857,
        )
        get_task_command_mock.assert_called_once_with(
            convert_raster,
            [in_dataset],
            out_dataset,
            driver=driver,
            config_options=None,
            creation_options=None,
            band_type=band_type,
            dst_alpha=dstalpha,
            boundary=None,
            src_srs=None,
            dst_srs=out_projection,
            translate_params=None,
            warp_params=None,
            use_translate=False,
        )
        get_task_command_mock.reset_mock()

    @patch("gdal_utils.ogr")
    @patch("gdal_utils.gdal")
    def test_polygonize(self, mock_gdal, mock_ogr):
        example_input = "input.tif"
        example_output = "output.geojson"
        dst_layer = Mock()
        mask_band = Mock()
        mock_ogr.GetDriverByName().CreateDataSource().CreateLayer.return_value = (
            dst_layer
        )
        mock_dataset = MagicMock()
        mock_dataset.RasterCount = 4
        mock_gdal.Open.return_value = mock_dataset
        mock_dataset.GetRasterBand.return_value = mask_band
        polygonize(example_input, example_output)
        expected_band = 4
        mock_dataset.GetRasterBand.assert_called_once_with(expected_band)
        mock_gdal.Polygonize.assert_called_once_with(
            mask_band, mask_band, dst_layer, -1, []
        )
        mock_gdal.Open.assert_called_once_with(example_input)
        mock_ogr.GetDriverByName.assert_called_with("GeoJSON")
        mock_ogr.GetDriverByName().CreateDataSource.assert_called_with(example_output)
        mock_ogr.GetDriverByName().CreateDataSource().CreateLayer.assert_called_with(
            example_output
        )
        mock_dataset.GetRasterBand.reset_mock()

        mock_dataset.RasterCount = 3
        mock_gdal.Open.return_value = mock_dataset
        polygonize(example_input, example_output)
        expected_band = 4
        mock_gdal.Nearblack.assert_called_once_with(ANY, example_input)
        mock_dataset.GetRasterBand.assert_called_once_with(expected_band)
        mock_dataset.GetRasterBand.reset_mock()

        mock_dataset.RasterCount = 2
        mock_gdal.Open.return_value = mock_dataset
        polygonize(example_input, example_output)
        expected_band = 2
        mock_dataset.GetRasterBand.assert_called_once_with(expected_band)
        mock_dataset.GetRasterBand.reset_mock()

        mock_dataset.RasterCount = 1
        mock_gdal.Open.return_value = mock_dataset
        polygonize(example_input, example_output)
        expected_band = 1
        mock_dataset.GetRasterBand.assert_called_once_with(expected_band)
        mock_dataset.GetRasterBand.reset_mock()

    def test_get_distance(self):
        expected_distance = 972.38
        point_a = [-72.377162, 42.218109]
        point_b = [-72.368493, 42.218903]
        distance = get_distance(point_a, point_b)
        self.assertEqual(int(expected_distance), int(distance))

    @patch("gdal_utils.get_distance")
    def test_get_dimensions(self, mock_get_distance):
        bbox = [0.0, 1.0, 2.0, 3.0]
        scale = 10
        expected_dim = (10, 20)
        mock_get_distance.side_effect = [100, 200]
        dim = get_dimensions(bbox, scale)
        mock_get_distance.assert_has_calls(
            [
                call([bbox[0], bbox[1]], [bbox[2], bbox[1]]),
                call([bbox[0], bbox[1]], [bbox[0], bbox[3]]),
            ]
        )
        self.assertEqual(dim, expected_dim)

        expected_dim = (1, 1)
        mock_get_distance.side_effect = [6, 8]
        dim = get_dimensions(bbox, scale)
        self.assertEqual(dim, expected_dim)

        expected_dim = (1, 5)
        mock_get_distance.side_effect = [9, 50]
        dim = get_dimensions(bbox, scale)
        self.assertEqual(dim, expected_dim)

        expected_dim = (6, 1)
        mock_get_distance.side_effect = [60, 8]
        dim = get_dimensions(bbox, scale)
        self.assertEqual(dim, expected_dim)

    @patch("gdal_utils.get_task_command")
    def test_merge_geotiffs(self, get_task_command_mock):
        in_files = ["1.tif", "2.tif", "3.tif", "4.tif"]
        out_file = "merged.tif"
        lambda_mock = Mock()
        get_task_command_mock.return_value = lambda_mock
        merge_geotiffs(in_files, out_file)
        get_task_command_mock.assert_called_once_with(
            convert_raster, in_files, out_file, driver="gtiff"
        )

    @patch("gdal_utils.gdal")
    def test_get_band_statistics(self, mock_gdal):
        in_file = "test.tif"
        example_stats = [0, 10, 5, 2]
        mock_gdal.Open.return_value.GetRasterBand.return_value.GetStatistics.return_value = (
            example_stats
        )
        returned_stats = get_band_statistics(in_file)
        self.assertEqual(example_stats, returned_stats)
        mock_gdal.Open.assert_called_once_with(in_file)

        mock_gdal.Open.return_value.GetRasterBand.return_value.GetStatistics.side_effect = [
            Exception
        ]
        self.assertIsNone(get_band_statistics(in_file))

    @patch("gdal_utils.os.path.isfile")
    @patch("gdal_utils.get_meta")
    @patch("gdal_utils.get_dataset_names")
    @patch("gdal_utils.gdal")
    def test_convert_raster(
        self, mock_gdal, mock_get_dataset_names, mock_get_meta, mock_isfile
    ):
        input_file = "/test/test.gpkg"
        output_file = "/test/test.tif"
        boundary = "/test/test.json"
        driver = "gtiff"
        srs = "EPSG:4326"
        mock_isfile.return_value = True
        mock_get_meta.return_value = {
            "driver": "gtiff",
            "is_raster": True,
            "nodata": None,
            "dim": [50, 50, 1],
            "srs": 4326,
        }
        mock_get_dataset_names.return_value = (input_file, output_file)
        convert_raster(
            input_file,
            output_file,
            driver=driver,
            boundary=boundary,
            src_srs=srs,
            dst_srs=srs,
        )
        mock_get_meta.assert_called_once_with(input_file)
        mock_gdal.Warp.assert_called_once_with(
            output_file,
            [input_file],
            dstSRS=srs,
            format=driver,
            srcSRS=srs,
        )
        mock_gdal.Translate.assert_called_once_with(
            output_file,
            input_file,
            format=driver,
            creationOptions=["COMPRESS=LZW", "TILED=YES", "BIGTIFF=YES"],
        )
        mock_gdal.reset_mock()
        warp_params = {"warp": "params"}
        translate_params = {"translate": "params"}
        mock_get_meta.return_value = {"dim": [200, 200, 1]}
        convert_raster(
            input_file,
            output_file,
            driver=driver,
            boundary=boundary,
            src_srs=srs,
            dst_srs=srs,
            warp_params=warp_params,
            translate_params=translate_params,
        )
        mock_gdal.Warp.assert_called_once_with(
            output_file,
            [input_file],
            cropToCutline=True,
            cutlineDSName=boundary,
            format=driver,
            warp="params",
        )
        mock_gdal.Translate.assert_called_once_with(
            output_file,
            input_file,
            format=driver,
            translate="params",
        )

    @patch("gdal_utils.gdal")
    def test_convert_vector(self, mock_gdal):
        input_file = "/test/test.gpkg"
        output_file = "/test/test.kml"
        boundary = "/test/test.json"
        driver = "kml"
        src_srs = "EPSG:4326"
        dst_srs = "EPSG:3857"

        convert_vector(
            input_file,
            output_file,
            driver=driver,
            boundary=boundary,
            src_srs=src_srs,
            dst_srs=dst_srs,
        )
        mock_gdal.VectorTranslate.assert_called_once_with(
            output_file,
            input_file,
            accessMode="overwrite",
            dstSRS=dst_srs,
            format=driver,
            options=["-clipSrc", boundary],
            reproject=True,
            skipFailures=False,
            srcSRS=src_srs,
        )
