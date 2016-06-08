import json
from collections import OrderedDict
from os.path import join, dirname
import pandas as pd
import pytest
from fabric.api import local
from mock import MagicMock
from scipy.sparse.csr import csr_matrix
import numpy as np

from sm.engine.db import DB
from sm.engine.search_results import SearchResults, METRICS_INS
from sm.engine.tests.util import spark_context, sm_config, ds_config, create_test_db, drop_test_db

db_mock = MagicMock(spec=DB)


@pytest.fixture
def search_results(spark_context, sm_config, ds_config):
    sf_iso_imgs = spark_context.parallelize([((1, '+H'),
                                            [csr_matrix([[100, 0, 0], [0, 0, 0]]),
                                             csr_matrix([[0, 0, 0], [0, 0, 10]])])])
    sf_metrics_df = pd.DataFrame([(1, '+H', 0.9, 0.9, 0.9, 0.9**3, 0.5)],
                                  columns=['sf_id', 'adduct', 'chaos', 'spatial', 'spectral', 'msm', 'fdr'])
    sf_adduct_peaksn = [(1, '+H', 2)]

    res = SearchResults(0, 0, 0, 'ds_name', sf_adduct_peaksn, db_mock, sm_config, ds_config)
    res.sf_metrics_df = sf_metrics_df
    res.metrics = ['chaos', 'spatial', 'spectral']
    res.sf_iso_images = sf_iso_imgs
    return res


def test_save_sf_img_metrics_correct_db_call(search_results):
    search_results.store_sf_img_metrics()

    metrics_json = json.dumps(OrderedDict(zip(['chaos', 'spatial', 'spectral'], (0.9, 0.9, 0.9))))
    correct_rows = [(0, 0, 1, '+H', 0.9**3, 0.5, metrics_json, 2)]
    db_mock.insert.assert_called_with(METRICS_INS, correct_rows)


@pytest.fixture()
def create_fill_sm_database(create_test_db, drop_test_db, sm_config):
    proj_dir_path = dirname(dirname(__file__))
    local('psql -h localhost -U sm sm_test < {}'.format(join(proj_dir_path, 'scripts/create_schema.sql')))

    db = DB(sm_config['db'])
    try:
        db.insert('INSERT INTO dataset VALUES (%s, %s, %s, %s, %s, %s)',
                  [(0, 'name', 0, 'fpath', json.dumps({}), json.dumps({}))])
        db.insert('INSERT INTO job VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                  [(0, 0, 0, '', 0, 0, None, None)])
    except:
        raise
    finally:
        db.close()


def test_save_sf_iso_images_correct_db_call(spark_context, create_fill_sm_database, sm_config, ds_config):
    sf_iso_imgs = spark_context.parallelize([((1, '+H'),
                                             [csr_matrix([[100, 0, 0], [0, 0, 0]]),
                                              csr_matrix([[0, 0, 0], [0, 0, 10]])])])
    sf_adduct_peaksn = [(1, '+H', 2)]
    res = SearchResults(0, 0, 0, 'ds_name', sf_adduct_peaksn, db_mock, sm_config, ds_config)
    res.sf_iso_images = sf_iso_imgs
    res.nrows, res.ncols = 2, 3
    res.store_sf_iso_images()

    correct_rows = [(0, 0, 1, '+H', 0, [0], [100], 0, 100),
                    (0, 0, 1, '+H', 1, [5], [10], 0, 10)]

    db = DB(sm_config['db'])
    try:
        rows = db.select(('SELECT job_id, db_id, sf_id, adduct, peak, pixel_inds, intensities, min_int, max_int '
                          'FROM iso_image '
                          'ORDER BY sf_id, adduct'))
        assert correct_rows == rows
    finally:
        db.close()


def test_non_native_python_number_types_handled(search_results):
    for col in ['chaos', 'spatial', 'spectral', 'msm', 'fdr']:
        search_results.sf_metrics_df[col] = search_results.sf_metrics_df[col].astype(np.float64)

        search_results.store_sf_img_metrics()

        metrics_json = json.dumps(OrderedDict(zip(['chaos', 'spatial', 'spectral'], (0.9, 0.9, 0.9))))
        correct_rows = [(0, 0, 1, '+H', 0.9 ** 3, 0.5, metrics_json, 2)]
        db_mock.insert.assert_called_with(METRICS_INS, correct_rows)
