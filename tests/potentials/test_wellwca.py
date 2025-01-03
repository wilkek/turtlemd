"""Test the DoubleWellPair potential."""
import logging

import numpy as np
import pytest

from turtlemd.potentials.well import DoubleWellPair
from turtlemd.system.box import Box
from turtlemd.system.particles import Particles
from turtlemd.system.system import System
from typing import List, Optional

CORRECT_FORCE = np.array([-2416.67712532, -2416.67712532, -2416.67712532])
CORRECT_VIRIAL = np.ones((3, 3)) * 483.33542506
CORRECT_VPOT = 873.18173451

POS1 = [
    [1.0, 1.0, 1.0],
    [2.25, 1.0, 1.0],
    [1.0, 2.0, 1.0],
    [1.0, 3.25, 1.0],
]
POS2 = [
    [1.0, 1.0, 1.0],
    [1.2, 1.2, 1.2],
    [1.0, 2.0, 1.0],
    [1.0, 3.25, 1.0],
]
PARAMETERS = {
    "rzero": 1.0,
    "width": 0.25,
    "height": 6.0,
}


def create_system(pos: Optional[List[List[float]]] = None) -> System:
    """Create a test system."""
    box = Box(high=[10, 10, 10])
    system = System(box=box, particles=Particles(dim=box.dim))
    if pos is None:
        pos = POS1
    system.particles.add_particle(pos=pos[0], mass=1.0, name="Ar1", ptype=0)
    system.particles.add_particle(pos=pos[1], mass=1.0, name="Ar2", ptype=0)
    system.particles.add_particle(pos=pos[2], mass=1.0, name="X", ptype=1)
    system.particles.add_particle(pos=pos[3], mass=1.0, name="X", ptype=1)
    return system


def test_parameters(caplog):
    """Test that the parameters are calculated correctly."""
    pot = DoubleWellPair(types=(0, 0))
    pot.set_parameters(PARAMETERS)
    assert pytest.approx(PARAMETERS["width"] ** 2) == pot.params["width2"]
    assert (
        pytest.approx(PARAMETERS["rzero"] + PARAMETERS["width"])
        == pot.params["rwidth"]
    )
    assert pytest.approx(PARAMETERS["height"] * 4) == pot.params["height4"]
    param = PARAMETERS.copy()
    param["extra"] = 123.0
    with caplog.at_level(logging.WARNING):
        pot.set_parameters(param)
        assert 'Ignored unknown parameter "extra"' in caplog.text


def test_min_max():
    """Test that the min/max of the potential are correct."""
    pot = DoubleWellPair(types=(0, 0))
    pot.set_parameters(PARAMETERS)
    min1, min2, max1 = pot.min_max()
    assert pytest.approx(min1) == 1.0
    assert pytest.approx(min2) == 1.5
    assert pytest.approx(max1) == 1.25


def test_activate():
    """Test that the potential activates for correct types."""
    pot = DoubleWellPair(types=(0, 0))
    assert pot.activate(0, 0)
    assert not pot.activate(0, 1)
    pot = DoubleWellPair(types=(0, 1))
    assert not pot.activate(0, 0)
    assert not pot.activate(1, 1)
    assert pot.activate(0, 1)
    assert pot.activate(1, 0)


def test_potential():
    """Test that we can calulate the potential energy correctly."""
    system = create_system()
    pot = DoubleWellPair(types=(0, 0))
    pot.set_parameters(PARAMETERS)
    vpot = pot.potential(system)
    assert pytest.approx(vpot) == 6


def test_force_and_potential():
    """Test that we can calculate the force, virial, and potential."""
    system = create_system(pos=POS2)
    pot = DoubleWellPair(types=(0, 0))
    pot.set_parameters(PARAMETERS)
    force, virial = pot.force(system)
    assert pytest.approx(force[0]) == CORRECT_FORCE
    assert pytest.approx(force[1]) == -CORRECT_FORCE
    assert pytest.approx(force[2]) == np.zeros(3)
    assert pytest.approx(force[3]) == np.zeros(3)
    assert pytest.approx(virial) == CORRECT_VIRIAL
    vpot, force2, virial2 = pot.potential_and_force(system)
    assert pytest.approx(force2) == force
    assert pytest.approx(virial2) == virial
    assert pytest.approx(vpot) == CORRECT_VPOT
