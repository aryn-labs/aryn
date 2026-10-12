"""Ingress configuration is explicit, bounded to Hosted HTTPS, with no embedded secret."""

import pytest
from packages.config import ARYNSettings


@pytest.mark.parametrize(
    "origin",
    [
        "http://studio.example",
        "https://127.0.0.1",
        "https://localhost",
        "https://user:synthetic@studio.example",
        "https://studio.example/path",
        "https://studio.example?token=synthetic",
        "https://studio.example#fragment",
    ],
)
def test_invalid_origin_cannot_configure_ingress(origin):
    with pytest.raises(ValueError):
        ARYNSettings(webhook_ingress_origin=origin)


def test_ingress_is_opt_in_not_a_default_public_url():
    assert ARYNSettings().webhook_ingress_origin == ""
    assert (
        ARYNSettings(
            webhook_ingress_origin="https://studio.example/"
        ).webhook_ingress_origin
        == "https://studio.example"
    )
