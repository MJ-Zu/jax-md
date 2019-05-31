# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for google3.third_party.py.jax_md.energy."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from absl.testing import absltest
from absl.testing import parameterized

from jax.config import config as jax_config
from jax import random
import jax.numpy as np

import numpy as onp

from jax.api import grad
from jax_md import space

from jax import test_util as jtu

from jax_md import energy
from jax_md.interpolate import spline

jax_config.parse_flags_with_absl()
FLAGS = jax_config.FLAGS

PARTICLE_COUNT = 10
STOCHASTIC_SAMPLES = 10
SPATIAL_DIMENSION = [2, 3]
UNIT_CELL_SIZE = [7, 8]

SOFT_SPHERE_ALPHA = [2.0, 3.0]


def lattice_repeater(small_cell_pos, latvec, no_rep):
  pos = onp.copy(small_cell_pos).tolist()
  for atom in small_cell_pos:
    for i in range(no_rep):
      for j in range(no_rep):
        for k in range(no_rep):
          if not i == j == k == 0:
            repeated_atom = atom + latvec[0] * i + latvec[1] * j + latvec[2] * k
            pos.append(onp.array(repeated_atom).tolist())
  return np.array(pos), latvec*no_rep

CUTOFF = 6.28721

NUM_SPLINE_POINTS = 21
dr = np.arange(0, NUM_SPLINE_POINTS) * (CUTOFF / NUM_SPLINE_POINTS)
drho = np.arange(0, 2, 2. / NUM_SPLINE_POINTS)

DENSITY_DATA = np.array([2.78589606e-01, 2.02694937e-01, 1.45334053e-01,
                      1.06069912e-01, 8.42517168e-02, 7.65140344e-02,
                      7.76263116e-02, 8.23214224e-02, 8.53322309e-02,
                      8.13915861e-02, 6.59095390e-02, 4.28915711e-02,
                      2.27910928e-02, 1.13713167e-02, 6.05020311e-03,
                      3.65836583e-03, 2.60587564e-03, 2.06750708e-03,
                      1.48749693e-03, 7.40019174e-04, 6.21225205e-05])

EMBEDDING_DATA = np.array([1.04222211e-10, -1.04142633e+00, -1.60359806e+00,
                       -1.89287637e+00, -2.09490167e+00, -2.26456628e+00,
                       -2.40590322e+00, -2.52245359e+00, -2.61385603e+00,
                       -2.67744693e+00, -2.71053295e+00, -2.71110418e+00,
                       -2.69287013e+00, -2.68464527e+00, -2.69204083e+00,
                       -2.68976209e+00, -2.66001244e+00, -2.60122024e+00,
                       -2.51338548e+00, -2.39650817e+00, -2.25058831e+00])
PAIRWISE_DATA = np.array([6.27032242e+01, 3.49638589e+01, 1.79007014e+01,
                  8.69001383e+00, 4.51545250e+00, 2.83260884e+00,
                  1.93216616e+00, 1.06795515e+00, 3.37740836e-01,
                  1.61087890e-02, -6.20816372e-02, -6.51314297e-02,
                  -5.35210341e-02, -5.20950200e-02, -5.51709524e-02,
                  -4.89093894e-02, -3.28051688e-02, -1.13738785e-02,
                  2.33833655e-03, 4.19132033e-03, 1.68600692e-04])


charge_fn = spline(DENSITY_DATA, dr[1] - dr[0])
embedding_fn = spline(EMBEDDING_DATA, drho[1] - drho[0])
pairwise_fn = spline(PAIRWISE_DATA, dr[1] - dr[0])


class EnergyTest(jtu.JaxTestCase):

  # pylint: disable=g-complex-comprehension
  @parameterized.named_parameters(jtu.cases_from_list(
      {
          'testcase_name': '_dim={}_alpha={}'.format(dim, alpha),
          'spatial_dimension': dim,
          'alpha': alpha,
      } for dim in SPATIAL_DIMENSION for alpha in SOFT_SPHERE_ALPHA))
  def test_soft_sphere(self, spatial_dimension, alpha):
    key = random.PRNGKey(0)

    for _ in range(STOCHASTIC_SAMPLES):
      key, split_dR, split_sigma, split_epsilon = random.split(key, 4)
      dR = random.normal(
          split_dR, (spatial_dimension,), dtype=np.float64)
      sigma = random.uniform(
          split_sigma, (1,), dtype=np.float64, minval=0.0, maxval=3.0)[0]
      dR = dR * sigma / np.sqrt(np.sum(dR ** 2, axis=1, keepdims=True))
      epsilon = random.uniform(
          split_epsilon, (1,), dtype=np.float64, minval=0.0, maxval=4.0)[0]
      self.assertAllClose(
          energy.soft_sphere(
              0.0 * dR, sigma, epsilon, alpha), epsilon / alpha, True)
      self.assertAllClose(
          energy.soft_sphere(dR, sigma, epsilon, alpha), 0.0, True)

      if alpha == 3.0:
        grad_energy = grad(energy.soft_sphere)
        g = grad_energy(dR, sigma, epsilon, alpha)
        self.assertAllClose(g, np.zeros_like(g), True)

  @parameterized.named_parameters(jtu.cases_from_list(
      {
          'testcase_name': '_dim={}'.format(dim),
          'spatial_dimension': dim,
      } for dim in SPATIAL_DIMENSION))
  def test_lennard_jones(self, spatial_dimension):
    key = random.PRNGKey(0)

    for _ in range(STOCHASTIC_SAMPLES):
      key, split_dR, split_sigma, split_epsilon = random.split(key, 4)
      dR = random.normal(
          split_dR, (spatial_dimension,), dtype=np.float64)
      sigma = random.uniform(
          split_sigma, (1,), dtype=np.float64, minval=0.5, maxval=3.0)[0]
      dR = dR * sigma / np.sqrt(np.sum(dR ** 2, keepdims=True))
      epsilon = random.uniform(
          split_epsilon, (1,), dtype=np.float64, minval=0.0, maxval=4.0)[0]
      self.assertAllClose(
          energy.lennard_jones(dR, sigma, epsilon), -epsilon, True)
      g = grad(energy.lennard_jones)(dR, sigma, epsilon)
      self.assertAllClose(g, np.zeros_like(g), True)


  @parameterized.named_parameters(jtu.cases_from_list(
      {
          'testcase_name': '_dim={}'.format(num_repetitions),
          'num_repetitions': num_repetitions,
      } for num_repetitions in UNIT_CELL_SIZE))
  def test_eam(self, num_repetitions):
    latvec = np.array([[0, 1, 1], [1, 0, 1], [1, 1, 0]]) * 4.05 / 2
    atoms = np.array([[0, 0, 0]])
    atoms_repeated, latvec_repeated = lattice_repeater(atoms, latvec, num_repetitions)
    inv_latvec = np.array(onp.linalg.inv(onp.array(latvec_repeated)))
    displacement, shift = space.periodic_general(latvec_repeated)
    eam_energy = energy.eam(displacement, charge_fn, embedding_fn, pairwise_fn)
    self.assertAllClose(
        eam_energy(np.dot(atoms_repeated, inv_latvec))/num_repetitions**3, -3.366, True)


if __name__ == '__main__':
  absltest.main()

