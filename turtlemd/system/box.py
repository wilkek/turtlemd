"""Define a simulation box."""
import itertools
import logging
from abc import ABC, abstractmethod

import numpy as np
from typing import List, Union

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


def guess_dimensionality(
    low: Union[np.ndarray, List[float], List[int], None] = None,
    high: Union[np.ndarray, List[float], List[int], None] = None,
    periodic: Union[List[bool], None] = None,
) -> int:
    """Figure out the number of dimensions from the box input."""
    dims = []
    if low is not None:
        dims.append(len(low))
    if high is not None:
        dims.append(len(high))
    if periodic is not None:
        dims.append(len(periodic))

    if len(dims) == 0:
        LOGGER.warning(
            "Missing low/high/periodic parameters for box: assuming 1D"
        )
        return 1
    if len(set(dims)) != 1:
        LOGGER.error("Inconsistent box dimensions for low/high/periodic!")
        raise ValueError("Inconsistent box dimensions for low/high/periodic!")
    return dims[0]  # They should all be equal, pick the first.


def cosine(angle: float) -> float:
    """Return cosine of an angle given in degrees.

    Note:
        If the angle is close to 90.0 we return 0.0.

    Args:
        angle: The angle in degrees.

    Returns:
        The cosine of the angle.
    """
    if np.isclose(angle, 90):
        return 0.0
    return np.cos(np.radians(angle))


def box_matrix_from_angles(
    length: np.ndarray, alpha: float, beta: float, gamma: float, dim: int
) -> np.ndarray:
    """Return the box matrix from given lengths and angles.

    Args:
        length: The box lengths as a 1D array.
        alpha: The angle between b and c in degrees.
        beta: The angle between a and c in degrees.
        gamma: The angle between a and b in degrees.
        dim: The dimensionality.

    Returns:
        The (upper triangular) box matrix.

    Note:
        The angles and box lengths follow the convention from
        LAMMPS (https://docs.lammps.org/Howto_triclinic.html).
    """
    box_matrix = np.zeros((dim, dim))
    cos_alpha = cosine(alpha)
    cos_beta = cosine(beta)
    cos_gamma = cosine(gamma)
    box_matrix[0, 0] = length[0]
    box_matrix[0, 1] = length[1] * cos_gamma
    box_matrix[1, 1] = np.sqrt(length[1] ** 2 - box_matrix[0, 1] ** 2)
    if dim > 2:
        box_matrix[0, 2] = length[2] * cos_beta
        box_matrix[1, 2] = (
            length[1] * length[2] * cos_alpha
            - box_matrix[0, 1] * box_matrix[0, 2]
        ) / box_matrix[1, 1]
        box_matrix[2, 2] = np.sqrt(
            length[2] ** 2 - box_matrix[0, 2] ** 2 - box_matrix[1, 2] ** 2
        )
    return box_matrix


class BoxBase(ABC):
    """Define a generic simulation box.

    Attributes:
        dim (int): The dimensionality of the box.
        dof (np.ndarray): The degrees of freedom removed by periodicity.
        periodic (list[bool]): Specifies which dimensions for
            which we should apply periodic boundaries.
        box_matrix (np.ndarray): 2D matrix (upper triangular), representing
            the simulation cell.
        low (np.ndarray): The lower limits of the simulation box.
        high (np.ndarray): The upper limits of the simulation box.
        length (np.ndarray): The box lengths
        ilength (np.ndarray): The inverse box lengths.
    """

    dim: int
    dof: np.ndarray
    periodic: List[bool]
    box_matrix: np.ndarray
    low: np.ndarray
    high: np.ndarray
    length: np.ndarray
    ilength: np.ndarray

    def __init__(
        self,
        dim: int,
        periodic: Union[List[bool], None],
        low: Union[np.ndarray, List[float], List[int], None] = None,
        high: Union[np.ndarray, List[float], List[int], None] = None,
    ) -> None:
        """Create a generic box.

        Args:
            dim: The dimensionality of the box.
            periodic: Specifies which dimensions for which we should
                apply periodic boundaries.
        """
        self.dim = dim
        if periodic is not None:
            self.periodic = periodic
        else:
            self.periodic = [True] * self.dim
        assert self.dim == len(self.periodic)
        # Keep track of the degrees of freedom removed by periodic
        # boundaries:
        self.dof = np.array([1 if i else 0 for i in self.periodic])
        self.box_matrix = np.zeros((self.dim, self.dim))
        # Interpret low and high arguments:
        if low is not None:
            self.low = np.asarray(low).astype(float)
        else:
            self.low = np.array(
                [0.0 if i else -float("inf") for i in self.periodic]
            )
            LOGGER.warning("Set box low values: %s", self.low)

        if high is not None:
            self.high = np.asarray(high).astype(float)
        else:
            self.high = np.array(
                [1.0 if i else float("inf") for i in self.periodic]
            )
            LOGGER.warning("Set box high values: %s", self.high)
        self.length = self.high - self.low
        self.ilength = 1.0 / self.length

    def volume(self) -> float:
        """Calculate volume of the simulation cell."""
        return np.linalg.det(self.box_matrix)

    @abstractmethod
    def pbc_wrap(self, pos: np.ndarray) -> np.ndarray:
        """Apply periodic boundaries to positions."""

    @abstractmethod
    def pbc_dist(self, distance: np.ndarray) -> np.ndarray:
        """Apply periodic boundaries to a distance vector."""

    @abstractmethod
    def pbc_dist_matrix(self, distance: np.ndarray) -> np.ndarray:
        """Apply periodic boundaries to a matrix of distance vectors."""


class TriclinicBox(BoxBase):
    """An triclinic simulation box.

    Attributes:
        alpha (float): The angle between b and c in degrees.
        beta (float): The angle between a and c in degrees.
        gamma (float): The angle between a and b in degrees.
        box_matrix_inv (np.ndarray): The inverse of the box matrix.
        translations (np.ndarray): Translation vectors to the nearest
            images.
        shortest_width (float): The shortest width of the box.
        shortest_width_half (float): `0.5 * shortest_width`.

    """

    alpha: float
    beta: float
    gamma: float

    def __init__(
        self,
        low: Union[np.ndarray, List[float], List[int], None] = None,
        high: Union[np.ndarray, List[float], List[int], None] = None,
        periodic: Union[List[bool], None] = None,
        alpha: Union[float, None] = None,
        beta: Union[float, None] = None,
        gamma: Union[float, None] = None,
    ):
        """Create the box."""
        super().__init__(
            dim=guess_dimensionality(low=low, high=high, periodic=periodic),
            periodic=periodic,
            low=low,
            high=high,
        )

        self.alpha = alpha if alpha is not None else 90
        self.beta = beta if beta is not None else 90
        self.gamma = gamma if gamma is not None else 90

        tricl = not (self.alpha == self.beta == self.gamma == 90)

        self.box_matrix = np.zeros((self.dim, self.dim))
        self.box_matrix_inv = np.zeros((self.dim, self.dim))
        self.translations = np.zeros((3**self.dim, self.dim))
        if tricl and self.dim > 1:
            self.update_box_matrix(
                self.length, self.alpha, self.beta, self.gamma
            )
        else:
            msg = "Not a valid triclinic box."
            msg += "\n-At least one angle must be != 90."
            msg += "\n-The dimensionality must be > 1."
            raise ValueError(msg)

    def update_box_matrix(
        self, length: np.ndarray, alpha: float, beta: float, gamma: float
    ):
        """Update the box matrix.

        Args:
            length (np.ndarray): The length of the box vectors.
            alpha (float): The angle between b and c in degrees.
            beta (float): The angle between a and c in degrees.
            gamma (float): The angle between a and b in degrees.
        """
        self.box_matrix = box_matrix_from_angles(
            length, alpha, beta, gamma, self.dim
        )
        self.box_matrix_inv = np.linalg.inv(self.box_matrix)
        self.translations = np.array(
            [
                np.dot(self.box_matrix, np.array(index))
                for index in itertools.product([-1, 0, 1], repeat=self.dim)
            ]
        )
        self.shortest_width = np.min(np.diagonal(self.box_matrix))
        self.shortest_width_half = 0.5 * self.shortest_width

    def pbc_wrap(self, pos: np.ndarray) -> np.ndarray:
        """Apply periodic boundaries to positions.

        Args:
            pos (np.ndarray): Positions to apply periodic
                boundaries to.

        Returns:
            np.ndarray: The periodic-boundary wrapped positions,
                same shape as parameter `pos`.
        """
        frac = pos @ self.box_matrix_inv.T
        frac = frac - np.floor(frac)
        return frac @ self.box_matrix.T + self.low

    def pbc_dist(self, distance: np.ndarray) -> np.ndarray:
        """Apply periodic boundaries to a distance vector.

        Args:
            distance (np.ndarray): The distance vector to apply PBC to.

        Note:
            This method is based on Mezei [1], but it does not use all the
            optimizations (since it is using numpy operations).

            [1] M. Mezei, Determining Nearest Image in non-Orthogonal
                Periodic Systems, Information Quarterly for Computer
                Simulation of Condensed Phases, No 34, 48-51 (1992).
                https://mezeim01.dmz.hpc.mssm.edu/ms/cv78ccp5.pdf
        """
        dist = distance - self.box_matrix @ np.rint(
            self.box_matrix_inv @ distance
        )
        smallest = (dist, np.dot(dist, dist))
        if np.sqrt(smallest[1]) < self.shortest_width_half:
            return smallest[0]
        images = dist + self.translations
        lengths = np.sum(images * images, axis=1)
        idx = np.argmin(lengths)
        if lengths[idx] < smallest[1]:
            smallest = (images[idx], lengths[idx])
        return smallest[0]

    def pbc_dist_matrix(self, distance: np.ndarray) -> np.ndarray:
        """Apply periodic boundaries to a matrix of distance vectors.

        Args:
            distance (np.ndarray): The distance vectors.

        Returns:
            np.ndarray: The PBC-wrapped distances, same shape as the
                `distance` parameter.
        """
        return np.array([self.pbc_dist(i) for i in distance])

    def __str__(self) -> str:
        """Return a string describing the box."""
        msg = (
            "Hello, this is triclinic box and my matrix "
            f"is:\n{self.box_matrix}"
            f"Periodic? {self.periodic}"
        )
        return msg


class Box(BoxBase):
    """An orthogonal simulation box."""

    def __init__(
        self,
        low: Union[np.ndarray, List[float], List[int], None] = None,
        high: Union[np.ndarray, List[float], List[int], None] = None,
        periodic: Union[List[bool], None] = None,
    ):
        """Create the box."""
        super().__init__(
            dim=guess_dimensionality(low=low, high=high, periodic=periodic),
            low=low,
            high=high,
            periodic=periodic,
        )
        # Create the box matrix:
        self.box_matrix = np.zeros((self.dim, self.dim))
        for i in range(self.dim):
            self.box_matrix[i, i] = self.length[i]

    def pbc_wrap(self, pos: np.ndarray) -> np.ndarray:
        """Apply periodic boundaries to positions.

        Args:
            pos (np.ndarray): Positions to apply periodic
                boundaries to.

        Returns:
            np.ndarray: The periodic-boundary wrapped positions,
                same shape as parameter `pos`.
        """
        pbcpos = np.zeros_like(pos)
        for i, periodic in enumerate(self.periodic):
            if periodic:
                low = self.low[i]
                length = self.length[i]
                ilength = self.ilength[i]
                relpos = pos[:, i] - low
                delta = np.where(
                    np.logical_or(relpos < 0.0, relpos >= length),
                    relpos - np.floor(relpos * ilength) * length,
                    relpos,
                )
                pbcpos[:, i] = delta + low
            else:
                pbcpos[:, i] = pos[:, i]
        return pbcpos

    def pbc_dist(self, distance: np.ndarray) -> np.ndarray:
        """Apply periodic boundaries to a distance vector."""
        pbcdist = np.zeros_like(distance)
        for i, (periodic, length, ilength) in enumerate(
            zip(self.periodic, self.length, self.ilength)
        ):
            if periodic and np.abs(distance[i]) > 0.5 * length:
                pbcdist[i] = (
                    distance[i] - np.rint(distance[i] * ilength) * length
                )
            else:
                pbcdist[i] = distance[i]
        return pbcdist

    def pbc_dist_matrix(self, distance: np.ndarray) -> np.ndarray:
        """Apply periodic boundaries to a matrix of distance vectors.

        Args:
            distance (np.ndarray): The distance vectors.

        Returns:
            np.ndarray: The PBC-wrapped distances, same shape as the
                `distance` parameter.
        """
        pbcdist = np.copy(distance)
        for i, (periodic, length, ilength) in enumerate(
            zip(self.periodic, self.length, self.ilength)
        ):
            if periodic:
                dist = pbcdist[:, i]
                high = 0.5 * length
                k = np.where(np.abs(dist) >= high)[0]
                dist[k] -= np.rint(dist[k] * ilength) * length
        return pbcdist

    def __str__(self) -> str:
        """Return a string describing the box."""
        msg = (
            f"Hello, this is box and my matrix is:\n{self.box_matrix}"
            f"\nPeriodic? {self.periodic}"
        )
        return msg
