# -*- coding: utf8 -*
"""
.. module:: handlers
    :synopsis: Handlers for the webserver.

.. moduleauthor:: Sergey Nikolenko <snikolenko@gmail.com>
"""

from cpyMSpec import IsotopePattern

import json
import threading
import Queue
from datetime import time

import numpy as np

import tornado.ioloop
import tornado.web
import tornado.httpserver
from tornado import gen
from tornado.ioloop import IOLoop


@gen.coroutine
def async_sleep(seconds):
    """Sleep for a given number of seconds."""
    yield gen.Task(IOLoop.instance().add_timeout, time.time() + seconds)


def call_in_background(f, *args):
    """Call function in background in a separate thread / coroutine"""
    result = Queue.Queue(1)
    t = threading.Thread(target=lambda: result.put(f(*args)))
    t.start()
    return result


class IndexHandler(tornado.web.RequestHandler):
    """Tornado handler for the index page."""

    @gen.coroutine
    def get(self):
        self.render("index.html")

def fetch_sigma_charge_ptspermz(db, job_id):
    DS_CONF_SEL = 'SELECT config FROM dataset where id = %s'
    ds_config = db.query(DS_CONF_SEL, job_id)[0]['config']  # job_id for now is equal to ds_id
    iso_gen_config = ds_config['isotope_generation']
    charge = '{}{}'.format(iso_gen_config['charge']['polarity'], iso_gen_config['charge']['n_charges'])
    return iso_gen_config['isocalc_sigma'], charge, iso_gen_config['isocalc_pts_per_mz']


class SFPeakMZsHandler(tornado.web.RequestHandler):
    CENTR_MZS_SEL = '''SELECT centr_mzs
                       FROM theor_peaks
                       WHERE db_id = %s AND sf_id = %s AND adduct = %s AND
                          ROUND(sigma::numeric, 6) = %s AND charge = %s AND pts_per_mz = %s'''

    @property
    def db(self):
        return self.application.db

    @gen.coroutine
    def get(self, job_id, db_id, sf_id, adduct):
        peaks_dict = self.db.query(self.CENTR_MZS_SEL, int(db_id), int(sf_id), adduct,
                                   *fetch_sigma_charge_ptspermz(self.db, job_id))[0]
        centr_mzs = peaks_dict['centr_mzs']
        self.write(json.dumps(centr_mzs))


class MinMaxIntHandler(tornado.web.RequestHandler):
    MIN_MAX_INT_SEL = '''SELECT min_int, max_int
                         FROM iso_image
                         WHERE job_id = %s and db_id = %s and sf_id = %s and adduct = %s;'''

    def get_current_user(self):
        return self.get_secure_cookie('client_id')

    @gen.coroutine
    def get(self, job_id, db_id, sf_id, adduct):
        if self.current_user:
            print 'USER_ID={} tries to access the DB'.format(self.current_user)
        else:
            print 'Not authenticated USER_ID tries to access the DB'
        min_max_rs = self.application.db.query(self.MIN_MAX_INT_SEL, int(job_id), int(db_id), int(sf_id), adduct)
        min_max_dict = min_max_rs[0] if min_max_rs else {'min_int': 0, 'max_int': 0}
        self.write(json.dumps(min_max_dict))


class SpectrumLineChartHandler(tornado.web.RequestHandler):
    PEAK_MZS_SQL = '''SELECT centr_mzs FROM theor_peaks
                          WHERE db_id = %s AND sf_id = %s AND adduct = %s AND
                          ROUND(sigma::numeric, 6) = %s AND charge = %s AND pts_per_mz = %s'''

    SAMPLE_INTENS_SQL = '''SELECT pixel_inds, intensities
                           FROM iso_image
                           WHERE job_id = %s and db_id = %s and sf_id = %s and adduct = %s
                           ORDER by peak'''

    @property
    def db(self):
        return self.application.db

    # TODO: move metric calculation logic to the engine
    @staticmethod
    def sample_centr_ints_norm(sample_ints_list):
        first_peak_inds = set(sample_ints_list[0]['pixel_inds'])
        sample_centr_ints = []
        for peak_d in sample_ints_list:
            peak_int_sum = 0
            first_peak_inds_mask = np.array([i in first_peak_inds for i in peak_d['pixel_inds']])
            if first_peak_inds_mask.size > 0:
                peak_int_sum = np.array(peak_d['intensities'])[first_peak_inds_mask].sum()
            sample_centr_ints.append(peak_int_sum)

        sample_centr_ints = np.asarray(sample_centr_ints)
        return sample_centr_ints / sample_centr_ints.max() * 100

    @gen.coroutine
    def get(self, job_id, db_id, sf_id, adduct):
        params = fetch_sigma_charge_ptspermz(self.db, job_id)
        sigma, charge, pts_per_mz = params

        centr_mzs = self.db.query(self.PEAK_MZS_SQL,
                                  int(db_id), int(sf_id), adduct, *params)[0].centr_mzs
        centr_mzs = np.array(centr_mzs)
        min_mz = min(centr_mzs) - 0.25
        max_mz = max(centr_mzs) + 0.25

        sf = self.db.query("SELECT sf FROM agg_formula WHERE db_id=%s AND id=%s", db_id, sf_id)[0].sf
        isotopes = IsotopePattern(str(sf + adduct)).charged(int(charge))
        fwhm = sigma * 2 * (2 * np.log(2)) ** 0.5
        resolution = isotopes.masses[0] / fwhm
        prof_mzs = np.arange(min_mz, max_mz, 1.0 / pts_per_mz)
        prof_ints = isotopes.envelope(resolution)(prof_mzs)
        nnz_idx = prof_ints > 1e-9
        prof_mzs = prof_mzs[nnz_idx]
        prof_ints = prof_ints[nnz_idx]

        sample_centr_ints_norm = []
        sample_ints_list = self.db.query(self.SAMPLE_INTENS_SQL,
                                         int(job_id), int(db_id), int(sf_id), adduct)
        if sample_ints_list:
            sample_centr_ints_norm = self.sample_centr_ints_norm(sample_ints_list)

        self.write(json.dumps({
            'mz_grid': {
                'min_mz': min_mz,
                'max_mz': max_mz
            },
            'sample': {
                'mzs': centr_mzs.tolist(),
                'ints': list(sample_centr_ints_norm)
            },
            'theor': {
                'mzs': prof_mzs.tolist(),
                'ints': (prof_ints * 100.0).tolist()
            }
        }))
