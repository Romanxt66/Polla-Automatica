import pytest

from app.services.scoring import calculate_points, is_exact


@pytest.mark.parametrize(
    "pred,real,points",
    [
        # exactos
        ((2, 1), (2, 1), 5),
        ((0, 0), (0, 0), 5),
        ((1, 1), (1, 1), 5),
        ((0, 3), (0, 3), 5),
        ((10, 0), (10, 0), 5),
        # ganador + misma diferencia (no exacto)
        ((2, 1), (3, 2), 3),
        ((1, 0), (4, 3), 3),
        ((0, 1), (2, 3), 3),
        ((1, 1), (2, 2), 3),  # empate con otro marcador
        ((0, 0), (3, 3), 3),
        # solo ganador / empate
        ((2, 0), (1, 0), 1),
        ((3, 0), (1, 0), 1),
        ((0, 2), (1, 4), 1),
        # fallos
        ((2, 1), (1, 2), 0),
        ((1, 0), (0, 0), 0),
        ((0, 0), (1, 0), 0),
        ((1, 1), (0, 1), 0),
        ((0, 1), (1, 0), 0),
        ((2, 2), (3, 1), 0),
    ],
)
def test_calculate_points(pred, real, points):
    assert calculate_points(*pred, *real) == points


def test_is_exact():
    assert is_exact(2, 1, 2, 1)
    assert not is_exact(2, 1, 1, 2)
    assert not is_exact(1, 1, 2, 2)


def test_symmetry_home_and_away_swapped():
    for pred, real in [((2, 1), (3, 2)), ((2, 0), (1, 0)), ((1, 1), (2, 2)), ((2, 1), (2, 1))]:
        swapped = calculate_points(pred[1], pred[0], real[1], real[0])
        assert swapped == calculate_points(*pred, *real)
