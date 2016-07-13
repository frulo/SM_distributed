from os.path import join
import pytest
from fabric.api import local
from pyspark import SparkContext, SparkConf

from sm.engine.db import DB
from sm.engine.util import proj_root


@pytest.fixture(scope='module')
def spark_context(request):
    sc = SparkContext(master='local[2]', conf=SparkConf())

    def fin():
        sc.stop()
    request.addfinalizer(fin)

    return sc


@pytest.fixture()
def create_test_db():
    db_config = dict(database='postgres', user='sm', host='localhost')
    db = DB(db_config, autocommit=True)
    db.alter('DROP DATABASE IF EXISTS sm_test')
    db.alter('CREATE DATABASE sm_test')
    db.close()

    local('psql -h localhost -U sm sm_test < {}'.format(join(proj_root(), 'scripts/create_schema.sql')))


@pytest.fixture()
def drop_test_db(request):
    def fin():
        db_config = dict(database='postgres', user='sm', host='localhost', password='1321')
        db = DB(db_config, autocommit=True)
        db.alter('DROP DATABASE IF EXISTS sm_test')
        db.close()
    request.addfinalizer(fin)


@pytest.fixture()
def ds_config():
    return {
        "database": {
            "name": "HMDB",
        },
        "isotope_generation": {
            "adducts": ["+H", "+Na"],
            "charge": {
                "polarity": "+",
                "n_charges": 1
            },
            "isocalc_sigma": 0.01,
            "isocalc_pts_per_mz": 10000
        },
        "image_generation": {
            "ppm": 1.0,
            "nlevels": 30,
            "q": 99,
            "do_preprocessing": False
        }
    }


@pytest.fixture()
def sm_config():
    return {
        "db": {
            "host": "localhost",
            "database": "sm_test",
            "user": "sm",
            "password": "1321"
        },
        "elasticsearch": {
            "host": "localhost"
        },
        "fs": {
            "base_path": "/opt/data/sm_test_data",
            "s3_base_path": ""
        },
        "spark": {
            "master": "local[2]",
            "executor.memory": "1g"
        }
    }
