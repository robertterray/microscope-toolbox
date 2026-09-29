#!/usr/bin/env python

"""Tests for `microscope_toolbox` package."""

import pytest
from unittest.mock import MagicMock

from microscope_toolbox.main import do_stuff
import microscope_toolbox.main as main

my_mock = MagicMock()
requests_mock = MagicMock()


@pytest.fixture
def reduce(monkeypatch):
    """Sample pytest fixture."""
    my_mock.reset_mock()
    monkeypatch.setattr(main, "reduce", my_mock)
    my_mock.return_value = "some=fake&list=mock"


@pytest.fixture
def requests(monkeypatch):
    """Sample pytest fixture."""
    requests_mock.reset_mock()
    monkeypatch.setattr(main, "get", requests_mock)
    requests_mock.return_value = "fake_result"


def test_content_true(reduce, requests):
    """Sample pytest test function with the pytest fixture as an argument."""

    l = ["my", "test", "list"]
    b = True
    s = "prefix"

    r = do_stuff(l, b, s)

    print(my_mock.call_args)

    assert list(my_mock.call_args[0][1]) == ["prefix=my", "prefix=test", "prefix=list"]
    requests_mock.assert_called_with("www.terraytx.com/api/some=fake&list=mock")


def test_content_false(reduce, requests):
    """Sample pytest test function with the pytest fixture as an argument."""

    l = ["my", "test", "list"]
    b = False
    s = "prefix"

    r = do_stuff(l, b, s)

    assert list(my_mock.call_args[0][1]) == ["my", "test", "list"]

    requests_mock.assert_called_with("www.terraytx.com/api/some=fake&list=mock")
    assert r == "fake_result"
