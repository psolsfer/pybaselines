# -*- coding: utf-8 -*-
"""Tests for pybaselines.splines.

@author: Donald Erb
Created on March 20, 2021

"""

from unittest import mock

import numpy as np
from numpy.testing import assert_allclose, assert_array_equal
import pytest

from pybaselines import _banded_utils, spline, utils, whittaker

from .conftest import BaseTester, InputWeightsMixin


@pytest.mark.parametrize('use_numba', (True, False))
def test_mapped_histogram_simple(use_numba):
    """Compares the output with numpy and the bin_mapping, testing corner cases."""
    num_bins = 10
    values = np.array([0, 0.01, 1, 1.5, 8, 9, 9.1, 10])
    expected_bin_edges = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    expected_bin_mapping = np.array([0, 0, 1, 1, 8, 9, 9, 9], dtype=np.intp)

    np_histogram, np_bin_edges = np.histogram(values, num_bins, density=True)
    assert_allclose(np_bin_edges, expected_bin_edges, rtol=0, atol=1e-12)

    with mock.patch.object(spline, '_HAS_NUMBA', use_numba):
        histogram, bin_edges, bin_mapping = spline._mapped_histogram(values, num_bins)

    assert_allclose(histogram, np_histogram)
    assert_allclose(bin_edges, np_bin_edges)
    assert_array_equal(bin_mapping, expected_bin_mapping)


@pytest.mark.parametrize('rng_seed', (0, 1))
@pytest.mark.parametrize('num_bins', (10, 100, 1000))
@pytest.mark.parametrize('use_numba', (True, False))
def test_mapped_histogram(rng_seed, num_bins, use_numba):
    """Compares the output with numpy and the bin_mapping with a nieve version."""
    # TODO replace with np.random.default_rng when min numpy version is >= 1.17
    rng = np.random.RandomState(rng_seed)
    values = rng.normal(0, 20, 1000)
    np_histogram, np_bin_edges = np.histogram(values, num_bins, density=True)
    with mock.patch.object(spline, '_HAS_NUMBA', use_numba):
        histogram, bin_edges, bin_mapping = spline._mapped_histogram(values, num_bins)

    assert_allclose(histogram, np_histogram)
    assert_allclose(bin_edges, np_bin_edges)

    expected_bin_mapping = np.zeros_like(values)
    for i, left_bin in enumerate(bin_edges[:-1]):
        mask = (values >= left_bin) & (values < bin_edges[i + 1])
        expected_bin_mapping[mask] = i
    expected_bin_mapping[values >= bin_edges[-1]] = num_bins - 1

    assert_array_equal(bin_mapping, expected_bin_mapping)


@pytest.mark.parametrize('fraction_pos', (0, 0.4))
@pytest.mark.parametrize('fraction_neg', (0, 0.3))
def test_mixture_pdf(fraction_pos, fraction_neg):
    """Ensures the probability density function for the Gaussian-uniform mixture model is right."""
    x = np.linspace(-5, 10, 1000)
    actual_sigma = 0.5
    sigma = np.log10(actual_sigma)
    # the gaussian should be area-normalized, so set height accordingly
    height = 1 / (actual_sigma * np.sqrt(2 * np.pi))
    expected_gaussian = utils.gaussian(x, height, 0, actual_sigma)

    fraction_gaus = 1 - fraction_pos - fraction_neg
    if fraction_pos > 0:
        pos_uniform = np.zeros_like(x)
        pos_uniform[x >= 0] = 1 / abs(x.max())
    elif fraction_neg > 0:
        pos_uniform = None
    else:
        pos_uniform = 0

    if fraction_neg > 0:
        neg_uniform = np.zeros_like(x)
        neg_uniform[x <= 0] = 1 / abs(x.min())
    elif fraction_pos > 0:
        neg_uniform = None
    else:
        neg_uniform = 0

    output_pdf = spline._mixture_pdf(
        x, fraction_gaus, sigma, fraction_pos, pos_uniform, neg_uniform
    )

    # now ensure neg_uniform and pos_uniform are not None
    if pos_uniform is None:
        pos_uniform = 0
    if neg_uniform is None:
        neg_uniform = 0

    expected_pdf = (
        fraction_gaus * expected_gaussian
        + fraction_pos * pos_uniform
        + fraction_neg * neg_uniform
    )

    assert_allclose(expected_pdf, output_pdf, 1e-12, 1e-12)
    # ensure pdf has an area of 1, ie total probability is 100%; accuracy is limited
    # by number of x-values
    assert_allclose(1.0, np.trapz(output_pdf, x), 1e-3)


def compare_pspline_whittaker(pspline_class, whittaker_func, data, lam=1e5,
                              test_rtol=1e-6, test_atol=1e-12, **kwargs):
    """
    Compares the output of the penalized spline (P-spline) versions of Whittaker functions.

    The number of knots for the P-splines are set to ``len(data) + 1`` and the spline
    degree is set to 0; the result is that the spline basis becomes the identity matrix,
    and the P-spline version should give the same output as the Whittaker version if
    the weighting and linear systems were correctly set up.

    """
    # ensure the Whittaker functions use Scipy since that is what P-splines use
    with mock.patch.object(_banded_utils, '_HAS_PENTAPY', False):
        whittaker_output = whittaker_func(data, lam=lam, **kwargs)[0]

    if hasattr(pspline_class, 'class_func'):
        spline_output = pspline_class.class_func(
            data, lam=lam, num_knots=len(data) + 1, spline_degree=0, **kwargs
        )[0]
    else:
        spline_output = pspline_class._call_func(
            data, lam=lam, num_knots=len(data) + 1, spline_degree=0, **kwargs
        )[0]

    assert_allclose(spline_output, whittaker_output, rtol=test_rtol, atol=test_atol)


class SplineTester(BaseTester):
    """Base testing class for spline functions."""

    module = spline
    algorithm_base = spline._Spline


class IterativeSplineTester(SplineTester, InputWeightsMixin):
    """Base testing class for iterative spline functions."""

    checked_keys = ('weights', 'tol_history')

    def test_tol_history(self):
        """Ensures the 'tol_history' item in the parameter output is correct."""
        max_iter = 5
        _, params = self.class_func(self.y, max_iter=max_iter, tol=-1)

        assert params['tol_history'].size == max_iter + 1


class TestMixtureModel(IterativeSplineTester):
    """Class for testing mixture_model baseline."""

    func_name = 'mixture_model'

    @pytest.mark.parametrize('use_class', (True, False))
    @pytest.mark.parametrize('weight_bool', (True, False))
    def test_unchanged_data(self, use_class, weight_bool):
        """Ensures that input data is unchanged by the function."""
        if weight_bool:
            weights = np.ones_like(self.y)
        else:
            weights = None
        super().test_unchanged_data(use_class, weights=weights)

    @pytest.mark.parametrize('symmetric', (False, True))
    def test_output(self, symmetric):
        """Ensures that the output has the desired format."""
        initial_y = self.y
        try:
            if symmetric:
                # make data with both positive and negative peaks; roll so peaks are not overlapping
                self.y = np.roll(self.y, -50) - np.roll(self.y, 50)
                p = 0.5
            else:
                p = 0.01
            super().test_output(p=p, symmetric=symmetric)
        finally:
            self.y = initial_y

    @pytest.mark.parametrize('p', (-1, 2))
    def test_outside_p_fails(self, p):
        """Ensures p values outside of [0, 1] raise an exception."""
        with pytest.raises(ValueError):
            self.class_func(self.y, p=p)

    @pytest.mark.parametrize('diff_order', (1, 2, 3))
    def test_diff_orders(self, diff_order):
        """Ensure that other difference orders work."""
        lam = {1: 1e2, 2: 1e5, 3: 1e8}[diff_order]
        self.class_func(self.y, lam=lam, diff_order=diff_order)


class TestIRSQR(IterativeSplineTester):
    """Class for testing irsqr baseline."""

    func_name = 'irsqr'

    @pytest.mark.parametrize('quantile', (-1, 2))
    def test_outside_p_fails(self, quantile):
        """Ensures quantile values outside of [0, 1] raise an exception."""
        with pytest.raises(ValueError):
            self.class_func(self.y, quantile=quantile)

    @pytest.mark.parametrize('diff_order', (1, 2, 3))
    def test_diff_orders(self, diff_order):
        """Ensure that other difference orders work."""
        lam = {1: 1e2, 2: 1e5, 3: 1e8}[diff_order]
        self.class_func(self.y, lam=lam, diff_order=diff_order)


class TestCornerCutting(SplineTester):
    """
    Class for testing corner_cutting baseline.

    Has lower tolerance values for some tests since it is not currently perfectly repeatable.

    """

    func_name = 'corner_cutting'

    def test_no_x(self):
        """Ensures that function output is similar when no x is input."""
        super().test_no_x(rtol=1e-3)

    def test_list_input(self):
        """Ensures that function works the same for both array and list inputs."""
        super().test_list_input(rtol=1e-5)


class TestPsplineAsLS(IterativeSplineTester):
    """Class for testing pspline_asls baseline."""

    func_name = 'pspline_asls'

    @pytest.mark.parametrize('p', (-1, 2))
    def test_outside_p_fails(self, p):
        """Ensures p values outside of [0, 1] raise an exception."""
        with pytest.raises(ValueError):
            self.class_func(self.y, p=p)

    @pytest.mark.parametrize('diff_order', (1, 3))
    def test_diff_orders(self, diff_order):
        """Ensure that other difference orders work."""
        lam = {1: 1e2, 3: 1e10}[diff_order]
        self.class_func(self.y, lam=lam, diff_order=diff_order)

    @pytest.mark.parametrize('lam', (1e1, 1e5))
    @pytest.mark.parametrize('p', (0.01, 0.1))
    def test_whittaker_comparison(self, lam, p):
        """Ensures the P-spline version is the same as the Whittaker version."""
        compare_pspline_whittaker(self, whittaker.asls, self.y, lam=lam, p=p)


class TestPsplineIAsLS(IterativeSplineTester):
    """Class for testing pspline_iasls baseline."""

    func_name = 'pspline_iasls'

    @pytest.mark.parametrize('use_class', (True, False))
    @pytest.mark.parametrize('weight_bool', (True, False))
    def test_unchanged_data(self, use_class, weight_bool):
        """Ensures that input data is unchanged by the function."""
        if weight_bool:
            weights = np.ones_like(self.y)
        else:
            weights = None
        super().test_unchanged_data(use_class, weights=weights)

    @pytest.mark.parametrize('p', (-1, 2))
    def test_outside_p_fails(self, p):
        """Ensures p values outside of [0, 1] raise an exception."""
        with pytest.raises(ValueError):
            self.class_func(self.y, p=p)

    @pytest.mark.parametrize('lam', (1e1, 1e5))
    @pytest.mark.parametrize('p', (0.01, 0.1))
    def test_whittaker_comparison(self, lam, p):
        """Ensures the P-spline version is the same as the Whittaker version."""
        compare_pspline_whittaker(self, whittaker.iasls, self.y, lam=lam, p=p)


class TestPsplineAirPLS(IterativeSplineTester):
    """Class for testing pspline_airpls baseline."""

    func_name = 'pspline_airpls'

    @pytest.mark.parametrize('diff_order', (1, 3))
    def test_diff_orders(self, diff_order):
        """Ensure that other difference orders work."""
        lam = {1: 1e3, 3: 1e10}[diff_order]
        self.class_func(self.y, lam=lam, diff_order=diff_order)

    # ignore the RuntimeWarning that occurs from using +/- inf or nan
    @pytest.mark.filterwarnings('ignore::RuntimeWarning')
    def test_avoid_nonfinite_weights(self, no_noise_data_fixture):
        """
        Ensures that the function gracefully exits when errors occur.

        When there are no negative residuals, which occurs when a low tol value is used with
        a high max_iter value, the weighting function would produce values all ~0, which
        can fail the solvers. The returned baseline should be the last iteration that was
        successful, and thus should not contain nan or +/- inf.

        Use data without noise since the lack of noise makes it easier to induce failure.
        Set tol to -1 so that it is never reached, and set max_iter to a high value.
        Uses np.isfinite on the dot product of the baseline since the dot product is fast,
        would propogate the nan or inf, and will create only a single value to check
        for finite-ness.

        """
        y, x = no_noise_data_fixture
        with pytest.warns(utils.ParameterWarning):
            baseline = self.class_func(y, tol=-1, max_iter=7000)[0]
        assert np.isfinite(baseline.dot(baseline))

    @pytest.mark.parametrize('lam', (1e1, 1e5))
    def test_whittaker_comparison(self, lam):
        """Ensures the P-spline version is the same as the Whittaker version."""
        compare_pspline_whittaker(self, whittaker.airpls, self.y, lam=lam)


class TestPsplineArPLS(IterativeSplineTester):
    """Class for testing pspline_arpls baseline."""

    func_name = 'pspline_arpls'

    @pytest.mark.parametrize('diff_order', (1, 3))
    def test_diff_orders(self, diff_order):
        """Ensure that other difference orders work."""
        lam = {1: 1e2, 3: 1e10}[diff_order]
        self.class_func(self.y, lam=lam, diff_order=diff_order)

    @pytest.mark.skip(reason='need to decide how to handle arpls weighting for no negatives')
    def test_avoid_overflow_warning(self, no_noise_data_fixture):
        """
        Ensures no warning is emitted for exponential overflow.

        The weighting is 1 / (1 + exp(values)), so if values is too high,
        exp(values) is inf, which should usually emit an overflow warning.
        However, the resulting weight is 0, which is fine, so the warning is
        not needed and should be avoided. This test ensures the overflow warning
        is not emitted, and also ensures that the output is all finite, just in
        case the weighting was not actually stable.

        """
        y, x = no_noise_data_fixture
        with np.errstate(over='raise'):
            baseline = self.class_func(y, tol=-1, max_iter=1000)[0]

        assert np.isfinite(baseline.dot(baseline))

    @pytest.mark.parametrize('lam', (1e1, 1e5))
    def test_whittaker_comparison(self, lam):
        """Ensures the P-spline version is the same as the Whittaker version."""
        compare_pspline_whittaker(self, whittaker.arpls, self.y, lam=lam)


class TestPsplineDrPLS(IterativeSplineTester):
    """Class for testing pspline_drpls baseline."""

    func_name = 'pspline_drpls'

    @pytest.mark.parametrize('diff_order', (2, 3))
    def test_diff_orders(self, diff_order):
        """Ensure that other difference orders work."""
        lam = {2: 1e6, 3: 1e10}[diff_order]
        self.class_func(self.y, lam=lam, diff_order=diff_order)

    # ignore the RuntimeWarning that occurs from using +/- inf or nan
    @pytest.mark.filterwarnings('ignore::RuntimeWarning')
    def test_avoid_nonfinite_weights(self, no_noise_data_fixture):
        """
        Ensures that the function gracefully exits when non-finite weights are created.

        When there are no negative residuals or exp(iterations) / std is very high, both
        of which occur when a low tol value is used with a high max_iter value, the
        weighting function would produce non-finite values. The returned baseline should
        be the last iteration that was successful, and thus should not contain nan or +/- inf.

        Use data without noise since the lack of noise makes it easier to induce failure.
        Set tol to -1 so that it is never reached, and set max_iter to a high value.
        Uses np.isfinite on the dot product of the baseline since the dot product is fast,
        would propogate the nan or inf, and will create only a single value to check
        for finite-ness.

        """
        y, x = no_noise_data_fixture
        with pytest.warns(utils.ParameterWarning):
            baseline, params = self.class_func(y, tol=-1, max_iter=1000)

        assert np.isfinite(baseline.dot(baseline))
        # ensure last tolerence calculation was non-finite as a double-check that
        # this test is actually doing what it should be doing
        assert not np.isfinite(params['tol_history'][-1])

    @pytest.mark.parametrize('lam', (1e1, 1e5))
    @pytest.mark.parametrize('eta', (0.2, 0.8))
    def test_whittaker_comparison(self, lam, eta):
        """
        Ensures the P-spline version is the same as the Whittaker version.

        Have to use a larger tolerance since pspline_drpls uses interpolation to
        get the weight at the coefficients' x-values.
        """
        compare_pspline_whittaker(self, whittaker.drpls, self.y, lam=lam, eta=eta, test_rtol=2e-3)

    @pytest.mark.parametrize('eta', (-1, 2))
    def test_outside_eta_fails(self, eta):
        """Ensures eta values outside of [0, 1] raise an exception."""
        with pytest.raises(ValueError):
            self.class_func(self.y, eta=eta)


class TestPsplineIArPLS(IterativeSplineTester):
    """Class for testing pspline_iarpls baseline."""

    func_name = 'pspline_iarpls'

    @pytest.mark.parametrize('diff_order', (1, 3))
    def test_diff_orders(self, diff_order):
        """Ensure that other difference orders work."""
        lam = {1: 1e2, 3: 1e10}[diff_order]
        self.class_func(self.y, lam=lam, diff_order=diff_order)

    # ignore the RuntimeWarning that occurs from using +/- inf or nan
    @pytest.mark.filterwarnings('ignore::RuntimeWarning')
    def test_avoid_nonfinite_weights(self, no_noise_data_fixture):
        """
        Ensures that the function gracefully exits when non-finite weights are created.

        When there are no negative residuals or exp(iterations) / std is very high, both
        of which occur when a low tol value is used with a high max_iter value, the
        weighting function would produce non-finite values. The returned baseline should
        be the last iteration that was successful, and thus should not contain nan or +/- inf.

        Use data without noise since the lack of noise makes it easier to induce failure.
        Set tol to -1 so that it is never reached, and set max_iter to a high value.
        Uses np.isfinite on the dot product of the baseline since the dot product is fast,
        would propogate the nan or inf, and will create only a single value to check
        for finite-ness.

        """
        y, x = no_noise_data_fixture
        with pytest.warns(utils.ParameterWarning):
            baseline, params = self.class_func(y, tol=-1, max_iter=1000)

        assert np.isfinite(baseline.dot(baseline))
        # ensure last tolerence calculation was non-finite as a double-check that
        # this test is actually doing what it should be doing
        assert not np.isfinite(params['tol_history'][-1])

    @pytest.mark.parametrize('lam', (1e1, 1e5))
    def test_whittaker_comparison(self, lam):
        """Ensures the P-spline version is the same as the Whittaker version."""
        compare_pspline_whittaker(self, whittaker.iarpls, self.y, lam=lam)


class TestPsplineAsPLS(IterativeSplineTester):
    """Class for testing pspline_aspls baseline."""

    func_name = 'pspline_aspls'
    checked_keys = ('weights', 'tol_history', 'alpha')
    weight_keys = ('weights', 'alpha')

    def test_wrong_alpha_shape(self):
        """Ensures that an exception is raised if input alpha and data are different shapes."""
        alpha = np.ones(self.y.shape[0] + 1)
        with pytest.raises(ValueError):
            self.class_func(self.y, alpha=alpha)

    @pytest.mark.parametrize('diff_order', (1, 3))
    def test_diff_orders(self, diff_order):
        """Ensure that other difference orders work."""
        lam = {1: 1e4, 3: 1e10}[diff_order]
        self.class_func(self.y, lam=lam, diff_order=diff_order)

    def test_avoid_overflow_warning(self, no_noise_data_fixture):
        """
        Ensures no warning is emitted for exponential overflow.

        The weighting is 1 / (1 + exp(values)), so if values is too high,
        exp(values) is inf, which should usually emit an overflow warning.
        However, the resulting weight is 0, which is fine, so the warning is
        not needed and should be avoided. This test ensures the overflow warning
        is not emitted, and also ensures that the output is all finite, just in
        case the weighting was not actually stable.

        """
        y, x = no_noise_data_fixture
        with np.errstate(over='raise'):
            baseline = self.class_func(y, tol=-1, max_iter=1000)[0]

        assert np.isfinite(baseline.dot(baseline))

    @pytest.mark.parametrize('lam', (1e1, 1e5))
    def test_whittaker_comparison(self, lam):
        """
        Ensures the P-spline version is the same as the Whittaker version.

        Have to use a larger tolerance since pspline_aspls uses interpolation to
        get the alpha values at the coefficients' x-values.
        """
        compare_pspline_whittaker(self, whittaker.aspls, self.y, lam=lam, test_rtol=2e-3)


class TestPsplinePsalsa(IterativeSplineTester):
    """Class for testing pspline_psalsa baseline."""

    func_name = 'pspline_psalsa'

    @pytest.mark.parametrize('p', (-1, 2))
    def test_outside_p_fails(self, p):
        """Ensures p values outside of [0, 1] raise an exception."""
        with pytest.raises(ValueError):
            self.class_func(self.y, p=p)

    @pytest.mark.parametrize('diff_order', (1, 3))
    def test_diff_orders(self, diff_order):
        """Ensure that other difference orders work."""
        lam = {1: 1e2, 3: 1e10}[diff_order]
        self.class_func(self.y, lam=lam, diff_order=diff_order)

    @pytest.mark.parametrize('lam', (1e1, 1e5))
    @pytest.mark.parametrize('p', (0.01, 0.1))
    def test_whittaker_comparison(self, lam, p):
        """Ensures the P-spline version is the same as the Whittaker version."""
        compare_pspline_whittaker(self, whittaker.psalsa, self.y, lam=lam, p=p)


class TestPsplineDerpsalsa(IterativeSplineTester):
    """Class for testing pspline_derpsalsa baseline."""

    func_name = 'pspline_derpsalsa'

    @pytest.mark.parametrize('p', (-1, 2))
    def test_outside_p_fails(self, p):
        """Ensures p values outside of [0, 1] raise an exception."""
        with pytest.raises(ValueError):
            self.class_func(self.y, p=p)

    @pytest.mark.parametrize('diff_order', (1, 3))
    def test_diff_orders(self, diff_order):
        """Ensure that other difference orders work."""
        lam = {1: 1e2, 3: 1e10}[diff_order]
        self.class_func(self.y, lam=lam, diff_order=diff_order)

    @pytest.mark.parametrize('lam', (1e1, 1e5))
    @pytest.mark.parametrize('p', (0.01, 0.1))
    def test_whittaker_comparison(self, lam, p):
        """Ensures the P-spline version is the same as the Whittaker version."""
        compare_pspline_whittaker(self, whittaker.derpsalsa, self.y, lam=lam, p=p)
